"""Emergency department analytics, including NEDOCS crowding.

Timing metrics report the median rather than the mean throughout. ED
interval distributions have a long right tail -- one patient boarding for
30 hours moves a mean far more than it moves the experience of the typical
patient -- so medians are what get acted on, with the 90th percentile
reported alongside to keep the tail visible.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.analytics.benchmarks import make_metric
from app.analytics.common import (
    MetricValue,
    interval_minutes,
    median_minutes,
    percentile_minutes,
    safe_div,
)

NEDOCS_BANDS = (
    (20, "NOT_BUSY", "غير مزدحم"),
    (60, "BUSY", "مزدحم"),
    (100, "EXTREMELY_BUSY", "مزدحم جداً"),
    (140, "OVERCROWDED", "مكتظ"),
    (180, "SEVERELY_OVERCROWDED", "مكتظ بشدة"),
    (float("inf"), "DANGEROUSLY_OVERCROWDED", "مكتظ بشكل خطير"),
)


def nedocs(
    *,
    ed_patients: int,
    ed_beds: int,
    admitted_in_ed: int,
    hospital_beds: int,
    longest_admit_wait_hours: float,
    longest_waiting_room_minutes: float,
    ventilated_patients: int = 0,
) -> tuple[float, str, str]:
    """National Emergency Department Overcrowding Scale.

    Returns ``(score, band_code, band_ar)``. The published instrument is
    calibrated on a 0-200 range, so the result is clipped there; values
    beyond 200 add no discriminating information but do make trend charts
    unreadable.
    """
    if ed_beds <= 0 or hospital_beds <= 0:
        return 0.0, "UNKNOWN", "غير معروف"

    score = (
        -20.0
        + 85.8 * (ed_patients / ed_beds)
        + 600.0 * (admitted_in_ed / hospital_beds)
        + 13.4 * float(longest_admit_wait_hours or 0)
        + 0.93 * float(longest_waiting_room_minutes or 0)
        + 5.64 * int(ventilated_patients or 0)
    )
    score = float(np.clip(score, 0, 200))
    for ceiling, code, arabic in NEDOCS_BANDS:
        if score <= ceiling:
            return round(score, 1), code, arabic
    return round(score, 1), "DANGEROUSLY_OVERCROWDED", "مكتظ بشكل خطير"


def hourly_state(visits: pd.DataFrame, start: date, end: date, *,
                 ed_beds: int, hospital_beds: int) -> pd.DataFrame:
    """Reconstruct the ED hour by hour: census, boarders and NEDOCS.

    This is what makes retrospective crowding analysis possible from a flat
    visit extract -- the platform never needs a live feed to tell a
    director which hours of which days the department was over its limit.
    """
    columns = ["bucket_start", "arrivals", "departures", "census", "boarders",
               "longest_boarding_hours", "longest_wait_minutes", "ventilated",
               "nedocs_score", "nedocs_band"]
    if visits.empty:
        return pd.DataFrame(columns=columns)

    frame = visits.copy()
    buckets = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1),
                            freq="h", inclusive="left")

    arrival = frame["arrival_at"]
    # A visit with no departure timestamp is treated as ending at disposition,
    # then at arrival, so an incomplete record cannot occupy the ED forever.
    departure = frame["departure_at"].fillna(frame["disposition_at"]).fillna(frame["arrival_at"])
    decision = frame["admission_decision_at"].fillna(frame["disposition_at"])
    is_admit = frame["ed_disposition"].eq("ADMIT")
    ventilated = frame["on_ventilator"].fillna(False).astype(bool)
    # Patients still waiting for a treatment space at the top of the hour.
    room_time = frame["room_at"].fillna(frame["physician_at"])

    rows = []
    for bucket in buckets:
        bucket_end = bucket + pd.Timedelta(hours=1)
        # NEDOCS is an instantaneous instrument: it describes the department
        # at a moment, not everyone who passed through the hour. Using
        # interval overlap here would count a patient who arrived at 10:55
        # as present at 10:00 and give them a negative waiting time.
        present = (arrival <= bucket) & (departure > bucket)

        if not present.any():
            rows.append({
                "bucket_start": bucket, "arrivals": int(((arrival >= bucket) & (arrival < bucket_end)).sum()),
                "departures": int(((departure >= bucket) & (departure < bucket_end)).sum()),
                "census": 0, "boarders": 0, "longest_boarding_hours": 0.0,
                "longest_wait_minutes": 0.0, "ventilated": 0,
                "nedocs_score": 0.0, "nedocs_band": "NOT_BUSY",
            })
            continue

        boarding = present & is_admit & decision.notna() & (decision <= bucket)
        boarding_hours = (
            ((bucket - decision[boarding]).dt.total_seconds() / 3600).clip(lower=0)
            if boarding.any() else pd.Series(dtype=float)
        )

        waiting = present & (room_time.isna() | (room_time > bucket))
        wait_minutes = (
            ((bucket - arrival[waiting]).dt.total_seconds() / 60).clip(lower=0)
            if waiting.any() else pd.Series(dtype=float)
        )

        census = int(present.sum())
        boarders = int(boarding.sum())
        longest_board = float(boarding_hours.max()) if len(boarding_hours) else 0.0
        longest_wait = float(wait_minutes.max()) if len(wait_minutes) else 0.0
        vents = int((present & ventilated).sum())

        score, band, _ = nedocs(
            ed_patients=census, ed_beds=ed_beds, admitted_in_ed=boarders,
            hospital_beds=hospital_beds, longest_admit_wait_hours=longest_board,
            longest_waiting_room_minutes=longest_wait, ventilated_patients=vents,
        )
        rows.append({
            "bucket_start": bucket,
            "arrivals": int(((arrival >= bucket) & (arrival < bucket_end)).sum()),
            "departures": int(((departure >= bucket) & (departure < bucket_end)).sum()),
            "census": census,
            "boarders": boarders,
            "longest_boarding_hours": round(longest_board, 2),
            "longest_wait_minutes": round(longest_wait, 1),
            "ventilated": vents,
            "nedocs_score": score,
            "nedocs_band": band,
        })
    return pd.DataFrame(rows, columns=columns)


def compute(
    *,
    visits: pd.DataFrame,
    ed_beds: int,
    hospital_beds: int,
    start: date,
    end: date,
    previous: dict[str, float] | None = None,
    overrides: dict[str, dict] | None = None,
) -> tuple[list[MetricValue], dict]:
    previous = previous or {}
    days_in_period = (end - start).days + 1

    if visits.empty:
        empty = [make_metric(key, None, overrides=overrides) for key in (
            "ed_visits", "door_to_triage_min", "door_to_physician_min",
            "door_to_disposition_min", "ed_los_min", "ed_boarding_min", "lwbs_rate",
            "lama_rate", "ed_revisit_72h_rate", "admission_rate", "ctas_1_2_share",
            "nedocs_score",
        )]
        return empty, {"hourly": [], "ctas_distribution": {}, "arrival_profile": [],
                       "peak_hours": []}

    frame = visits.copy()
    total = len(frame)

    frame["door_to_triage"] = interval_minutes(frame["triage_at"], frame["arrival_at"])
    frame["door_to_room"] = interval_minutes(frame["room_at"], frame["arrival_at"])
    frame["door_to_physician"] = interval_minutes(frame["physician_at"], frame["arrival_at"])
    frame["door_to_disposition"] = interval_minutes(frame["disposition_at"], frame["arrival_at"])
    frame["ed_los"] = interval_minutes(frame["departure_at"], frame["arrival_at"])
    frame["boarding"] = interval_minutes(
        frame["departure_at"], frame["admission_decision_at"].fillna(frame["disposition_at"])
    )

    completed = frame[~frame["is_lwbs"].fillna(False).astype(bool)]
    admitted = frame[frame["ed_disposition"] == "ADMIT"]

    lwbs = int(frame["is_lwbs"].fillna(False).astype(bool).sum())
    lama = int(frame["is_lama"].fillna(False).astype(bool).sum())
    revisits = int(frame["is_72h_revisit"].fillna(False).astype(bool).sum())
    high_acuity = int(frame["ctas_level"].isin([1, 2]).sum())

    hourly = hourly_state(frame, start, end, ed_beds=ed_beds, hospital_beds=hospital_beds)
    mean_nedocs = float(hourly["nedocs_score"].mean()) if not hourly.empty else None
    peak_nedocs = float(hourly["nedocs_score"].max()) if not hourly.empty else None
    hours_overcrowded = int((hourly["nedocs_score"] > 100).sum()) if not hourly.empty else 0

    metrics = [
        make_metric("ed_visits", float(total), denominator=days_in_period,
                    previous=previous.get("ed_visits"), overrides=overrides,
                    context={"per_day": round(total / days_in_period, 1)}),
        make_metric("door_to_triage_min", median_minutes(frame["door_to_triage"]),
                    previous=previous.get("door_to_triage_min"), overrides=overrides,
                    context={"p90": percentile_minutes(frame["door_to_triage"], 0.9)}),
        make_metric("door_to_physician_min", median_minutes(frame["door_to_physician"]),
                    previous=previous.get("door_to_physician_min"), overrides=overrides,
                    context={"p90": percentile_minutes(frame["door_to_physician"], 0.9),
                             "by_ctas": _median_by_ctas(frame, "door_to_physician")}),
        make_metric("door_to_disposition_min", median_minutes(frame["door_to_disposition"]),
                    previous=previous.get("door_to_disposition_min"), overrides=overrides,
                    context={"p90": percentile_minutes(frame["door_to_disposition"], 0.9)}),
        make_metric("ed_los_min", median_minutes(completed["ed_los"]),
                    previous=previous.get("ed_los_min"), overrides=overrides,
                    context={"p90": percentile_minutes(completed["ed_los"], 0.9),
                             "admitted_median": median_minutes(admitted["ed_los"]),
                             "discharged_median": median_minutes(
                                 completed[completed["ed_disposition"] == "DISCHARGE"]["ed_los"])}),
        make_metric("ed_boarding_min", median_minutes(admitted["boarding"]),
                    numerator=None, denominator=len(admitted) or None,
                    previous=previous.get("ed_boarding_min"), overrides=overrides,
                    context={"p90": percentile_minutes(admitted["boarding"], 0.9),
                             "boarded_over_4h": int((admitted["boarding"] > 240).sum())}),
        make_metric("lwbs_rate", safe_div(lwbs, total, scale=100), numerator=lwbs,
                    denominator=total, previous=previous.get("lwbs_rate"), overrides=overrides),
        make_metric("lama_rate", safe_div(lama, total, scale=100), numerator=lama,
                    denominator=total, previous=previous.get("lama_rate"), overrides=overrides),
        make_metric("ed_revisit_72h_rate", safe_div(revisits, total, scale=100),
                    numerator=revisits, denominator=total,
                    previous=previous.get("ed_revisit_72h_rate"), overrides=overrides),
        make_metric("admission_rate", safe_div(len(admitted), total, scale=100),
                    numerator=len(admitted), denominator=total,
                    previous=previous.get("admission_rate"), overrides=overrides),
        make_metric("ctas_1_2_share", safe_div(high_acuity, total, scale=100),
                    numerator=high_acuity, denominator=total,
                    previous=previous.get("ctas_1_2_share"), overrides=overrides),
        make_metric("nedocs_score", mean_nedocs, previous=previous.get("nedocs_score"),
                    overrides=overrides,
                    context={"peak": peak_nedocs, "hours_over_100": hours_overcrowded,
                             "hours_measured": int(len(hourly))}),
    ]

    detail = {
        "hourly": [
            {
                "bucket_start": row["bucket_start"].isoformat(),
                "arrivals": int(row["arrivals"]),
                "departures": int(row["departures"]),
                "census": int(row["census"]),
                "boarders": int(row["boarders"]),
                "nedocs_score": float(row["nedocs_score"]),
                "nedocs_band": row["nedocs_band"],
            }
            for _, row in hourly.iterrows()
        ],
        "ctas_distribution": _ctas_distribution(frame),
        "arrival_profile": _arrival_profile(frame),
        "peak_hours": _peak_hours(frame),
        "disposition_mix": _disposition_mix(frame),
    }
    return metrics, detail


def _median_by_ctas(frame: pd.DataFrame, column: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for level in (1, 2, 3, 4, 5):
        subset = frame[frame["ctas_level"] == level]
        out[f"ctas_{level}"] = median_minutes(subset[column]) if len(subset) else None
    return out


def _ctas_distribution(frame: pd.DataFrame) -> dict[str, dict]:
    total = len(frame)
    out = {}
    for level in (1, 2, 3, 4, 5):
        count = int((frame["ctas_level"] == level).sum())
        out[f"ctas_{level}"] = {
            "count": count,
            "share_pct": round(safe_div(count, total, scale=100) or 0, 1),
        }
    unknown = int(frame["ctas_level"].isna().sum())
    out["unrecorded"] = {"count": unknown,
                         "share_pct": round(safe_div(unknown, total, scale=100) or 0, 1)}
    return out


def _arrival_profile(frame: pd.DataFrame) -> list[dict]:
    """Mean arrivals per hour-of-day x day-of-week, the staffing heat map."""
    arrivals = frame["arrival_at"].dropna()
    if arrivals.empty:
        return []
    grouped = (
        pd.DataFrame({
            "weekday": arrivals.dt.dayofweek,
            "hour": arrivals.dt.hour,
            "day": arrivals.dt.date,
        })
        .groupby(["weekday", "hour", "day"]).size().rename("count").reset_index()
        .groupby(["weekday", "hour"])["count"].mean().reset_index()
    )
    return [
        {"weekday": int(row["weekday"]), "hour": int(row["hour"]),
         "mean_arrivals": round(float(row["count"]), 2)}
        for _, row in grouped.iterrows()
    ]


def _peak_hours(frame: pd.DataFrame, top: int = 5) -> list[dict]:
    arrivals = frame["arrival_at"].dropna()
    if arrivals.empty:
        return []
    per_hour = (
        pd.DataFrame({"hour": arrivals.dt.hour, "day": arrivals.dt.date})
        .groupby(["hour", "day"]).size().rename("count").reset_index()
        .groupby("hour")["count"].mean()
        .sort_values(ascending=False).head(top)
    )
    return [{"hour": int(hour), "mean_arrivals": round(float(value), 2)}
            for hour, value in per_hour.items()]


def _disposition_mix(frame: pd.DataFrame) -> list[dict]:
    total = len(frame)
    counts = frame["ed_disposition"].fillna("UNKNOWN").value_counts()
    return [
        {"disposition": str(key), "count": int(value),
         "share_pct": round(safe_div(value, total, scale=100) or 0, 1)}
        for key, value in counts.items()
    ]
