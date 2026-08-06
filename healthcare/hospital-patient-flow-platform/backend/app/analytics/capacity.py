"""Hospital capacity metrics.

Occupancy is computed from the bed-movement trail rather than from a
midnight census, so a unit that admits and discharges eight day-cases into
one bed shows the utilisation it actually delivered.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from app.analytics.benchmarks import make_metric
from app.analytics.common import MetricValue, expand_to_days, safe_div

CRITICAL_CARE_KINDS = ("ICU", "NICU", "HDU")


def unit_day_occupancy(
    movements: pd.DataFrame,
    units: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Per unit, per day: patient days, staffed bed days and occupancy."""
    if units.empty:
        return pd.DataFrame(columns=["unit_id", "service_date", "patient_days",
                                     "available_bed_days", "occupancy_rate", "patients"])

    daily = expand_to_days(
        movements, start_col="in_at", end_col="out_at", group_cols=["unit_id"],
        window_start=start, window_end=end,
    )

    # Every active unit gets a row for every day, so a unit that emptied out
    # reports 0% rather than dropping off the chart entirely.
    calendar = pd.MultiIndex.from_product(
        [units["unit_id"].tolist(), pd.date_range(start, end, freq="D").date],
        names=["unit_id", "service_date"],
    ).to_frame(index=False)

    frame = calendar.merge(daily, on=["unit_id", "service_date"], how="left")
    frame["patient_days"] = frame["patient_days"].fillna(0.0)
    frame["patients"] = frame["patients"].fillna(0).astype(int)

    frame = frame.merge(
        units[["unit_id", "code", "name_en", "name_ar", "kind", "staffed_beds"]],
        on="unit_id", how="left",
    )
    frame["available_bed_days"] = pd.to_numeric(frame["staffed_beds"], errors="coerce").fillna(0.0)
    frame["occupancy_rate"] = np.where(
        frame["available_bed_days"] > 0,
        100.0 * frame["patient_days"] / frame["available_bed_days"],
        np.nan,
    )
    return frame


