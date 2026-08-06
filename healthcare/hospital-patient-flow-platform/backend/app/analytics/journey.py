"""Patient journey analysis: milestone intervals and bottleneck ranking.

The journey is modelled as an ordered set of segments from first contact
to physical discharge. Each segment gets a median duration, a 90th
percentile and a benchmark, and the module then ranks segments by how much
total patient time they waste -- median delay multiplied by volume -- so
leadership sees where an hour of improvement effort buys the most.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.analytics.benchmarks import CATALOGUE, make_metric
from app.analytics.common import (
    MetricValue,
    interval_minutes,
    median_minutes,
    percentile_minutes,
    safe_div,
)

#: (segment key, label EN, label AR, start column, end column, benchmark metric key)
JOURNEY_SEGMENTS = (
    ("registration_to_triage", "Registration to triage", "من التسجيل إلى الفرز",
     "registration_at", "triage_at", "door_to_triage_min"),
    ("triage_to_physician", "Triage to physician", "من الفرز إلى الطبيب",
     "triage_at", "physician_at", "door_to_physician_min"),
    ("physician_to_disposition", "Physician to disposition", "من الطبيب إلى القرار",
     "physician_at", "disposition_at", "door_to_disposition_min"),
    ("decision_to_bed_request", "Decision to bed request", "من القرار إلى طلب السرير",
     "admission_decision_at", "bed_requested_at", None),
    ("bed_request_to_assignment", "Bed request to assignment", "من الطلب إلى التخصيص",
     "bed_requested_at", "bed_assigned_at", "bed_allocation_min"),
    ("assignment_to_ward", "Assignment to ward arrival", "من التخصيص إلى الوصول",
     "bed_assigned_at", "ward_arrival_at", "assignment_to_arrival_min"),
    ("discharge_order_to_ready", "Discharge order to medically ready", "من أمر الخروج إلى الجاهزية",
     "discharge_order_at", "discharge_ready_at", None),
    ("ready_to_departure", "Medically ready to departure", "من الجاهزية إلى المغادرة",
     "discharge_ready_at", "discharge_at", "discharge_delay_min"),
)


def segment_table(encounters: pd.DataFrame, ed_visits: pd.DataFrame) -> pd.DataFrame:
    """One row per encounter with every journey interval in minutes."""
    if encounters.empty:
        return pd.DataFrame()

    frame = encounters.copy()
    if not ed_visits.empty:
        ed_columns = ["encounter_id", "arrival_at", "triage_at", "physician_at",
                      "disposition_at", "departure_at", "ctas_level"]
        frame = frame.merge(ed_visits[ed_columns], on="encounter_id", how="left")
    else:
        for column in ("arrival_at", "triage_at", "physician_at", "disposition_at",
                       "departure_at", "ctas_level"):
            frame[column] = pd.NaT if column != "ctas_level" else None

    # Registration is the first contact; for a walk-in ED patient that is
    # usually the arrival stamp rather than a separate registration event.
    frame["registration_at"] = frame["registration_at"].fillna(frame["arrival_at"])

    for key, _, _, start_col, end_col, _ in JOURNEY_SEGMENTS:
        if start_col in frame.columns and end_col in frame.columns:
            frame[key] = interval_minutes(frame[end_col], frame[start_col])
        else:
            frame[key] = pd.NA

    frame["total_journey_min"] = interval_minutes(
        frame["discharge_at"], frame["registration_at"].fillna(frame["admission_at"])
    )
    return frame


def bottlenecks(segments: pd.DataFrame, *, top: int = 5) -> list[dict]:
    """Rank segments by total avoidable patient-hours above benchmark.

    Ranking on median duration alone points leadership at rare, slow steps.
    Weighting by volume points them at the step where the hospital as a
    whole loses the most time, which is where an intervention pays back.
    """
    if segments.empty:
        return []

    rows = []
    for key, label_en, label_ar, _, _, benchmark_key in JOURNEY_SEGMENTS:
        if key not in segments.columns:
            continue
        values = pd.to_numeric(segments[key], errors="coerce").dropna()
        if values.empty:
            continue

        median = float(values.median())
        target = None
        if benchmark_key and (definition := CATALOGUE.get(benchmark_key)):
            target = definition.target
        excess_per_case = max(median - target, 0.0) if target is not None else 0.0
        wasted_hours = excess_per_case * len(values) / 60

        rows.append({
            "segment": key,
            "label_en": label_en,
            "label_ar": label_ar,
            "cases": int(len(values)),
            "median_min": round(median, 1),
            "p90_min": round(float(values.quantile(0.9)), 1),
            "target_min": target,
            "excess_per_case_min": round(excess_per_case, 1),
            "avoidable_patient_hours": round(wasted_hours, 1),
        })

    rows.sort(key=lambda r: (r["avoidable_patient_hours"], r["median_min"]), reverse=True)
    return rows[:top]


def diagnostic_turnaround(orders: pd.DataFrame) -> dict:
    """Median and p90 turnaround by domain, modality and urgency."""
    if orders.empty:
        return {"lab": {}, "radiology": {}, "consults": {}}

    frame = orders.copy()
    is_lab = frame["domain"] == "LAB"
    # Lab turnaround is measured from collection because the pre-analytic
    # wait belongs to nursing, not to the laboratory.
    frame["tat_min"] = interval_minutes(
        frame["resulted_at"],
        frame["collected_at"].where(is_lab & frame["collected_at"].notna(), frame["ordered_at"]),
    )

    def summarise(subset: pd.DataFrame) -> dict:
        return {
            "count": int(len(subset)),
            "median_min": median_minutes(subset["tat_min"]),
            "p90_min": percentile_minutes(subset["tat_min"], 0.9),
        }

    lab = frame[is_lab]
    radiology = frame[frame["domain"] == "RADIOLOGY"]
    consults = frame[frame["domain"] == "CONSULT"]

    result = {
        "lab": {
            "overall": summarise(lab),
            "stat": summarise(lab[lab["is_stat"].fillna(False).astype(bool)]),
            "routine": summarise(lab[~lab["is_stat"].fillna(False).astype(bool)]),
        },
        "radiology": {
            "overall": summarise(radiology),
            "by_modality": {
                str(modality): summarise(group)
                for modality, group in radiology.groupby(radiology["modality"].fillna("OTHER"))
            },
        },
        "consults": {
            "overall": summarise(consults),
            "by_specialty": {
                str(specialty): summarise(group)
                for specialty, group in consults.groupby(
                    consults["responding_specialty"].fillna("UNSPECIFIED"))
            },
        },
    }
    return result


def or_journey(or_cases: pd.DataFrame) -> dict:
    """Theatre timings: on-time starts, turnover, utilisation and cancellations."""
    if or_cases.empty:
        return {"cases": 0}

    frame = or_cases.copy()
    active = frame[~frame["is_cancelled"].fillna(False).astype(bool)]

    frame["start_delay_min"] = interval_minutes(frame["wheels_in_at"], frame["scheduled_start_at"])
    active = active.assign(
        procedure_min=interval_minutes(active["closure_at"], active["incision_at"]),
        in_room_min=interval_minutes(active["wheels_out_at"], active["wheels_in_at"]),
        pacu_min=interval_minutes(active["pacu_out_at"], active["pacu_in_at"]),
    )

    # Turnover is the gap between consecutive cases in the same theatre on
    # the same day; a gap spanning theatres or days is not turnover.
    turnovers = []
    if "theatre_code" in active.columns:
        ordered = active.dropna(subset=["wheels_in_at", "wheels_out_at"]).sort_values(
            ["theatre_code", "wheels_in_at"]
        )
        for theatre, group in ordered.groupby("theatre_code"):
            previous_out = group["wheels_out_at"].shift()
            same_day = group["wheels_in_at"].dt.date == previous_out.dt.date
            gap = (group["wheels_in_at"] - previous_out).dt.total_seconds() / 60
            turnovers.extend(gap[same_day & (gap >= 0) & (gap < 480)].tolist())

    first_cases = (
        frame.dropna(subset=["scheduled_start_at"])
        .sort_values("scheduled_start_at")
        .groupby([frame["scheduled_start_at"].dt.date, frame["theatre_code"]])
        .first()
    ) if not frame["scheduled_start_at"].isna().all() else pd.DataFrame()

    first_case_delay = (
        median_minutes(first_cases["start_delay_min"]) if not first_cases.empty else None
    )
    on_time_share = None
    if not first_cases.empty:
        delays = pd.to_numeric(first_cases["start_delay_min"], errors="coerce").dropna()
        if len(delays):
            on_time_share = round(float((delays <= 15).mean() * 100), 1)

    cancelled = int(frame["is_cancelled"].fillna(False).astype(bool).sum())
    return {
        "cases": int(len(frame)),
        "performed": int(len(active)),
        "cancelled": cancelled,
        "cancellation_rate_pct": round(safe_div(cancelled, len(frame), scale=100) or 0, 1),
        "median_procedure_min": median_minutes(active["procedure_min"]),
        "median_in_room_min": median_minutes(active["in_room_min"]),
        "median_pacu_min": median_minutes(active["pacu_min"]),
        "median_turnover_min": round(float(pd.Series(turnovers).median()), 1) if turnovers else None,
        "median_first_case_delay_min": first_case_delay,
        "first_case_on_time_pct": on_time_share,
        "cancellation_reasons": (
            frame[frame["is_cancelled"].fillna(False).astype(bool)]["cancellation_reason"]
            .fillna("UNSPECIFIED").value_counts().head(5).to_dict()
        ),
    }


def compute(
    *,
    encounters: pd.DataFrame,
    ed_visits: pd.DataFrame,
    orders: pd.DataFrame,
    or_cases: pd.DataFrame,
    start: date,
    end: date,
    previous: dict[str, float] | None = None,
    overrides: dict[str, dict] | None = None,
) -> tuple[list[MetricValue], dict]:
    previous = previous or {}
    segments = segment_table(encounters, ed_visits)
    turnaround = diagnostic_turnaround(orders)
    theatre = or_journey(or_cases)

    def segment_median(key: str) -> float | None:
        if segments.empty or key not in segments.columns:
            return None
        return median_minutes(segments[key])

    discharge_process = None
    if not segments.empty:
        discharge_process = median_minutes(
            interval_minutes(segments["discharge_at"], segments["discharge_order_at"])
        )

    lab = turnaround.get("lab", {})
    radiology = turnaround.get("radiology", {})
    consults = turnaround.get("consults", {})

    metrics = [
        make_metric("bed_allocation_min", segment_median("bed_request_to_assignment"),
                    previous=previous.get("bed_allocation_min"), overrides=overrides),
        make_metric("assignment_to_arrival_min", segment_median("assignment_to_ward"),
                    previous=previous.get("assignment_to_arrival_min"), overrides=overrides),
        make_metric("discharge_process_min", discharge_process,
                    previous=previous.get("discharge_process_min"), overrides=overrides),
        make_metric("discharge_delay_min", segment_median("ready_to_departure"),
                    previous=previous.get("discharge_delay_min"), overrides=overrides),
        make_metric("lab_tat_min", lab.get("routine", {}).get("median_min"),
                    denominator=lab.get("routine", {}).get("count"),
                    previous=previous.get("lab_tat_min"), overrides=overrides,
                    context={"p90": lab.get("routine", {}).get("p90_min")}),
        make_metric("lab_stat_tat_min", lab.get("stat", {}).get("median_min"),
                    denominator=lab.get("stat", {}).get("count"),
                    previous=previous.get("lab_stat_tat_min"), overrides=overrides,
                    context={"p90": lab.get("stat", {}).get("p90_min")}),
        make_metric("radiology_tat_min", radiology.get("overall", {}).get("median_min"),
                    denominator=radiology.get("overall", {}).get("count"),
                    previous=previous.get("radiology_tat_min"), overrides=overrides,
                    context={"p90": radiology.get("overall", {}).get("p90_min")}),
        make_metric("consult_response_min", consults.get("overall", {}).get("median_min"),
                    denominator=consults.get("overall", {}).get("count"),
                    previous=previous.get("consult_response_min"), overrides=overrides),
        make_metric("or_first_case_delay_min", theatre.get("median_first_case_delay_min"),
                    previous=previous.get("or_first_case_delay_min"), overrides=overrides,
                    context={"on_time_pct": theatre.get("first_case_on_time_pct")}),
        make_metric("or_turnover_min", theatre.get("median_turnover_min"),
                    previous=previous.get("or_turnover_min"), overrides=overrides),
    ]

    detail = {
        "segments": _segment_summary(segments),
        "bottlenecks": bottlenecks(segments),
        "turnaround": turnaround,
        "operating_room": theatre,
        "total_journey": {
            "median_hours": round((median_minutes(segments["total_journey_min"]) or 0) / 60, 2)
            if not segments.empty else None,
            "p90_hours": round((percentile_minutes(segments["total_journey_min"], 0.9) or 0) / 60, 2)
            if not segments.empty else None,
        },
    }
    return metrics, detail


def _segment_summary(segments: pd.DataFrame) -> list[dict]:
    if segments.empty:
        return []
    rows = []
    for key, label_en, label_ar, _, _, benchmark_key in JOURNEY_SEGMENTS:
        if key not in segments.columns:
            continue
        values = pd.to_numeric(segments[key], errors="coerce").dropna()
        definition = CATALOGUE.get(benchmark_key) if benchmark_key else None
        rows.append({
            "segment": key,
            "label_en": label_en,
            "label_ar": label_ar,
            "cases": int(len(values)),
            "median_min": round(float(values.median()), 1) if len(values) else None,
            "p90_min": round(float(values.quantile(0.9)), 1) if len(values) else None,
            "target_min": definition.target if definition else None,
        })
    return rows
