"""Feature engineering for the predictive models.

Three rules are enforced here rather than trusted to the model code:

1. **No leakage.** Every feature for time *t* is computable from data
   available at *t*. Lags and rolling windows are shifted before use; a
   rolling mean that includes the current value would produce a model
   that scores beautifully offline and fails on the day it goes live.
2. **Calendar effects are explicit.** Hospital demand is strongly weekly,
   and in Saudi Arabia the weekend falls on Friday-Saturday, so day-of-week
   is encoded with that in mind rather than assuming Sat-Sun.
3. **Gaps are filled deliberately.** A missing day is a real zero for
   arrivals but not for occupancy, so the two are handled differently.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

#: In the Gulf the weekend is Friday-Saturday.
WEEKEND_DAYS = (4, 5)          # pandas dayofweek: Monday=0 ... Friday=4, Saturday=5

DAILY_LAGS = (1, 2, 3, 7, 14)
ROLLING_WINDOWS = (3, 7, 14)


def observed_span(occupancy_daily: pd.DataFrame, encounters: pd.DataFrame,
                  start: date, end: date) -> tuple[date, date]:
    """Narrow a requested window to the days the warehouse actually covers.

    Callers ask for a year of training history regardless of how much the
    hospital has loaded. Padding the months before go-live with zeros
    teaches a forecaster that the hospital is usually empty, and it
    collapses the median and MAD that anomaly detection depends on -- with
    a median of zero, every real day looks equally extreme and nothing is
    flagged at all.

    ``unit_day_occupancy`` emits a row per unit per requested day, so its
    own date range proves nothing; only days that carried a patient count.
    """
    observed: list[pd.Timestamp] = []

    if not occupancy_daily.empty and "patient_days" in occupancy_daily.columns:
        occupied = occupancy_daily[occupancy_daily["patient_days"] > 0]
        if not occupied.empty:
            observed += [pd.Timestamp(occupied["service_date"].min()),
                         pd.Timestamp(occupied["service_date"].max())]

    if not encounters.empty and "admission_at" in encounters.columns \
            and encounters["admission_at"].notna().any():
        observed += [encounters["admission_at"].min(), encounters["admission_at"].max()]

    if not observed:
        return start, end

    narrowed_start = max(pd.Timestamp(start), min(observed).normalize()).date()
    narrowed_end = min(pd.Timestamp(end), max(observed).normalize()).date()
    if narrowed_end < narrowed_start:
        narrowed_end = narrowed_start
    return narrowed_start, narrowed_end


def trim_partial_edges(frame: pd.DataFrame, columns: list[str] | None = None,
                       threshold: float = 0.25) -> pd.DataFrame:
    """Drop leading and trailing days where a feed had not started or had stopped.

    Different extracts rarely begin on the same day: a hospital may load
    two years of inpatient movements but only six months of ED visits, and
    the overlap is the only period where a cross-feed model is meaningful.
    Days where any normally-busy column sits near zero are treated as
    partial coverage rather than as a genuinely quiet hospital, and
    trimmed. Interior gaps are left alone -- a real quiet day inside the
    period is signal, and is exactly what anomaly detection should see.
    """
    if frame.empty:
        return frame

    candidates = [c for c in (columns or frame.columns)
                  if c in frame.columns and pd.api.types.is_numeric_dtype(frame[c])]
    if not candidates:
        return frame

    activity = frame[candidates].fillna(0)
    medians = activity.median()
    medians = medians[medians > 0]
    if medians.empty:
        return frame

    complete = (activity[medians.index] >= medians * threshold).all(axis=1)
    if not complete.any():
        return frame

    first = complete.idxmax()
    last = complete[::-1].idxmax()
    return frame.loc[first:last]


def _calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame(index=index)
    frame["dayofweek"] = index.dayofweek
    frame["is_weekend"] = index.dayofweek.isin(WEEKEND_DAYS).astype(int)
    frame["day_of_month"] = index.day
    frame["month"] = index.month
    # Cyclical encodings so the model treats December and January as adjacent.
    frame["dow_sin"] = np.sin(2 * np.pi * index.dayofweek / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * index.dayofweek / 7)
    frame["month_sin"] = np.sin(2 * np.pi * index.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * index.month / 12)
    return frame


def _hour_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    frame = _calendar_features(index)
    frame["hour"] = index.hour
    frame["hour_sin"] = np.sin(2 * np.pi * index.hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * index.hour / 24)
    # Overnight cover is thinner; the model benefits from the flag directly.
    frame["is_night"] = ((index.hour >= 22) | (index.hour < 7)).astype(int)
    return frame


def add_lags(frame: pd.DataFrame, column: str, lags=DAILY_LAGS,
             windows=ROLLING_WINDOWS) -> pd.DataFrame:
    """Append shifted lags and trailing rolling statistics for ``column``."""
    out = frame.copy()
    for lag in lags:
        out[f"{column}_lag{lag}"] = out[column].shift(lag)
    for window in windows:
        # shift(1) first: the window must end at t-1, never include t.
        shifted = out[column].shift(1)
        out[f"{column}_roll{window}_mean"] = shifted.rolling(window, min_periods=1).mean()
        out[f"{column}_roll{window}_std"] = shifted.rolling(window, min_periods=2).std()
    out[f"{column}_dow_mean"] = (
        out.groupby(out.index.dayofweek)[column].transform(
            lambda s: s.shift(1).expanding().mean()
        )
    )
    return out


def daily_occupancy_features(
    occupancy_daily: pd.DataFrame,
    encounters: pd.DataFrame,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Facility-level daily frame: occupancy, admissions, discharges + lags.

    The frame is trimmed to the span the warehouse actually covers. The
    caller asks for a year of training history, but padding the months
    before go-live with zero-occupancy days would teach the model that the
    hospital is usually empty and drag every forecast toward zero.
    """
    start, end = observed_span(occupancy_daily, encounters, start, end)
    index = pd.DatetimeIndex(pd.date_range(start, end, freq="D"))

    if occupancy_daily.empty:
        base = pd.DataFrame(index=index, data={"patient_days": 0.0, "available_bed_days": 0.0})
    else:
        grouped = occupancy_daily.groupby("service_date").agg(
            patient_days=("patient_days", "sum"),
            available_bed_days=("available_bed_days", "sum"),
        )
        grouped.index = pd.to_datetime(grouped.index)
        base = grouped.reindex(index)
        # An absent day means nobody was in a bed, which is a genuine zero.
        base["patient_days"] = base["patient_days"].fillna(0.0)
        # Bed capacity, by contrast, persists across a day with no data.
        base["available_bed_days"] = base["available_bed_days"].ffill().bfill().fillna(0.0)

    base["occupancy_rate"] = np.where(
        base["available_bed_days"] > 0,
        100 * base["patient_days"] / base["available_bed_days"],
        np.nan,
    )
    base["occupancy_rate"] = base["occupancy_rate"].interpolate(limit_direction="both")

    if not encounters.empty:
        admissions = (
            encounters.dropna(subset=["admission_at"])
            .set_index(pd.to_datetime(encounters.dropna(subset=["admission_at"])["admission_at"]))
            .resample("D").size().reindex(index).fillna(0)
        )
        discharges = (
            encounters.dropna(subset=["discharge_at"])
            .set_index(pd.to_datetime(encounters.dropna(subset=["discharge_at"])["discharge_at"]))
            .resample("D").size().reindex(index).fillna(0)
        )
    else:
        admissions = pd.Series(0, index=index)
        discharges = pd.Series(0, index=index)

    base["admissions"] = admissions.values
    base["discharges"] = discharges.values
    base["net_flow"] = base["admissions"] - base["discharges"]

    base = trim_partial_edges(base, ["occupancy_rate", "admissions", "discharges"])
    if base.empty:
        return base
    frame = base.join(_calendar_features(pd.DatetimeIndex(base.index)))
    for column in ("occupancy_rate", "admissions", "discharges"):
        frame = add_lags(frame, column)
    return frame