def midnight_census(movements: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Classic midnight census, kept because regulators still ask for it."""
    if movements.empty:
        return pd.DataFrame(columns=["unit_id", "service_date", "midnight_census"])

    frame = movements.copy()
    frame["in_at"] = pd.to_datetime(frame["in_at"], errors="coerce")
    frame["out_at"] = pd.to_datetime(frame["out_at"], errors="coerce")

    rows = []
    for day in pd.date_range(start, end, freq="D"):
        midnight = day + pd.Timedelta(hours=23, minutes=59)
        occupied = frame[
            (frame["in_at"] <= midnight)
            & (frame["out_at"].isna() | (frame["out_at"] > midnight))
        ]
        counts = occupied.groupby("unit_id")["encounter_id"].nunique()
        for unit_id, count in counts.items():
            rows.append({"unit_id": unit_id, "service_date": day.date(),
                         "midnight_census": int(count)})
    return pd.DataFrame(rows, columns=["unit_id", "service_date", "midnight_census"])


def flow_counts(encounters: pd.DataFrame, start: date, end: date) -> dict[str, int]:
    """Admissions, discharges, deaths and transfers inside the window."""
    if encounters.empty:
        return {"admissions": 0, "discharges": 0, "deaths": 0}

    lower = pd.Timestamp(start)
    upper = pd.Timestamp(end) + pd.Timedelta(days=1)

    inpatient = encounters[encounters["encounter_class"].isin(["INPATIENT", "OBSERVATION"])]
    admitted = inpatient["admission_at"].between(lower, upper, inclusive="left")
    discharged = inpatient["discharge_at"].between(lower, upper, inclusive="left")

    return {
        "admissions": int(admitted.sum()),
        "discharges": int(discharged.sum()),
        "deaths": int((discharged & inpatient["is_death"].fillna(False).astype(bool)).sum()),
    }


def compute(
    *,
    movements: pd.DataFrame,
    encounters: pd.DataFrame,
    units: pd.DataFrame,
    icu_stays: pd.DataFrame,
    start: date,
    end: date,
    previous: dict[str, float] | None = None,
    overrides: dict[str, dict] | None = None,
    unit_kinds: tuple[str, ...] | None = None,
) -> tuple[list[MetricValue], pd.DataFrame]:
    """Capacity headline metrics plus the per-unit/day detail frame."""
    previous = previous or {}

    scope_units = units
    if unit_kinds:
        scope_units = units[units["kind"].isin(unit_kinds)]
    # Inpatient occupancy counts only beds a patient can be admitted into.
    # Outpatient clinics and theatres have no beds to occupy, and ED
    # treatment spaces are not inpatient capacity -- including the ED's 45
    # spaces in the denominator would understate ward occupancy by roughly
    # ten points. ED load is reported by the emergency module instead.
    inpatient_units = scope_units[~scope_units["kind"].isin(["OPD", "OR", "PACU", "ED"])]

    daily = unit_day_occupancy(
        movements[movements["unit_id"].isin(inpatient_units["unit_id"])] if not movements.empty
        else movements,
        inpatient_units, start, end,
    )

    days_in_period = (end - start).days + 1
    total_patient_days = float(daily["patient_days"].sum()) if not daily.empty else 0.0
    total_bed_days = float(daily["available_bed_days"].sum()) if not daily.empty else 0.0

    counts = flow_counts(encounters, start, end)
    discharges = counts["discharges"]

    # ALOS uses only stays that both started and finished as inpatient
    # episodes; still-admitted patients have no length of stay yet.
    completed = encounters[
        encounters["encounter_class"].isin(["INPATIENT", "OBSERVATION"])
        & encounters["discharge_at"].between(
            pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1), inclusive="left")
        & encounters["admission_at"].notna()
    ]
    los_days = (
        (completed["discharge_at"] - completed["admission_at"]).dt.total_seconds() / 86400
    ) if not completed.empty else pd.Series(dtype=float)
    los_days = los_days[los_days >= 0]

    staffed_beds = float(pd.to_numeric(inpatient_units["staffed_beds"], errors="coerce").fillna(0).sum())

    occupancy = safe_div(total_patient_days, total_bed_days, scale=100)
    adc = safe_div(total_patient_days, days_in_period)
    alos = float(los_days.mean()) if len(los_days) else None
    turnover_rate = safe_div(discharges, staffed_beds)
    # Idle bed-hours per discharge. Negative means the unit exceeded staffed beds.
    turnover_interval = safe_div((total_bed_days - total_patient_days) * 24, discharges)

    transfer_share = None
    if not movements.empty and counts["admissions"]:
        per_encounter = movements.groupby("encounter_id")["unit_id"].nunique()
        transferred = int((per_encounter > 1).sum())
        transfer_share = safe_div(transferred, len(per_encounter), scale=100)

    icu_units = units[units["kind"].isin(CRITICAL_CARE_KINDS)]
    icu_occupancy = None
    if not icu_units.empty and not daily.empty:
        icu_daily = daily[daily["unit_id"].isin(icu_units["unit_id"])]
        icu_occupancy = safe_div(
            icu_daily["patient_days"].sum(), icu_daily["available_bed_days"].sum(), scale=100
        )

    icu_mortality = None
    if not icu_stays.empty:
        completed_icu = icu_stays[icu_stays["discharge_at"].notna()]
        if len(completed_icu):
            icu_mortality = safe_div(
                (completed_icu["outcome"] == "DIED").sum(), len(completed_icu), scale=100
            )

    metrics = [
        make_metric("occupancy_rate", occupancy, numerator=total_patient_days,
                    denominator=total_bed_days, previous=previous.get("occupancy_rate"),
                    overrides=overrides,
                    context={"staffed_beds": staffed_beds, "days": days_in_period}),
        make_metric("average_daily_census", adc, numerator=total_patient_days,
                    denominator=days_in_period, previous=previous.get("average_daily_census"),
                    overrides=overrides),
        make_metric("alos_days", alos, numerator=float(los_days.sum()) if len(los_days) else None,
                    denominator=len(los_days) or None, previous=previous.get("alos_days"),
                    overrides=overrides,
                    context={"median_los_days": round(float(los_days.median()), 2)
                             if len(los_days) else None}),
        make_metric("bed_turnover_rate", turnover_rate, numerator=discharges,
                    denominator=staffed_beds, previous=previous.get("bed_turnover_rate"),
                    overrides=overrides),
        make_metric("bed_turnover_interval_hours", turnover_interval,
                    numerator=(total_bed_days - total_patient_days) * 24, denominator=discharges,
                    previous=previous.get("bed_turnover_interval_hours"), overrides=overrides),
        make_metric("discharge_rate", safe_div(discharges, days_in_period),
                    numerator=discharges, denominator=days_in_period,
                    previous=previous.get("discharge_rate"), overrides=overrides),
        make_metric("transfer_rate", transfer_share, previous=previous.get("transfer_rate"),
                    overrides=overrides),
        make_metric("mortality_rate", safe_div(counts["deaths"], discharges, scale=100),
                    numerator=counts["deaths"], denominator=discharges,
                    previous=previous.get("mortality_rate"), overrides=overrides),
        make_metric("icu_utilization", icu_occupancy, previous=previous.get("icu_utilization"),
                    overrides=overrides),
        make_metric("icu_mortality_rate", icu_mortality,
                    previous=previous.get("icu_mortality_rate"), overrides=overrides),
    ]
    return metrics, daily


def unit_breakdown(daily: pd.DataFrame, encounters: pd.DataFrame,
                   units: pd.DataFrame, start: date, end: date) -> list[dict]:
    """Per-unit rows for the bed-management drill-down table."""
    if daily.empty:
        return []

    grouped = daily.groupby(["unit_id", "code", "name_en", "name_ar", "kind"], dropna=False).agg(
        patient_days=("patient_days", "sum"),
        available_bed_days=("available_bed_days", "sum"),
        peak_patients=("patients", "max"),
    ).reset_index()

    discharges = (
        encounters[encounters["discharge_at"].notna()]
        .groupby("discharge_unit_id").size().rename("discharges")
    ) if not encounters.empty else pd.Series(dtype=int, name="discharges")

    los = (
        encounters.assign(
            los_days=(encounters["discharge_at"] - encounters["admission_at"]).dt.total_seconds() / 86400
        )
        .query("los_days >= 0")
        .groupby("discharge_unit_id")["los_days"].mean().rename("alos_days")
    ) if not encounters.empty else pd.Series(dtype=float, name="alos_days")

    grouped = grouped.merge(discharges, left_on="unit_id", right_index=True, how="left")
    grouped = grouped.merge(los, left_on="unit_id", right_index=True, how="left")
    grouped["discharges"] = grouped["discharges"].fillna(0).astype(int)

    days_in_period = (end - start).days + 1
    rows = []
    for _, row in grouped.iterrows():
        staffed = safe_div(row["available_bed_days"], days_in_period) or 0
        rows.append({
            "unit_id": int(row["unit_id"]),
            "unit_code": row["code"],
            "unit_name_en": row["name_en"],
            "unit_name_ar": row["name_ar"],
            "unit_kind": row["kind"],
            "staffed_beds": round(staffed, 1),
            "patient_days": round(float(row["patient_days"]), 1),
            "occupancy_rate": round(
                safe_div(row["patient_days"], row["available_bed_days"], scale=100) or 0, 1),
            "average_daily_census": round(safe_div(row["patient_days"], days_in_period) or 0, 1),
            "peak_census": int(row["peak_patients"]),
            "discharges": int(row["discharges"]),
            "alos_days": round(float(row["alos_days"]), 2) if pd.notna(row["alos_days"]) else None,
            "bed_turnover_rate": round(safe_div(row["discharges"], staffed) or 0, 2),
        })
    return sorted(rows, key=lambda r: r["occupancy_rate"], reverse=True)


def occupancy_heatmap(daily: pd.DataFrame) -> dict:
    """Unit x day occupancy matrix for the command-centre heat map."""
    if daily.empty:
        return {"units": [], "dates": [], "values": []}

    pivot = daily.pivot_table(
        index="name_en", columns="service_date", values="occupancy_rate", aggfunc="mean"
    ).sort_index()
    return {
        "units": [str(u) for u in pivot.index.tolist()],
        "dates": [d.isoformat() for d in pivot.columns.tolist()],
        "values": [[None if pd.isna(v) else round(float(v), 1) for v in row]
                   for row in pivot.to_numpy()],
    }
