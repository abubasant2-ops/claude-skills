"""Predictive analytics endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.ml import service as ml_service
from app.models import Anomaly, MlModel, Prediction

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])


@router.get("", summary="All forecasts, risk scores and anomaly flags")
def predictions(
    facility_id: int = Query(1),
    as_of: date | None = Query(None),
    horizon_days: int = Query(14, ge=1, le=60),
    persist: bool = Query(False, description="Store the run for later accuracy review"),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return ml_service.predict_all(
            session, facility_id=facility_id, as_of=as_of,
            horizon_days=horizon_days, persist=persist,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/occupancy", summary="Bed occupancy forecast only")
def occupancy_forecast(
    facility_id: int = Query(1),
    horizon_days: int = Query(14, ge=1, le=60),
    session: Session = Depends(get_session),
) -> dict:
    payload = ml_service.predict_all(
        session, facility_id=facility_id, horizon_days=horizon_days, persist=False
    )
    return {
        "occupancy": payload["occupancy_forecast"],
        "icu": payload["icu_forecast"],
        "discharges": payload["discharge_forecast"],
        "warnings": payload["bottleneck_warnings"],
    }


@router.get("/ed-crowding", summary="Short-horizon ED overcrowding risk")
def ed_crowding(
    facility_id: int = Query(1),
    session: Session = Depends(get_session),
) -> dict:
    payload = ml_service.predict_all(session, facility_id=facility_id, persist=False)
    return payload["ed_crowding"]


@router.get("/high-risk-patients", summary="Currently-admitted patients ranked by risk")
def high_risk(
    facility_id: int = Query(1),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    payload = ml_service.predict_all(session, facility_id=facility_id, persist=False)
    return {
        "model": payload["risk_model"],
        "patients": payload["high_risk_patients"][:limit],
        "disclaimer": (
            "Operational prioritisation aid for the patient-flow team. Not a clinical "
            "decision support tool and not validated for individual treatment decisions."
        ),
    }


@router.get("/anomalies", summary="Stored anomaly detections")
def anomalies(
    facility_id: int = Query(1),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.scalars(
        select(Anomaly).where(Anomaly.facility_id == facility_id)
        .order_by(desc(Anomaly.service_date)).limit(limit)
    ).all()
    return {
        "anomalies": [
            {
                "service_date": a.service_date.isoformat(),
                "metric_key": a.metric_key,
                "observed": a.observed_value,
                "expected": a.expected_value,
                "deviation_score": a.deviation_score,
                "severity": a.severity,
                "explanation_en": a.explanation_en,
                "explanation_ar": a.explanation_ar,
            }
            for a in rows
        ]
    }


@router.get("/accuracy", summary="Forecast accuracy against realised values")
def accuracy(
    facility_id: int = Query(1),
    session: Session = Depends(get_session),
) -> dict:
    """Realised error for past forecasts.

    Reported per target so a reader can see which forecasts have earned
    trust and which have not, rather than a single flattering headline.
    """
    updated = ml_service.backfill_actuals(session, facility_id)

    rows = session.scalars(
        select(Prediction).where(
            Prediction.facility_id == facility_id,
            Prediction.actual_value.is_not(None),
        ).order_by(desc(Prediction.horizon_at)).limit(2000)
    ).all()

    by_target: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        if row.predicted_value is None:
            continue
        by_target.setdefault(row.target_key, []).append(
            (float(row.predicted_value), float(row.actual_value))
        )

    summary = []
    for target, pairs in by_target.items():
        errors = [abs(p - a) for p, a in pairs]
        within_band = sum(1 for p, a in pairs if abs(p - a) <= 5)
        summary.append({
            "target_key": target,
            "evaluated_points": len(pairs),
            "mae": round(sum(errors) / len(errors), 2),
            "within_5_units_pct": round(100 * within_band / len(pairs), 1),
        })

    return {
        "backfilled_this_call": updated,
        "targets": summary,
        "note": (
            "Accuracy is computed only for horizons that have already elapsed. "
            "An empty result means no forecast has yet reached its target date."
        ),
    }


@router.get("/models", summary="Model registry")
def models(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(
        select(MlModel).order_by(desc(MlModel.trained_at)).limit(50)
    ).all()
    return {
        "models": [
            {
                "model_key": m.model_key,
                "version": m.version,
                "algorithm": m.algorithm,
                "trained_at": m.trained_at.isoformat() if m.trained_at else None,
                "training_rows": m.training_rows,
                "metrics": m.metrics,
                "is_active": m.is_active,
            }
            for m in rows
        ]
    }
