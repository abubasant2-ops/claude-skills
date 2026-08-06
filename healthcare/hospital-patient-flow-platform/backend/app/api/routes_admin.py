"""Reference data administration: facilities, units and benchmark overrides."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.benchmarks import CATALOGUE
from app.core.db import get_session
from app.models import UNIT_KINDS, Benchmark, Facility, Unit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class FacilityIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name_en: str
    name_ar: str | None = None
    timezone: str = "Asia/Riyadh"
    licensed_beds: int = Field(ge=0)
    ed_treatment_spaces: int = Field(default=0, ge=0)
    cluster_name: str | None = None


class UnitIn(BaseModel):
    code: str
    name_en: str
    name_ar: str | None = None
    kind: str
    specialty: str | None = None
    physical_beds: int = Field(default=0, ge=0)
    staffed_beds: int = Field(default=0, ge=0)
    target_occupancy: float | None = Field(default=85.0, ge=0, le=100)


class BenchmarkIn(BaseModel):
    metric_key: str
    target_value: float | None = None
    amber_threshold: float | None = None
    red_threshold: float | None = None
    higher_is_better: bool | None = None
    source: str = "INTERNAL"


@router.post("/facilities", status_code=status.HTTP_201_CREATED)
def create_facility(payload: FacilityIn, session: Session = Depends(get_session)) -> dict:
    if session.scalar(select(Facility).where(Facility.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Facility code '{payload.code}' already exists")
    facility = Facility(**payload.model_dump())
    session.add(facility)
    session.flush()
    return {"facility_id": facility.facility_id, "code": facility.code}


@router.get("/units")
def list_units(facility_id: int = Query(1), session: Session = Depends(get_session)) -> dict:
    units = session.scalars(select(Unit).where(Unit.facility_id == facility_id)).all()
    return {
        "units": [
            {
                "unit_id": u.unit_id, "code": u.code, "name_en": u.name_en, "name_ar": u.name_ar,
                "kind": u.kind, "specialty": u.specialty, "physical_beds": u.physical_beds,
                "staffed_beds": u.staffed_beds,
                "target_occupancy": float(u.target_occupancy) if u.target_occupancy else None,
                "is_active": u.is_active,
            }
            for u in units
        ]
    }


@router.post("/units", status_code=status.HTTP_201_CREATED)
def upsert_unit(
    payload: UnitIn,
    facility_id: int = Query(1),
    session: Session = Depends(get_session),
) -> dict:
    if payload.kind not in UNIT_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"kind must be one of {', '.join(UNIT_KINDS)}",
        )
    if session.get(Facility, facility_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Facility {facility_id} not found")

    unit = session.scalar(
        select(Unit).where(Unit.facility_id == facility_id, Unit.code == payload.code)
    )
    if unit is None:
        unit = Unit(facility_id=facility_id, code=payload.code, name_en=payload.name_en,
                    kind=payload.kind)
        session.add(unit)

    for key, value in payload.model_dump().items():
        setattr(unit, key, value)
    session.flush()
    return {"unit_id": unit.unit_id, "code": unit.code}


@router.get("/benchmarks")
def list_benchmarks(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(Benchmark)).all()
    overrides = {r.metric_key for r in rows}
    return {
        "configured": [
            {
                "metric_key": r.metric_key,
                "target": float(r.target_value) if r.target_value is not None else None,
                "amber": float(r.amber_threshold) if r.amber_threshold is not None else None,
                "red": float(r.red_threshold) if r.red_threshold is not None else None,
                "higher_is_better": r.higher_is_better,
                "source": r.source,
            }
            for r in rows
        ],
        "using_defaults": sorted(set(CATALOGUE) - overrides),
    }


@router.put("/benchmarks")
def set_benchmark(payload: BenchmarkIn, session: Session = Depends(get_session)) -> dict:
    if payload.metric_key not in CATALOGUE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown metric key '{payload.metric_key}'",
        )
    definition = CATALOGUE[payload.metric_key]

    row = session.scalar(
        select(Benchmark).where(
            Benchmark.metric_key == payload.metric_key, Benchmark.scope == "FACILITY"
        )
    )
    if row is None:
        row = Benchmark(metric_key=payload.metric_key, scope="FACILITY")
        session.add(row)

    row.target_value = payload.target_value
    row.amber_threshold = payload.amber_threshold
    row.red_threshold = payload.red_threshold
    row.higher_is_better = (
        payload.higher_is_better if payload.higher_is_better is not None
        else definition.higher_is_better
    )
    row.source = payload.source
    session.flush()
    return {"metric_key": row.metric_key, "updated": True}
