"""Dashboard assembly.

One :func:`analyse` call loads every frame the period needs, runs all
metric modules once, and caches the result. Role dashboards are then
projections over that single computation -- the CEO and the bed manager
see different tiles, never different numbers for the same indicator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import capacity, ed, journey, nursing, quality, repository
from app.analytics.common import Grain, MetricValue, period_bounds, previous_period, to_period
from app.models import Benchmark, Facility

log = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    facility_id: int
    start: date
    end: date
    metrics: dict[str, MetricValue] = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)

    def metric_dicts(self, keys: list[str] | None = None) -> list[dict]:
        if keys is None:
            return [m.to_dict() for m in self.metrics.values()]
        return [self.metrics[k].to_dict() for k in keys if k in self.metrics]


def _benchmark_overrides(session: Session, facility_id: int) -> dict[str, dict]:
    rows = session.scalars(select(Benchmark).where(Benchmark.scope == "FACILITY")).all()
    return {
        row.metric_key: {
            "target_value": float(row.target_value) if row.target_value is not None else None,
            "amber_threshold": float(row.amber_threshold) if row.amber_threshold is not None else None,
            "red_threshold": float(row.red_threshold) if row.red_threshold is not None else None,
            "higher_is_better": row.higher_is_better,
        }
        for row in rows
    }


def analyse(
    session: Session,
    *,
    facility_id: int,
    start: date,
    end: date,
    include_previous: bool = True,
    unit_ids: list[int] | None = None,
) -> AnalysisResult:
    """Compute every indicator for one facility and window."""
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise ValueError(f"Facility {facility_id} not found")
    if end < start:
        raise ValueError("end date must not precede start date")

    overrides = _benchmark_overrides(session, facility_id)

    units = repository.load_units(session, facility_id)
    if unit_ids:
        units = units[units["unit_id"].isin(unit_ids)]

    encounters = repository.load_encounters(session, facility_id, start, end)
    ed_visits = repository.load_ed_visits(session, facility_id, start, end)
    movements = repository.load_bed_movements(session, facility_id, start, end)
    orders = repository.load_orders(session, facility_id, start, end)
    safety = repository.load_safety_events(session, facility_id, start, end)
    staffing = repository.load_staffing(session, facility_id, start, end)
    icu = repository.load_icu_stays(session, facility_id, start, end)
    or_cases = repository.load_or_cases(session, facility_id, start, end)
    experience = repository.load_experience(session, facility_id, start, end)
    vitals = repository.load_vitals(session, facility_id, start, end)
    readmission_source = repository.load_all_encounters_for_readmission(
        session, facility_id, start, end
    )

    if unit_ids and not movements.empty:
        movements = movements[movements["unit_id"].isin(unit_ids)]
    if unit_ids and not staffing.empty:
        staffing = staffing[staffing["unit_id"].isin(unit_ids)]

    previous_values: dict[str, float] = {}
    if include_previous:
        previous_start, previous_end = previous_period("day", start, end)
        try:
            prior = analyse(session, facility_id=facility_id, start=previous_start,
                            end=previous_end, include_previous=False, unit_ids=unit_ids)
            previous_values = {
                key: metric.value for key, metric in prior.metrics.items()
                if metric.value is not None
            }
        except Exception:                      # a missing prior period must not break the current one
            log.warning("Previous-period comparison unavailable", exc_info=True)

    capacity_metrics, occupancy_daily = capacity.compute(
        movements=movements, encounters=encounters, units=units, icu_stays=icu,
        start=start, end=end, previous=previous_values, overrides=overrides,
    )

    ed_beds = int(facility.ed_treatment_spaces or 0)
    if not ed_beds and not units.empty:
        ed_beds = int(units[units["kind"] == "ED"]["staffed_beds"].sum())
    hospital_beds = int(facility.licensed_beds or 0)
    if not hospital_beds and not units.empty:
        hospital_beds = int(units[~units["kind"].isin(["OPD", "OR", "PACU"])]["staffed_beds"].sum())

    ed_metrics, ed_detail = ed.compute(
        visits=ed_visits, ed_beds=max(ed_beds, 1), hospital_beds=max(hospital_beds, 1),
        start=start, end=end, previous=previous_values, overrides=overrides,
    )

    journey_metrics, journey_detail = journey.compute(
        encounters=encounters, ed_visits=ed_visits, orders=orders, or_cases=or_cases,
        start=start, end=end, previous=previous_values, overrides=overrides,
    )

    patient_days = float(occupancy_daily["patient_days"].sum()) if not occupancy_daily.empty else 0.0
    quality_metrics, quality_detail = quality.compute(
        safety_events=safety, encounters=encounters, readmission_source=readmission_source,
        experience=experience, vitals=vitals, icu_stays=icu, patient_days=patient_days,
        start=start, end=end, previous=previous_values, overrides=overrides,
    )

    # Nursing needs a wider occupancy frame than capacity does: emergency
    # nurses care for real patients and their hours have to be divided by a
    # real denominator, even though ED spaces are not inpatient beds.
    bedded_units = units[~units["kind"].isin(["OPD", "OR", "PACU"])] if not units.empty else units
    occupancy_bedded = capacity.unit_day_occupancy(
        movements[movements["unit_id"].isin(bedded_units["unit_id"])]
        if not movements.empty else movements,
        bedded_units, start, end,
    )
    nursing_metrics, nursing_detail = nursing.compute(
        staffing=staffing, occupancy_daily=occupancy_bedded, start=start, end=end,
        previous=previous_values, overrides=overrides,
    )

    metrics: dict[str, MetricValue] = {}
    # Capacity is applied last for the handful of keys both it and the
    # quality module produce (mortality), so the capacity denominators win.
    for group in (quality_metrics, nursing_metrics, journey_metrics, ed_metrics, capacity_metrics):
        for metric in group:
            if metric.value is not None or metric.key not in metrics:
                metrics[metric.key] = metric

    detail = {
        "capacity": {
            "units": capacity.unit_breakdown(occupancy_daily, encounters, units, start, end),
            "heatmap": capacity.occupancy_heatmap(occupancy_daily),
        },
        "emergency": ed_detail,
        "journey": journey_detail,
        "quality": quality_detail,
        "nursing": nursing_detail,
        "coverage": _coverage(encounters, ed_visits, movements, staffing, safety, orders),
    }

    return AnalysisResult(
        facility_id=facility_id, start=start, end=end, metrics=metrics, detail=detail,
        frames={
            "encounters": encounters, "ed_visits": ed_visits, "movements": movements,
            "occupancy_daily": occupancy_daily, "staffing": staffing, "safety": safety,
            "units": units, "orders": orders,
        },
    )


def _coverage(encounters, ed_visits, movements, staffing, safety, orders) -> dict:
    """What the period actually contains, so an empty chart is explainable."""
    return {
        "encounters": int(len(encounters)),
        "ed_visits": int(len(ed_visits)),
        "bed_movements": int(len(movements)),
        "staffing_rows": int(len(staffing)),
        "safety_events": int(len(safety)),
        "orders": int(len(orders)),
    }


# ---------------------------------------------------------------------
# Trend series
# ---------------------------------------------------------------------
def trend(
    session: Session,
    *,
    facility_id: int,
    metric_keys: list[str],
    start: date,
    end: date,
    grain: Grain = "day",
) -> dict:
    """Metric values bucketed over time for the trend charts.

    Each bucket is a full recomputation rather than a resampling of daily
    values, because ratio metrics do not average correctly: the mean of
    daily occupancy rates is not the period occupancy rate when bed counts
    or open units change mid-period.
    """
    buckets: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        bucket_start, bucket_end = period_bounds(grain, cursor)
        bucket_start = max(bucket_start, start)
        bucket_end = min(bucket_end, end)
        buckets.append((bucket_start, bucket_end))
        cursor = bucket_end + timedelta(days=1)

    series: dict[str, list] = {key: [] for key in metric_keys}
    labels: list[str] = []
    for bucket_start, bucket_end in buckets:
        result = analyse(session, facility_id=facility_id, start=bucket_start,
                         end=bucket_end, include_previous=False)
        labels.append(bucket_start.isoformat())
        for key in metric_keys:
            metric = result.metrics.get(key)
            series[key].append(None if metric is None or metric.value is None
                               else round(metric.value, 2))

    return {"grain": grain, "labels": labels, "series": series}


# ---------------------------------------------------------------------
# Role dashboards
# ---------------------------------------------------------------------
#: Which tiles each command centre leads with. Ordering is deliberate --
#: the first four are what that role is accountable for day to day.
ROLE_TILES: dict[str, list[str]] = {
    "CEO": [
        "occupancy_rate", "alos_days", "mortality_rate", "readmission_30d_rate",
        "patient_satisfaction", "ed_boarding_min", "average_daily_census", "net_promoter_score",
    ],
    "COO": [
        "occupancy_rate", "ed_boarding_min", "discharge_delay_min", "bed_turnover_interval_hours",
        "alos_days", "bed_allocation_min", "or_first_case_delay_min", "discharge_rate",
    ],
    "CNO": [
        "nchpd", "rn_skill_mix", "overtime_rate", "vacancy_rate",
        "fall_rate", "pressure_injury_rate", "turnover_rate", "sick_leave_rate",
    ],
    "ED_DIRECTOR": [
        "nedocs_score", "door_to_physician_min", "ed_los_min", "ed_boarding_min",
        "lwbs_rate", "ed_visits", "admission_rate", "ed_revisit_72h_rate",
    ],
    "QUALITY": [
        "mortality_rate", "readmission_30d_rate", "hai_rate", "fall_with_injury_rate",
        "medication_error_rate", "pressure_injury_rate", "code_blue_rate", "news2_high_rate",
    ],
    "BED_MANAGER": [
        "occupancy_rate", "icu_utilization", "bed_allocation_min", "assignment_to_arrival_min",
        "discharge_delay_min", "bed_turnover_interval_hours", "average_daily_census",
        "transfer_rate",
    ],
}

ROLE_SECTIONS: dict[str, list[str]] = {
    "CEO": ["capacity", "quality", "emergency"],
    "COO": ["capacity", "journey", "emergency"],
    "CNO": ["nursing", "quality", "capacity"],
    "ED_DIRECTOR": ["emergency", "journey"],
    "QUALITY": ["quality", "journey"],
    "BED_MANAGER": ["capacity", "journey"],
}


def dashboard(result: AnalysisResult, role: str) -> dict:
    """Project a completed analysis onto one role's command centre."""
    role = role.upper()
    if role not in ROLE_TILES:
        raise ValueError(f"Unknown role '{role}'. Known roles: {', '.join(sorted(ROLE_TILES))}")

    tiles = result.metric_dicts(ROLE_TILES[role])
    sections = {name: result.detail.get(name, {}) for name in ROLE_SECTIONS[role]}

    return {
        "role": role,
        "facility_id": result.facility_id,
        "period": {"start": result.start.isoformat(), "end": result.end.isoformat()},
        "tiles": tiles,
        "alerts": build_alerts(result),
        "sections": sections,
        "coverage": result.detail.get("coverage", {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_alerts(result: AnalysisResult, *, limit: int = 8) -> list[dict]:
    """Red and amber tiles, worst first, with the reason spelled out."""
    alerts = []
    for metric in result.metrics.values():
        if metric.status not in ("red", "amber") or metric.value is None:
            continue
        direction = "below" if metric.higher_is_better else "above"
        # "%" reads correctly against the number; every other unit needs a
        # space, and a bare "score" adds nothing to "NEDOCS crowding score".
        if metric.unit in ("", "score"):
            suffix = ""
        elif metric.unit == "%":
            suffix = "%"
        else:
            suffix = f" {metric.unit}"

        alerts.append({
            "metric": metric.key,
            "label_en": metric.label_en,
            "label_ar": metric.label_ar,
            "severity": metric.status,
            "value": round(metric.value, 2),
            "target": metric.target,
            "unit": metric.unit,
            "message_en": (
                f"{metric.label_en} is {metric.value:.1f}{suffix}, {direction} the "
                f"target of {metric.target:.1f}{suffix}."
                if metric.target is not None
                else f"{metric.label_en} is outside the expected range."
            ),
        })
    alerts.sort(key=lambda a: (a["severity"] != "red", -abs(a["value"] - (a["target"] or 0))))
    return alerts[:limit]
