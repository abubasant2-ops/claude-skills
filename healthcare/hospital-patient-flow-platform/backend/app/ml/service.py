"""Prediction orchestration: train on demand, persist, and serve.

Models are trained from the warehouse rather than shipped pre-trained.
A bed-occupancy model fitted on one hospital transfers badly to another --
case mix, bed counts and discharge culture all differ -- so each facility
learns its own, and the training run is cheap enough to do on demand.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import capacity, ed, repository
from app.ml import models as ml
from app.models import Anomaly, Facility, MlModel, Prediction, Unit

log = logging.getLogger(__name__)

#: How much history to pull when training. Roughly a year captures the
#: seasonal pattern without making the fit slow.
TRAIN_LOOKBACK_DAYS = 365


def _training_window(end: date, lookback: int = TRAIN_LOOKBACK_DAYS) -> tuple[date, date]:
    return end - timedelta(days=lookback), end


def _load_training_frames(session: Session, facility_id: int, start: date, end: date) -> dict:
    units = repository.load_units(session, facility_id)
    encounters = repository.load_encounters(session, facility_id, start, end)
    movements = repository.load_bed_movements(session, facility_id, start, end)
    ed_visits = repository.load_ed_visits(session, facility_id, start, end)
    icu_stays = repository.load_icu_stays(session, facility_id, start, end)

    inpatient_units = units[~units["kind"].isin(["OPD", "OR", "PACU"])] if not units.empty else units
    occupancy_daily = capacity.unit_day_occupancy(
        movements[movements["unit_id"].isin(inpatient_units["unit_id"])]
        if not movements.empty else movements,
        inpatient_units, start, end,
    )
    return {
        "units": units,
        "encounters": encounters,
        "movements": movements,
        "ed_visits": ed_visits,
        "icu_stays": icu_stays,
        "occupancy_daily": occupancy_daily,
    }


def _register_model(session: Session, result: ml.ModelResult) -> MlModel | None:
    """Record a training run so predictions can be traced to a model version."""
    if not result.is_fitted:
        return None
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    record = MlModel(
        model_key=result.model_key,
        version=version,
        algorithm=result.algorithm,
        training_rows=result.training_rows,
        feature_names=result.feature_names,
        metrics=result.metrics,
        is_active=True,
    )
    # Only the newest version of a model key stays active.
    for previous in session.scalars(
        select(MlModel).where(MlModel.model_key == result.model_key, MlModel.is_active.is_(True))
    ):
        previous.is_active = False
    session.add(record)
    session.flush()
    return record


def predict_all(
    session: Session,
    *,
    facility_id: int,
    as_of: date | None = None,
    horizon_days: int = 14,
    persist: bool = True,
) -> dict:
    """Run every predictive model and return one combined payload."""
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise ValueError(f"Facility {facility_id} not found")

    as_of = as_of or date.today()
    start, end = _training_window(as_of)
    frames = _load_training_frames(session, facility_id, start, end)

    occupancy_forecast = ml.forecast_occupancy(
        frames["occupancy_daily"], frames["encounters"],
        start=start, end=end, horizon_days=horizon_days,
    )
    discharge_forecast = ml.forecast_discharges(
        frames["occupancy_daily"], frames["encounters"],
        start=start, end=end, horizon_days=min(horizon_days, 7),
    )

    units = frames["units"]
    icu_unit_ids = (
        units[units["kind"].isin(capacity.CRITICAL_CARE_KINDS)]["unit_id"].tolist()
        if not units.empty else []
    )
    icu_forecast = ml.forecast_icu(
        frames["occupancy_daily"], icu_unit_ids, start=start, end=end, horizon_days=horizon_days
    )

    # ED crowding needs the hourly reconstruction, which is expensive over a
    # year, so it trains on the most recent 60 days.
    crowding_start = max(start, as_of - timedelta(days=60))
    ed_beds = int(facility.ed_treatment_spaces or 0) or 30
    hospital_beds = int(facility.licensed_beds or 0) or 300
    ed_visits_recent = repository.load_ed_visits(session, facility_id, crowding_start, as_of)
    hourly = ed.hourly_state(ed_visits_recent, crowding_start, as_of,
                             ed_beds=ed_beds, hospital_beds=hospital_beds)

    crowding_model = ml.train_ed_crowding(hourly)
    crowding = ml.predict_ed_crowding(crowding_model, hourly)

    risk_model = ml.train_patient_risk(
        frames["encounters"], frames["ed_visits"], frames["movements"], frames["icu_stays"]
    )
    high_risk = ml.score_patients(
        risk_model, frames["encounters"], frames["ed_visits"],
        frames["movements"], frames["icu_stays"],
    )

    anomalies = ml.detect_anomalies(_daily_kpi_matrix(frames, start, end))
    bottlenecks = ml.anticipate_bottlenecks(occupancy_forecast, icu_forecast, discharge_forecast)

    if persist:
        _persist(session, facility_id, occupancy_forecast, discharge_forecast, icu_forecast,
                 crowding_model, risk_model, anomalies)

    return {
        "facility_id": facility_id,
        "as_of": as_of.isoformat(),
        "horizon_days": horizon_days,
        "occupancy_forecast": occupancy_forecast.to_dict(),
        "discharge_forecast": discharge_forecast.to_dict(),
        "icu_forecast": icu_forecast.to_dict(),
        "ed_crowding": crowding,
        "high_risk_patients": high_risk,
        "risk_model": risk_model.to_dict(),
        "anomalies": anomalies,
        "bottleneck_warnings": bottlenecks,
        "training_window": {"start": start.isoformat(), "end": end.isoformat()},
    }


def _daily_kpi_matrix(frames: dict, start: date, end: date) -> pd.DataFrame:
    """Daily matrix of headline indicators, the input to anomaly detection."""
    from app.ml.features import observed_span, trim_partial_edges

    start, end = observed_span(frames["occupancy_daily"], frames["encounters"], start, end)
    index = pd.DatetimeIndex(pd.date_range(start, end, freq="D"))
    matrix = pd.DataFrame(index=index)

    occupancy = frames["occupancy_daily"]
    if not occupancy.empty:
        grouped = occupancy.groupby("service_date").agg(
            patient_days=("patient_days", "sum"),
            available_bed_days=("available_bed_days", "sum"),
        )
        grouped.index = pd.to_datetime(grouped.index)
        grouped = grouped.reindex(index)
        matrix["occupancy_rate"] = 100 * grouped["patient_days"] / grouped["available_bed_days"]
        matrix["census"] = grouped["patient_days"]

    encounters = frames["encounters"]
    if not encounters.empty:
        admissions = encounters.dropna(subset=["admission_at"])
        discharges = encounters.dropna(subset=["discharge_at"])
        matrix["admissions"] = (
            admissions.set_index(pd.to_datetime(admissions["admission_at"]))
            .resample("D").size().reindex(index).fillna(0)
        )
        matrix["discharges"] = (
            discharges.set_index(pd.to_datetime(discharges["discharge_at"]))
            .resample("D").size().reindex(index).fillna(0)
        )
        deaths = discharges[discharges["is_death"].fillna(False).astype(bool)]
        matrix["deaths"] = (
            deaths.set_index(pd.to_datetime(deaths["discharge_at"]))
            .resample("D").size().reindex(index).fillna(0)
            if not deaths.empty else 0
        )

    ed_visits = frames["ed_visits"]
    if not ed_visits.empty:
        arrivals = ed_visits.dropna(subset=["arrival_at"])
        matrix["ed_arrivals"] = (
            arrivals.set_index(pd.to_datetime(arrivals["arrival_at"]))
            .resample("D").size().reindex(index).fillna(0)
        )
        lwbs = arrivals[arrivals["is_lwbs"].fillna(False).astype(bool)]
        matrix["ed_lwbs"] = (
            lwbs.set_index(pd.to_datetime(lwbs["arrival_at"]))
            .resample("D").size().reindex(index).fillna(0)
            if not lwbs.empty else 0
        )

    matrix = matrix.dropna(how="all")
    # Ramp-up days at the edge of the loaded history are a data artefact,
    # not an operational anomaly. Leaving them in means the detector spends
    # its whole contamination budget on them and never reaches the real
    # surge in the middle of the period.
    return trim_partial_edges(matrix, ["census", "admissions", "discharges", "ed_arrivals"])


def _persist(session: Session, facility_id: int, occupancy, discharges, icu,
             crowding_model, risk_model, anomalies) -> None:
    """Store forecasts and anomalies so accuracy can be reviewed later."""
    registered: dict[str, MlModel] = {}
    for key, algorithm, metrics in (
        ("bed_occupancy", occupancy.model.get("algorithm", "unknown"), occupancy.model),
        ("discharge_demand", discharges.model.get("algorithm", "unknown"), discharges.model),
        ("icu_utilization", icu.model.get("algorithm", "unknown"), icu.model),
    ):
        record = MlModel(
            model_key=key,
            version=datetime.now().strftime("%Y%m%d%H%M%S") + f"-{key}",
            algorithm=algorithm,
            training_rows=metrics.get("training_rows"),
            metrics={k: v for k, v in metrics.items() if k != "algorithm"},
            is_active=True,
        )
        session.add(record)
        session.flush()
        registered[key] = record

    for model_result in (crowding_model, risk_model):
        _register_model(session, model_result)

    for key, forecast in (("bed_occupancy", occupancy), ("discharge_demand", discharges),
                          ("icu_utilization", icu)):
        record = registered[key]
        for point in forecast.points:
            session.add(Prediction(
                model_id=record.model_id,
                facility_id=facility_id,
                target_key=forecast.target_key,
                horizon_at=datetime.fromisoformat(point["date"]),
                predicted_value=point["predicted"],
                lower_bound=point["lower"],
                upper_bound=point["upper"],
                drivers={"horizon_days": point["horizon_days"]},
            ))

    for anomaly in anomalies:
        session.add(Anomaly(
            facility_id=facility_id,
            service_date=datetime.fromisoformat(anomaly["service_date"]).date(),
            metric_key=anomaly["drivers"][0]["metric"] if anomaly["drivers"] else "composite",
            observed_value=anomaly["drivers"][0]["observed"] if anomaly["drivers"] else None,
            expected_value=anomaly["drivers"][0]["typical"] if anomaly["drivers"] else None,
            deviation_score=anomaly["anomaly_score"],
            severity=anomaly["severity"],
            explanation_en=anomaly["explanation_en"],
        ))
    session.flush()


def backfill_actuals(session: Session, facility_id: int) -> int:
    """Fill in what actually happened against past forecasts.

    Without this the platform can promise accuracy but never demonstrate
    it. Populating ``actual_value`` is what makes the model-performance
    page real rather than decorative.
    """
    predictions = session.scalars(
        select(Prediction).where(
            Prediction.facility_id == facility_id,
            Prediction.actual_value.is_(None),
            Prediction.horizon_at < datetime.now(),
        )
    ).all()
    if not predictions:
        return 0

    horizons = [p.horizon_at.date() for p in predictions]
    start, end = min(horizons), max(horizons)
    frames = _load_training_frames(session, facility_id, start, end)

    occupancy = frames["occupancy_daily"]
    actual_occupancy: dict[date, float] = {}
    if not occupancy.empty:
        grouped = occupancy.groupby("service_date").agg(
            patient_days=("patient_days", "sum"),
            available_bed_days=("available_bed_days", "sum"),
        )
        for service_date, row in grouped.iterrows():
            if row["available_bed_days"]:
                actual_occupancy[service_date] = 100 * row["patient_days"] / row["available_bed_days"]

    encounters = frames["encounters"]
    actual_discharges: dict[date, int] = {}
    if not encounters.empty:
        discharged = encounters.dropna(subset=["discharge_at"])
        counts = discharged.groupby(discharged["discharge_at"].dt.date).size()
        actual_discharges = counts.to_dict()

    updated = 0
    for prediction in predictions:
        target_date = prediction.horizon_at.date()
        if prediction.target_key == "occupancy_rate" and target_date in actual_occupancy:
            prediction.actual_value = round(actual_occupancy[target_date], 2)
            updated += 1
        elif prediction.target_key == "discharge_demand" and target_date in actual_discharges:
            prediction.actual_value = float(actual_discharges[target_date])
            updated += 1
    session.flush()
    return updated
