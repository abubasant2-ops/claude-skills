"""Metric, dashboard, drill-down and export endpoints."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.analytics import service
from app.analytics.benchmarks import CATALOGUE
from app.api.deps import Period, get_period
from app.core.db import get_session
from app.models import Facility

router = APIRouter(prefix="/api/v1", tags=["analytics"])


def _analyse(session: Session, facility_id: int, period: Period, unit_ids: list[int] | None = None):
    try:
        return service.analyse(
            session, facility_id=facility_id, start=period.start, end=period.end,
            unit_ids=unit_ids,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/facilities", summary="Facilities available to the caller")
def list_facilities(session: Session = Depends(get_session)) -> dict:
    facilities = session.query(Facility).all()
    return {
        "facilities": [
            {
                "facility_id": f.facility_id,
                "code": f.code,
                "name_en": f.name_en,
                "name_ar": f.name_ar,
                "licensed_beds": f.licensed_beds,
                "ed_treatment_spaces": f.ed_treatment_spaces,
                "timezone": f.timezone,
                "cluster": f.cluster_name,
            }
            for f in facilities
        ]
    }


@router.get("/metrics/catalogue", summary="Metric definitions and default benchmarks")
def metric_catalogue(domain: str | None = Query(None)) -> dict:
    definitions = [d for d in CATALOGUE.values() if domain is None or d.domain == domain]
    return {
        "count": len(definitions),
        "metrics": [
            {
                "key": d.key,
                "label_en": d.label_en,
                "label_ar": d.label_ar,
                "unit": d.unit,
                "domain": d.domain,
                "definition_en": d.definition_en,
                "numerator": d.numerator_en,
                "denominator": d.denominator_en,
                "target": d.target,
                "amber": d.amber,
                "red": d.red,
                "higher_is_better": d.higher_is_better,
                "source": d.source,
            }
            for d in definitions
        ],
    }


@router.get("/metrics", summary="All computed indicators for a period")
def metrics(
    facility_id: int = Query(1),
    unit_ids: list[int] | None = Query(None),
    domain: str | None = Query(None, description="capacity | ed | journey | quality | nursing"),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period, unit_ids)
    values = result.metric_dicts()
    if domain:
        keys = {d.key for d in CATALOGUE.values() if d.domain == domain}
        values = [v for v in values if v["key"] in keys]

    return {
        "facility_id": facility_id,
        "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
        "metrics": values,
        "alerts": service.build_alerts(result),
        "coverage": result.detail.get("coverage", {}),
    }


@router.get("/dashboards/{role}", summary="Role-specific command centre payload")
def dashboard(
    role: str,
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    try:
        return service.dashboard(result, role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/trends", summary="Metric time series")
def trends(
    metric_keys: list[str] = Query(..., description="One or more metric keys"),
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    unknown = [k for k in metric_keys if k not in CATALOGUE]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown metric key(s): {', '.join(unknown)}",
        )
    # Daily recomputation across a long window is expensive; nudge the caller
    # toward a coarser grain rather than timing out.
    if period.grain == "day" and period.days > 120:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A {period.days}-day window at daily grain is too expensive to compute. "
                "Use grain=week or grain=month for windows over 120 days."
            ),
        )
    return service.trend(
        session, facility_id=facility_id, metric_keys=metric_keys,
        start=period.start, end=period.end, grain=period.grain,
    )


@router.get("/drilldown/units", summary="Per-unit capacity breakdown")
def drilldown_units(
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    return {
        "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
        "units": result.detail["capacity"]["units"],
        "heatmap": result.detail["capacity"]["heatmap"],
    }


@router.get("/drilldown/journey", summary="Journey segments and bottleneck ranking")
def drilldown_journey(
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    return {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            **result.detail["journey"]}


@router.get("/drilldown/emergency", summary="ED hourly state, CTAS mix and arrival profile")
def drilldown_emergency(
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    return {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            **result.detail["emergency"]}


@router.get("/drilldown/quality", summary="Safety event detail")
def drilldown_quality(
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    return {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            **result.detail["quality"]}


@router.get("/drilldown/nursing", summary="Per-unit nursing indicators")
def drilldown_nursing(
    facility_id: int = Query(1),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
) -> dict:
    result = _analyse(session, facility_id, period)
    return {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            **result.detail["nursing"]}


@router.get("/export", summary="Export a period as CSV or JSON")
def export(
    facility_id: int = Query(1),
    fmt: str = Query("csv", pattern="^(csv|json)$"),
    scope: str = Query("metrics", pattern="^(metrics|units|journey|nursing)$"),
    period: Period = Depends(get_period),
    session: Session = Depends(get_session),
):
    result = _analyse(session, facility_id, period)

    if scope == "metrics":
        rows = result.metric_dicts()
    elif scope == "units":
        rows = result.detail["capacity"]["units"]
    elif scope == "journey":
        rows = result.detail["journey"]["segments"]
    else:
        rows = result.detail["nursing"]["units"]

    stamp = f"{period.start.isoformat()}_{period.end.isoformat()}"
    filename = f"hpf_{scope}_{stamp}.{fmt}"

    if fmt == "json":
        payload = json.dumps(
            {"facility_id": facility_id, "scope": scope,
             "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
             "rows": rows},
            ensure_ascii=False, indent=2,
        )
        return StreamingResponse(
            io.BytesIO(payload.encode("utf-8")), media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    buffer = io.StringIO()
    if rows:
        # Nested dicts (context, drivers) are flattened to JSON strings so the
        # CSV stays one row per record and opens cleanly in Excel.
        flattened = [
            {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
             for k, v in row.items()}
            for row in rows
        ]
        writer = csv.DictWriter(buffer, fieldnames=list(flattened[0].keys()))
        writer.writeheader()
        writer.writerows(flattened)
    else:
        buffer.write("no_data\n")

    # UTF-8 BOM so Excel renders the Arabic labels instead of mojibake.
    data = "﻿" + buffer.getvalue()
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
