"""Nursing and workforce indicators.

Patient days are taken from the bed-movement trail rather than from
whatever census the roster file happens to carry. Rosters are usually
built on midnight census, which understates the workload of a busy
short-stay unit and makes its nursing hours per patient day look generous.
The reported census is kept as a cross-check and any material disagreement
is surfaced instead of silently reconciled.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.analytics.benchmarks import make_metric
from app.analytics.common import MetricValue, safe_div

#: Hours in a standard nursing shift, used to convert hours into headcount.
SHIFT_HOURS = 12.0


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def compute(
    *,
    staffing: pd.DataFrame,
    occupancy_daily: pd.DataFrame,
    start: date,
    end: date,
    previous: dict[str, float] | None = None,
    overrides: dict[str, dict] | None = None,
) -> tuple[list[MetricValue], dict]:
    previous = previous or {}

    if staffing.empty:
        keys = ("nchpd", "rn_hppd", "rn_skill_mix", "nurse_to_patient_ratio",
                "staffing_utilization", "overtime_rate", "agency_rate", "sick_leave_rate",
                "vacancy_rate", "turnover_rate")
        return [make_metric(k, None, overrides=overrides) for k in keys], {"units": []}

    # Patient days derived from actual bed occupancy, per unit and per day.
    if not occupancy_daily.empty:
        derived = (
            occupancy_daily.groupby(["unit_id", "service_date"])["patient_days"]
            .sum().reset_index().rename(columns={"patient_days": "derived_patient_days"})
        )
        merged = staffing.merge(derived, on=["unit_id", "service_date"], how="left")
    else:
        merged = staffing.copy()
        merged["derived_patient_days"] = pd.NA

    merged["patient_days"] = pd.to_numeric(merged["derived_patient_days"], errors="coerce")
    reported = pd.to_numeric(merged["reported_patient_days"], errors="coerce")
    merged["patient_days"] = merged["patient_days"].fillna(reported)

    rn = _sum(merged, "rn_productive_hours")
    lpn = _sum(merged, "lpn_productive_hours")
    na = _sum(merged, "na_productive_hours")
    non_productive = _sum(merged, "non_productive_hours")
    overtime = _sum(merged, "overtime_hours")
    agency = _sum(merged, "agency_hours")
    sick = _sum(merged, "sick_leave_hours")
    scheduled = _sum(merged, "scheduled_hours")
    productive = rn + lpn + na
    patient_days = float(merged["patient_days"].fillna(0).sum())

    # FTE and headcount are point-in-time stocks, not flows: they are
    # averaged across the days of the period *within* each unit, then summed
    # across units. Averaging across the whole frame instead would divide a
    # hospital-wide separations count by a single unit's headcount and
    # produce a turnover rate several times too high.
    stocks = merged.groupby("unit_id")[["budgeted_fte", "filled_fte", "headcount"]].mean()
    budgeted_fte = float(pd.to_numeric(stocks["budgeted_fte"], errors="coerce").sum())
    filled_fte = float(pd.to_numeric(stocks["filled_fte"], errors="coerce").sum())
    headcount = float(pd.to_numeric(stocks["headcount"], errors="coerce").sum())
    separations = _sum(merged, "separations")

    # Turnover is annualised so a one-month view is comparable to a yearly target.
    days_in_period = max((end - start).days + 1, 1)
    annualisation = 365.0 / days_in_period
    turnover = safe_div(separations * annualisation, headcount, scale=100)

    nchpd = safe_div(productive, patient_days)
    rn_hppd = safe_div(rn, patient_days)
    ratio = safe_div(patient_days * 24, rn)          # mean patients per RN on duty

    metrics = [
        make_metric("nchpd", nchpd, numerator=productive, denominator=patient_days,
                    previous=previous.get("nchpd"), overrides=overrides),
        make_metric("rn_hppd", rn_hppd, numerator=rn, denominator=patient_days,
                    previous=previous.get("rn_hppd"), overrides=overrides),
        make_metric("rn_skill_mix", safe_div(rn, productive, scale=100), numerator=rn,
                    denominator=productive, previous=previous.get("rn_skill_mix"),
                    overrides=overrides),
        make_metric("nurse_to_patient_ratio", ratio, previous=previous.get("nurse_to_patient_ratio"),
                    overrides=overrides,
                    context={"rn_on_duty_estimate": round(safe_div(rn, days_in_period * 24 / SHIFT_HOURS * SHIFT_HOURS) or 0, 1)}),
        make_metric("staffing_utilization",
                    safe_div(productive, productive + non_productive, scale=100),
                    numerator=productive, denominator=productive + non_productive,
                    previous=previous.get("staffing_utilization"), overrides=overrides),
        make_metric("overtime_rate", safe_div(overtime, productive, scale=100),
                    numerator=overtime, denominator=productive,
                    previous=previous.get("overtime_rate"), overrides=overrides),
        make_metric("agency_rate", safe_div(agency, productive, scale=100), numerator=agency,
                    denominator=productive, previous=previous.get("agency_rate"),
                    overrides=overrides),
        make_metric("sick_leave_rate", safe_div(sick, scheduled, scale=100), numerator=sick,
                    denominator=scheduled, previous=previous.get("sick_leave_rate"),
                    overrides=overrides),
        make_metric("vacancy_rate", safe_div(budgeted_fte - filled_fte, budgeted_fte, scale=100),
                    numerator=budgeted_fte - filled_fte, denominator=budgeted_fte,
                    previous=previous.get("vacancy_rate"), overrides=overrides),
        make_metric("turnover_rate", turnover, numerator=separations, denominator=headcount,
                    previous=previous.get("turnover_rate"), overrides=overrides,
                    context={"annualised": True, "period_days": days_in_period}),
    ]

    detail = {
        "units": _unit_rows(merged),
        "census_reconciliation": _reconcile_census(merged),
        "totals": {
            "rn_hours": round(rn, 1),
            "lpn_hours": round(lpn, 1),
            "na_hours": round(na, 1),
            "overtime_hours": round(overtime, 1),
            "agency_hours": round(agency, 1),
            "patient_days": round(patient_days, 1),
        },
    }
    return metrics, detail


def _unit_rows(merged: pd.DataFrame) -> list[dict]:
    grouped = merged.groupby(["unit_id", "unit_name", "unit_kind"], dropna=False).agg(
        rn_hours=("rn_productive_hours", "sum"),
        lpn_hours=("lpn_productive_hours", "sum"),
        na_hours=("na_productive_hours", "sum"),
        overtime_hours=("overtime_hours", "sum"),
        agency_hours=("agency_hours", "sum"),
        sick_hours=("sick_leave_hours", "sum"),
        scheduled_hours=("scheduled_hours", "sum"),
        patient_days=("patient_days", "sum"),
        budgeted_fte=("budgeted_fte", "mean"),
        filled_fte=("filled_fte", "mean"),
    ).reset_index()

    rows = []
    for _, row in grouped.iterrows():
        productive = float(row["rn_hours"] + row["lpn_hours"] + row["na_hours"])
        rows.append({
            "unit_id": int(row["unit_id"]),
            "unit_name": row["unit_name"],
            "unit_kind": row["unit_kind"],
            "patient_days": round(float(row["patient_days"] or 0), 1),
            "nchpd": round(safe_div(productive, row["patient_days"]) or 0, 2),
            "rn_hppd": round(safe_div(row["rn_hours"], row["patient_days"]) or 0, 2),
            "rn_skill_mix": round(safe_div(row["rn_hours"], productive, scale=100) or 0, 1),
            "overtime_rate": round(safe_div(row["overtime_hours"], productive, scale=100) or 0, 1),
            "agency_rate": round(safe_div(row["agency_hours"], productive, scale=100) or 0, 1),
            "sick_leave_rate": round(
                safe_div(row["sick_hours"], row["scheduled_hours"], scale=100) or 0, 1),
            "vacancy_rate": round(
                safe_div((row["budgeted_fte"] or 0) - (row["filled_fte"] or 0),
                         row["budgeted_fte"], scale=100) or 0, 1),
        })
    return sorted(rows, key=lambda r: r["nchpd"])


def _reconcile_census(merged: pd.DataFrame) -> dict:
    """Flag units where the roster's census and the ADT trail disagree.

    A persistent gap means one of the two feeds is wrong, and every nursing
    indicator for that unit inherits the error -- worth showing rather than
    quietly preferring one source.
    """
    if "reported_patient_days" not in merged.columns:
        return {"checked": 0, "divergent_units": []}

    comparable = merged.dropna(subset=["reported_patient_days", "derived_patient_days"])
    if comparable.empty:
        return {"checked": 0, "divergent_units": []}

    grouped = comparable.groupby(["unit_id", "unit_name"]).agg(
        reported=("reported_patient_days", "sum"),
        derived=("derived_patient_days", "sum"),
    ).reset_index()
    grouped["gap_pct"] = 100 * (grouped["reported"] - grouped["derived"]) / grouped["derived"].replace(0, pd.NA)

    divergent = grouped[grouped["gap_pct"].abs() > 10]
    return {
        "checked": int(len(grouped)),
        "divergent_units": [
            {"unit_id": int(row["unit_id"]), "unit_name": row["unit_name"],
             "reported_patient_days": round(float(row["reported"]), 1),
             "derived_patient_days": round(float(row["derived"]), 1),
             "gap_pct": round(float(row["gap_pct"]), 1)}
            for _, row in divergent.iterrows()
        ],
    }
