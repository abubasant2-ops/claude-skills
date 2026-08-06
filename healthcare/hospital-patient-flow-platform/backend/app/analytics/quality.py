"""Quality and patient-safety indicators.

Two conventions run through this module and matter for how the numbers
are read:

* Harm rates are expressed per 1,000 patient days, not as raw counts, so
  a 40-bed ward and a 12-bed ICU can appear on the same chart.
* Only events flagged as *not* present on admission count as
  hospital-acquired. Mixing the two is the most common way an infection
  or pressure-injury rate ends up indefensible in an accreditation survey.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.analytics.benchmarks import make_metric
from app.analytics.common import MetricValue, safe_div

HAI_KINDS = ("HAI_CLABSI", "HAI_CAUTI", "HAI_VAP", "HAI_SSI")
HARMFUL = ("MODERATE", "SEVERE", "DEATH")


# ---------------------------------------------------------------------
# NEWS2 early warning score
# ---------------------------------------------------------------------
def _news2_component(value, bands: tuple[tuple[float, float, int], ...]) -> int | None:
    if value is None:
        return None
    for low, high, points in bands:
        if low <= value <= high:
            return points
    return None


def news2_score(
    *,
    respiratory_rate: int | None = None,
    spo2: int | None = None,
    on_oxygen: bool | None = None,
    systolic_bp: int | None = None,
    heart_rate: int | None = None,
    temperature_c: float | None = None,
    consciousness: str | None = None,
) -> tuple[int | None, str | None]:
    """Royal College of Physicians NEWS2, SpO2 Scale 1.

    Returns ``(score, band)``. If fewer than four of the seven parameters
    are present the score is withheld rather than under-reported -- a
    partial NEWS2 reads falsely reassuring, which is worse than no score.
    """
    components: list[int] = []

    for value, bands in (
        (respiratory_rate, ((0, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, 999, 3))),
        (spo2, ((0, 91, 3), (92, 93, 2), (94, 95, 1), (96, 100, 0))),
        (systolic_bp, ((0, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, 999, 3))),
        (heart_rate, ((0, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1),
                      (111, 130, 2), (131, 999, 3))),
        (temperature_c, ((0, 35.0, 3), (35.1, 36.0, 1), (36.1, 38.0, 0),
                         (38.1, 39.0, 1), (39.1, 99, 2))),
    ):
        points = _news2_component(value, bands)
        if points is not None:
            components.append(points)

    if on_oxygen is not None:
        components.append(2 if on_oxygen else 0)

    if consciousness:
        components.append(0 if consciousness.upper() == "A" else 3)

    if len(components) < 4:
        return None, None

    total = sum(components)
    if total >= 7:
        band = "HIGH"
    elif total >= 5:
        band = "MEDIUM"
    elif any(point == 3 for point in components):
        # A single parameter scoring 3 escalates the response even when the
        # aggregate is low -- one severely deranged observation matters.
        band = "LOW_MEDIUM"
    else:
        band = "LOW"
    return total, band


# ---------------------------------------------------------------------
# Readmissions
# ---------------------------------------------------------------------
def readmission_rate(encounters: pd.DataFrame, start: date, end: date,
                     *, window_days: int = 30) -> tuple[float | None, int, int]:
    """Unplanned readmissions within ``window_days`` of a live discharge.

    The denominator is index discharges inside the reporting window; the
    numerator looks forward beyond it, which is why the repository loads a
    wider slice than the window itself.
    """
    if encounters.empty:
        return None, 0, 0

    inpatient = encounters[encounters["encounter_class"].isin(["INPATIENT", "OBSERVATION"])]
    if inpatient.empty:
        return None, 0, 0

    lower = pd.Timestamp(start)
    upper = pd.Timestamp(end) + pd.Timedelta(days=1)

    index = inpatient[
        inpatient["discharge_at"].between(lower, upper, inclusive="left")
        & ~inpatient["is_death"].fillna(False).astype(bool)
        & ~inpatient["disposition"].isin(["TRANSFER_OUT", "DECEASED"])
    ]
    if index.empty:
        return None, 0, 0

    # Candidate readmissions: any later unplanned inpatient admission.
    candidates = inpatient[
        inpatient["admission_at"].notna()
        & ~inpatient["is_elective"].fillna(False).astype(bool)
    ][["patient_id", "encounter_id", "admission_at"]]

    merged = index[["patient_id", "encounter_id", "discharge_at"]].merge(
        candidates, on="patient_id", how="left", suffixes=("_index", "_next")
    )
    horizon = timedelta(days=window_days)
    is_readmission = (
        (merged["encounter_id_next"] != merged["encounter_id_index"])
        & (merged["admission_at"] > merged["discharge_at"])
        & (merged["admission_at"] <= merged["discharge_at"] + horizon)
    )
    readmitted = merged[is_readmission]["encounter_id_index"].nunique()
    denominator = len(index)
    return safe_div(readmitted, denominator, scale=100), int(readmitted), int(denominator)


# ---------------------------------------------------------------------
# Headline computation
# ---------------------------------------------------------------------
def compute(
    *,
    safety_events: pd.DataFrame,
    encounters: pd.DataFrame,
    readmission_source: pd.DataFrame,
    experience: pd.DataFrame,
    vitals: pd.DataFrame,
    icu_stays: pd.DataFrame,
    patient_days: float,
    start: date,
    end: date,
    previous: dict[str, float] | None = None,
    overrides: dict[str, dict] | None = None,
) -> tuple[list[MetricValue], dict]:
    previous = previous or {}

    lower = pd.Timestamp(start)
    upper = pd.Timestamp(end) + pd.Timedelta(days=1)
    discharged = encounters[
        encounters["discharge_at"].between(lower, upper, inclusive="left")
    ] if not encounters.empty else encounters
    discharges = len(discharged)
    deaths = int(discharged["is_death"].fillna(False).astype(bool).sum()) if discharges else 0

    events = safety_events.copy() if not safety_events.empty else safety_events
    if not events.empty:
        # Present-on-admission harm is the community's, not the hospital's.
        acquired = events[~events["present_on_admission"].fillna(False).astype(bool)]
    else:
        acquired = events

    def rate_per_1000_days(kinds: tuple[str, ...] | str, *, harmful_only: bool = False,
                           stages: tuple[str, ...] | None = None) -> tuple[float | None, int]:
        if acquired.empty:
            return None, 0
        subset = acquired[acquired["kind"].isin([kinds] if isinstance(kinds, str) else list(kinds))]
        if harmful_only:
            subset = subset[subset["harm"].isin(HARMFUL)]
        if stages:
            subset = subset[subset["pressure_injury_stage"].isin(list(stages))]
        count = int(len(subset))
        return safe_div(count, patient_days, scale=1000), count

    def rate_per_1000_discharges(kind: str) -> tuple[float | None, int]:
        if events.empty:
            return None, 0
        count = int((events["kind"] == kind).sum())
        return safe_div(count, discharges, scale=1000), count

    hai_rate, hai_count = rate_per_1000_days(HAI_KINDS)
    fall_rate, fall_count = rate_per_1000_days("FALL")
    fall_injury_rate, fall_injury_count = rate_per_1000_days("FALL", harmful_only=True)
    pi_rate, pi_count = rate_per_1000_days(
        "PRESSURE_INJURY", stages=("II", "III", "IV", "UNSTAGEABLE", "DTI"))
    med_rate, med_count = rate_per_1000_days("MEDICATION_ERROR")
    code_rate, code_count = rate_per_1000_discharges("CODE_BLUE")
    rrt_rate, rrt_count = rate_per_1000_discharges("RRT_ACTIVATION")

    readmit_rate, readmitted, index_discharges = readmission_rate(readmission_source, start, end)

    satisfaction = nps = None
    if not experience.empty:
        ratings = pd.to_numeric(experience["overall_rating"], errors="coerce").dropna()
        if len(ratings):
            satisfaction = float(ratings.mean()) * 10        # 0-10 scale -> percentage
        recommend = pd.to_numeric(experience["would_recommend"], errors="coerce").dropna()
        if len(recommend):
            promoters = float((recommend >= 9).mean())
            detractors = float((recommend <= 6).mean())
            nps = (promoters - detractors) * 100

    news_high = None
    if not vitals.empty:
        scores = pd.to_numeric(vitals["news2_score"], errors="coerce").dropna()
        if len(scores):
            news_high = float((scores >= 7).mean() * 100)

    icu_mortality = None
    if not icu_stays.empty:
        completed = icu_stays[icu_stays["discharge_at"].notna()]
        if len(completed):
            icu_mortality = safe_div((completed["outcome"] == "DIED").sum(), len(completed),
                                     scale=100)

    metrics = [
        make_metric("mortality_rate", safe_div(deaths, discharges, scale=100),
                    numerator=deaths, denominator=discharges,
                    previous=previous.get("mortality_rate"), overrides=overrides),
        make_metric("icu_mortality_rate", icu_mortality,
                    previous=previous.get("icu_mortality_rate"), overrides=overrides),
        make_metric("readmission_30d_rate", readmit_rate, numerator=readmitted,
                    denominator=index_discharges,
                    previous=previous.get("readmission_30d_rate"), overrides=overrides),
        make_metric("hai_rate", hai_rate, numerator=hai_count, denominator=patient_days,
                    previous=previous.get("hai_rate"), overrides=overrides,
                    context={"by_type": _count_by_kind(acquired, HAI_KINDS)}),
        make_metric("fall_rate", fall_rate, numerator=fall_count, denominator=patient_days,
                    previous=previous.get("fall_rate"), overrides=overrides),
        make_metric("fall_with_injury_rate", fall_injury_rate, numerator=fall_injury_count,
                    denominator=patient_days, previous=previous.get("fall_with_injury_rate"),
                    overrides=overrides),
        make_metric("pressure_injury_rate", pi_rate, numerator=pi_count,
                    denominator=patient_days, previous=previous.get("pressure_injury_rate"),
                    overrides=overrides),
        make_metric("medication_error_rate", med_rate, numerator=med_count,
                    denominator=patient_days, previous=previous.get("medication_error_rate"),
                    overrides=overrides,
                    context={"by_stage": _count_by_stage(acquired)}),
        make_metric("code_blue_rate", code_rate, numerator=code_count, denominator=discharges,
                    previous=previous.get("code_blue_rate"), overrides=overrides),
        make_metric("rrt_activation_rate", rrt_rate, numerator=rrt_count,
                    denominator=discharges, previous=previous.get("rrt_activation_rate"),
                    overrides=overrides,
                    context={"rrt_to_code_ratio": round(safe_div(rrt_count, code_count) or 0, 2)}),
        make_metric("news2_high_rate", news_high, previous=previous.get("news2_high_rate"),
                    overrides=overrides),
        make_metric("patient_satisfaction", satisfaction,
                    denominator=len(experience) or None,
                    previous=previous.get("patient_satisfaction"), overrides=overrides),
        make_metric("net_promoter_score", nps, denominator=len(experience) or None,
                    previous=previous.get("net_promoter_score"), overrides=overrides),
    ]

    detail = {
        "events_by_kind": _count_by_kind(events, None) if not events.empty else {},
        "harm_distribution": (
            events["harm"].value_counts().to_dict() if not events.empty else {}
        ),
        "sentinel_events": int(events["is_sentinel"].fillna(False).astype(bool).sum())
        if not events.empty else 0,
        "unit_safety": _unit_safety(acquired),
        "patient_days": round(patient_days, 1),
        "index_discharges": index_discharges,
    }
    return metrics, detail


def _count_by_kind(events: pd.DataFrame, kinds: tuple[str, ...] | None) -> dict[str, int]:
    if events.empty:
        return {}
    subset = events if kinds is None else events[events["kind"].isin(list(kinds))]
    return {str(k): int(v) for k, v in subset["kind"].value_counts().items()}


def _count_by_stage(events: pd.DataFrame) -> dict[str, int]:
    if events.empty:
        return {}
    subset = events[events["kind"] == "MEDICATION_ERROR"]
    if subset.empty:
        return {}
    return {
        str(k): int(v)
        for k, v in subset["medication_error_stage"].fillna("UNSPECIFIED").value_counts().items()
    }


def _unit_safety(events: pd.DataFrame) -> list[dict]:
    if events.empty or "unit_id" not in events.columns:
        return []
    grouped = events.groupby("unit_id").agg(
        events=("event_id", "count"),
        harmful=("harm", lambda s: int(s.isin(HARMFUL).sum())),
    ).reset_index()
    return [
        {"unit_id": int(row["unit_id"]) if pd.notna(row["unit_id"]) else None,
         "events": int(row["events"]), "harmful_events": int(row["harmful"])}
        for _, row in grouped.iterrows()
    ]
