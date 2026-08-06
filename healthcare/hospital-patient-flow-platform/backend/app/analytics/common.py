"""Shared primitives for the analytics modules.

The one piece of real machinery here is :func:`expand_to_days`, which
converts interval records (a patient occupying a bed from X to Y) into
per-day occupancy fractions. Every capacity, nursing and safety-rate
metric in the platform ultimately divides by the patient days it produces,
so it is written once and reused rather than re-derived per module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Literal

import numpy as np
import pandas as pd

Grain = Literal["day", "week", "month", "quarter", "year"]

_GRAIN_FREQ = {"day": "D", "week": "W-SUN", "month": "MS", "quarter": "QS", "year": "YS"}


@dataclass
class MetricValue:
    """One computed indicator, ready to be rendered as a dashboard tile."""

    key: str
    label_en: str
    label_ar: str
    value: float | None
    unit: str = ""
    numerator: float | None = None
    denominator: float | None = None
    target: float | None = None
    status: str = "unknown"          # green | amber | red | unknown
    trend_pct: float | None = None   # change against the preceding period
    higher_is_better: bool = False
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label_en": self.label_en,
            "label_ar": self.label_ar,
            "value": _round(self.value),
            "unit": self.unit,
            "numerator": _round(self.numerator),
            "denominator": _round(self.denominator),
            "target": _round(self.target),
            "status": self.status,
            "trend_pct": _round(self.trend_pct),
            "higher_is_better": self.higher_is_better,
            "context": self.context,
        }


def _round(value, digits: int = 2):
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        if np.isnan(value) or np.isinf(value):
            return None
        return round(float(value), digits)
    return value


def safe_div(numerator, denominator, *, scale: float = 1.0) -> float | None:
    """Division that returns None instead of raising or producing inf.

    Rate metrics are routinely computed over periods with an empty
    denominator (a unit that was closed, a day with no discharges). None
    renders as "no data" rather than a misleading zero.
    """
    if numerator is None or denominator in (None, 0):
        return None
    try:
        result = float(numerator) / float(denominator) * scale
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if np.isnan(result) or np.isinf(result):
        return None
    return result


def period_bounds(grain: Grain, reference: date) -> tuple[date, date]:
    """Inclusive start/end of the period containing ``reference``."""
    if grain == "day":
        return reference, reference
    if grain == "week":
        start = reference - timedelta(days=(reference.weekday() + 1) % 7)   # week starts Sunday
        return start, start + timedelta(days=6)
    if grain == "month":
        start = reference.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)
    if grain == "quarter":
        quarter_start_month = 3 * ((reference.month - 1) // 3) + 1
        start = reference.replace(month=quarter_start_month, day=1)
        next_quarter = (start + timedelta(days=95)).replace(day=1)
        return start, next_quarter - timedelta(days=1)
    if grain == "year":
        return reference.replace(month=1, day=1), reference.replace(month=12, day=31)
    raise ValueError(f"Unsupported grain '{grain}'")


def previous_period(grain: Grain, start: date, end: date) -> tuple[date, date]:
    """The equivalent window immediately before ``start``, used for trends."""
    span = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=span - 1), previous_end


def to_period(series: pd.Series, grain: Grain) -> pd.Series:
    """Bucket a datetime series onto period start dates."""
    stamps = pd.to_datetime(series, errors="coerce")
    if grain == "day":
        return stamps.dt.floor("D")
    if grain == "week":
        # Align weeks to Sunday, the Saudi working-week convention.
        return (stamps - pd.to_timedelta((stamps.dt.weekday + 1) % 7, unit="D")).dt.floor("D")
    if grain == "month":
        return stamps.dt.to_period("M").dt.start_time
    if grain == "quarter":
        return stamps.dt.to_period("Q").dt.start_time
    if grain == "year":
        return stamps.dt.to_period("Y").dt.start_time
    raise ValueError(f"Unsupported grain '{grain}'")


def expand_to_days(
    intervals: pd.DataFrame,
    *,
    start_col: str = "in_at",
    end_col: str = "out_at",
    group_cols: Iterable[str] = ("unit_id",),
    window_start: date | None = None,
    window_end: date | None = None,
    open_interval_end: datetime | None = None,
) -> pd.DataFrame:
    """Turn occupancy intervals into per-day fractional patient days.

    A patient who occupies a bed from 22:00 on Monday to 06:00 on Wednesday
    contributes 0.083 days to Monday, 1.0 to Tuesday and 0.25 to Wednesday
    -- not "2 midnights". Midnight-census counting is what makes short-stay
    and observation activity vanish from occupancy reports, so the platform
    does not use it as the primary denominator.

    Returns a frame of ``group_cols + [service_date, patient_days, patients]``.
    """
    group_cols = list(group_cols)
    if intervals.empty:
        return pd.DataFrame(columns=group_cols + ["service_date", "patient_days", "patients"])

    frame = intervals.copy()
    frame[start_col] = pd.to_datetime(frame[start_col], errors="coerce")
    frame[end_col] = pd.to_datetime(frame[end_col], errors="coerce")

    # Still-admitted patients have no end timestamp; cap them at "now" (or
    # the caller's window end) so they count toward current occupancy.
    fallback_end = pd.Timestamp(open_interval_end or datetime.now())
    if window_end is not None:
        fallback_end = min(fallback_end, pd.Timestamp(window_end) + pd.Timedelta(days=1))
    frame[end_col] = frame[end_col].fillna(fallback_end)

    frame = frame[frame[start_col].notna() & (frame[end_col] > frame[start_col])]
    if frame.empty:
        return pd.DataFrame(columns=group_cols + ["service_date", "patient_days", "patients"])

    if window_start is not None:
        clip_lo = pd.Timestamp(window_start)
        frame[start_col] = frame[start_col].clip(lower=clip_lo)
    if window_end is not None:
        clip_hi = pd.Timestamp(window_end) + pd.Timedelta(days=1)
        frame[end_col] = frame[end_col].clip(upper=clip_hi)
    frame = frame[frame[end_col] > frame[start_col]]
    if frame.empty:
        return pd.DataFrame(columns=group_cols + ["service_date", "patient_days", "patients"])

    # Explode each interval into one row per calendar day it touches.
    frame = frame.reset_index(drop=True)
    day_starts = frame[start_col].dt.floor("D")
    day_ends = (frame[end_col] - pd.Timedelta(nanoseconds=1)).dt.floor("D")
    spans = ((day_ends - day_starts).dt.days + 1).clip(lower=1)

    repeat_index = np.repeat(frame.index.values, spans.values)
    offsets = np.concatenate([np.arange(n) for n in spans.values])

    exploded = frame.loc[repeat_index].reset_index(drop=True)
    exploded["service_date"] = (
        day_starts.loc[repeat_index].reset_index(drop=True) + pd.to_timedelta(offsets, unit="D")
    )

    segment_start = np.maximum(
        exploded[start_col].values.astype("datetime64[ns]"),
        exploded["service_date"].values.astype("datetime64[ns]"),
    )
    segment_end = np.minimum(
        exploded[end_col].values.astype("datetime64[ns]"),
        (exploded["service_date"] + pd.Timedelta(days=1)).values.astype("datetime64[ns]"),
    )
    seconds = (segment_end - segment_start) / np.timedelta64(1, "s")
    exploded["patient_days"] = np.clip(seconds / 86400.0, 0, 1)
    exploded["service_date"] = exploded["service_date"].dt.date

    aggregated = (
        exploded.groupby(group_cols + ["service_date"], dropna=False)
        .agg(patient_days=("patient_days", "sum"), patients=("patient_days", "size"))
        .reset_index()
    )
    return aggregated


def daily_index(start: date, end: date) -> pd.DatetimeIndex:
    return pd.date_range(start=start, end=end, freq="D")


def rag_status(value: float | None, *, target: float | None, amber: float | None,
               red: float | None, higher_is_better: bool) -> str:
    """Classify a value against its benchmark thresholds.

    ``amber``/``red`` are the boundaries at which performance stops being
    acceptable. For a "lower is better" metric such as door-to-doctor,
    crossing above ``red`` is red; for "higher is better" metrics the
    comparison flips.
    """
    if value is None:
        return "unknown"
    if higher_is_better:
        if red is not None and value < red:
            return "red"
        if amber is not None and value < amber:
            return "amber"
        if target is not None or amber is not None:
            return "green"
        return "unknown"
    if red is not None and value > red:
        return "red"
    if amber is not None and value > amber:
        return "amber"
    if target is not None or amber is not None:
        return "green"
    return "unknown"


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def median_minutes(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values >= 0]
    return float(values.median()) if len(values) else None


def percentile_minutes(series: pd.Series, q: float) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values >= 0]
    return float(values.quantile(q)) if len(values) else None


def interval_minutes(later: pd.Series, earlier: pd.Series) -> pd.Series:
    """Minutes between two datetime columns, negatives dropped.

    A negative interval means the source timestamps are inconsistent. The
    ingestion layer already flags those rows; here they are excluded so a
    handful of bad records cannot drag a median below zero.
    """
    delta = (pd.to_datetime(later, errors="coerce") - pd.to_datetime(earlier, errors="coerce"))
    minutes = delta.dt.total_seconds() / 60
    return minutes.where(minutes >= 0)
