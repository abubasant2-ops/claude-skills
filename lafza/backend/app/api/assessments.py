import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Assessment, Child
from app.schemas.assessment import AssessmentCreate, AssessmentOut, AssessmentUpdate

router = APIRouter(prefix="/assessments", tags=["assessments"])


def get_assessment_or_404(assessment_id: uuid.UUID, db: Session) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return assessment


@router.post("", response_model=AssessmentOut, status_code=201)
def create_assessment(
    payload: AssessmentCreate, db: Session = Depends(get_db)
) -> Assessment:
    if db.get(Child, payload.child_id) is None:
        raise HTTPException(status_code=404, detail="child not found")
    assessment = Assessment(
        child_id=payload.child_id,
        type=payload.type.value,
        raw_json=payload.raw_json,
        severity=payload.severity,
        red_flags=payload.red_flags,
    )
    db.add(assessment)
    db.commit()
    return assessment


@router.get("", response_model=list[AssessmentOut])
def list_assessments(
    child_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[Assessment]:
    query = select(Assessment).order_by(Assessment.created_at)
    if child_id is not None:
        query = query.where(Assessment.child_id == child_id)
    return list(db.scalars(query))


@router.get("/{assessment_id}", response_model=AssessmentOut)
def get_assessment(
    assessment_id: uuid.UUID, db: Session = Depends(get_db)
) -> Assessment:
    return get_assessment_or_404(assessment_id, db)


@router.patch("/{assessment_id}", response_model=AssessmentOut)
def update_assessment(
    assessment_id: uuid.UUID, payload: AssessmentUpdate, db: Session = Depends(get_db)
) -> Assessment:
    assessment = get_assessment_or_404(assessment_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assessment, field, value)
    db.commit()
    return assessment


@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(
    assessment_id: uuid.UUID, db: Session = Depends(get_db)
) -> Response:
    assessment = get_assessment_or_404(assessment_id, db)
    db.delete(assessment)
    db.commit()
    return Response(status_code=204)