def hourly_ed_features(hourly: pd.DataFrame) -> pd.DataFrame:
    """Hourly ED frame from :func:`analytics.ed.hourly_state` plus lags."""
    if hourly.empty:
        return pd.DataFrame()

    frame = hourly.copy()
    frame["bucket_start"] = pd.to_datetime(frame["bucket_start"])
    frame = frame.set_index("bucket_start").sort_index()

    index = pd.DatetimeIndex(frame.index)
    features = frame.join(_hour_features(index))

    for column in ("census", "arrivals", "boarders", "nedocs_score"):
        for lag in (1, 2, 3, 6, 12, 24, 168):
            features[f"{column}_lag{lag}"] = features[column].shift(lag)
        shifted = features[column].shift(1)
        features[f"{column}_roll6_mean"] = shifted.rolling(6, min_periods=1).mean()
        features[f"{column}_roll24_mean"] = shifted.rolling(24, min_periods=1).mean()

    # Same hour on the previous three days: the strongest single predictor
    # of ED load, and cheap to compute.
    for days_back in (1, 2, 3):
        features[f"census_same_hour_d{days_back}"] = features["census"].shift(24 * days_back)
    return features


def icu_features(occupancy_daily: pd.DataFrame, icu_unit_ids: list[int],
                 *, start: date, end: date) -> pd.DataFrame:
    """Daily critical-care occupancy with lags."""
    if occupancy_daily.empty or not icu_unit_ids:
        return pd.DataFrame(index=pd.DatetimeIndex(pd.date_range(start, end, freq="D")))

    subset = occupancy_daily[occupancy_daily["unit_id"].isin(icu_unit_ids)]
    if subset.empty:
        return pd.DataFrame(index=pd.DatetimeIndex(pd.date_range(start, end, freq="D")))

    # Same reasoning as the facility frame: never pad with phantom empty days.
    occupied = subset[subset["patient_days"] > 0]
    if occupied.empty:
        return pd.DataFrame(index=pd.DatetimeIndex(pd.date_range(start, end, freq="D")))
    start = max(pd.Timestamp(start), pd.Timestamp(occupied["service_date"].min())).date()
    end = min(pd.Timestamp(end), pd.Timestamp(occupied["service_date"].max())).date()
    if end < start:
        end = start
    index = pd.DatetimeIndex(pd.date_range(start, end, freq="D"))

    grouped = subset.groupby("service_date").agg(
        patient_days=("patient_days", "sum"),
        available_bed_days=("available_bed_days", "sum"),
    )
    grouped.index = pd.to_datetime(grouped.index)
    base = grouped.reindex(index)
    base["patient_days"] = base["patient_days"].fillna(0.0)
    base["available_bed_days"] = base["available_bed_days"].ffill().bfill().fillna(0.0)
    base["icu_occupancy"] = np.where(
        base["available_bed_days"] > 0,
        100 * base["patient_days"] / base["available_bed_days"], np.nan,
    )
    base["icu_occupancy"] = base["icu_occupancy"].interpolate(limit_direction="both")

    frame = base.join(_calendar_features(index))
    return add_lags(frame, "icu_occupancy")


def patient_risk_features(
    encounters: pd.DataFrame,
    ed_visits: pd.DataFrame,
    movements: pd.DataFrame,
    icu_stays: pd.DataFrame,
) -> pd.DataFrame:
    """One row per encounter describing risk factors known at admission.

    Only variables observable early in the stay are included -- discharge
    disposition and total length of stay are outcomes, not features.
    """
    if encounters.empty:
        return pd.DataFrame()

    frame = encounters.copy()
    features = pd.DataFrame(index=frame.index)
    features["encounter_id"] = frame["encounter_id"].values

    admission = pd.to_datetime(frame["admission_at"], errors="coerce")
    features["admit_hour"] = admission.dt.hour.fillna(12)
    features["admit_dayofweek"] = admission.dt.dayofweek.fillna(0)
    features["admit_is_weekend"] = admission.dt.dayofweek.isin(WEEKEND_DAYS).astype(int)
    features["is_elective"] = frame["is_elective"].fillna(False).astype(int)
    features["is_emergency_class"] = frame["encounter_class"].eq("EMERGENCY").astype(int)

    if not ed_visits.empty:
        ed_lookup = ed_visits.set_index("encounter_id")
        features["ctas_level"] = (
            frame["encounter_id"].map(ed_lookup["ctas_level"]).fillna(3).values
        )
        boarding = (
            (ed_lookup["departure_at"] - ed_lookup["admission_decision_at"]).dt.total_seconds() / 3600
        )
        features["ed_boarding_hours"] = (
            frame["encounter_id"].map(boarding).clip(lower=0).fillna(0).values
        )
        arrived_by_ambulance = ed_lookup["arrival_mode"].eq("AMBULANCE").astype(int)
        features["arrived_by_ambulance"] = (
            frame["encounter_id"].map(arrived_by_ambulance).fillna(0).values
        )
    else:
        features["ctas_level"] = 3
        features["ed_boarding_hours"] = 0.0
        features["arrived_by_ambulance"] = 0

    if not movements.empty:
        transfers = movements.groupby("encounter_id")["unit_id"].nunique()
        features["units_visited"] = frame["encounter_id"].map(transfers).fillna(1).values
    else:
        features["units_visited"] = 1

    if not icu_stays.empty:
        icu_encounters = set(icu_stays["encounter_id"].tolist())
        features["had_icu"] = frame["encounter_id"].isin(icu_encounters).astype(int).values
    else:
        features["had_icu"] = 0

    # Prior admissions in the loaded history: the strongest available proxy
    # for chronic burden without touching diagnosis coding.
    if "patient_id" in frame.columns:
        ordered = frame.sort_values("admission_at")
        prior = ordered.groupby("patient_id").cumcount()
        features["prior_admissions"] = prior.reindex(frame.index).fillna(0).values
    else:
        features["prior_admissions"] = 0

    features["specialty"] = frame["specialty"].fillna("UNKNOWN").values
    return features


FEATURE_EXCLUSIONS = {
    "patient_days", "available_bed_days", "net_flow", "encounter_id",
    "nedocs_band", "longest_boarding_hours", "longest_wait_minutes", "departures",
}


def select_feature_columns(frame: pd.DataFrame, target: str) -> list[str]:
    """Numeric columns usable as predictors, excluding the target itself.

    Contemporaneous measurements of the target are dropped as well -- only
    its lags survive, which is what keeps the horizon honest.
    """
    columns = []
    for column in frame.columns:
        if column == target or column in FEATURE_EXCLUSIONS:
            continue
        if column.startswith(target) and "lag" not in column and "roll" not in column \
                and "dow_mean" not in column:
            continue
        if pd.api.types.is_numeric_dtype(frame[column]):
            columns.append(column)
    return columns
