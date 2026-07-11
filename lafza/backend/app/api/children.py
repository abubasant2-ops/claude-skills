import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Assessment, Child, TreatmentPlan, User
from app.models.enums import AssessmentType
from app.schemas.child import ChildCreate, ChildOut, ChildUpdate
from app.schemas.parent_summary import ParentSummaryOut
from app.schemas.screening import (
    QuestionnaireOut,
    ScreeningResultOut,
    ScreeningSubmission,
)
from app.schemas.therapist import HeatmapOut
from app.schemas.treatment_plan import TreatmentPlanOut
from app.services.parent_summary import build_parent_summary
from app.services.plan_generator import NoTherapyTargetsError, PlanGeneratorService
from app.services.screening import age_in_months, evaluate_screening, get_questionnaire
from app.services.therapist import build_heatmap

router = APIRouter(prefix="/children", tags=["children"])

plan_generator = PlanGeneratorService()


def get_child_or_404(child_id: uuid.UUID, db: Session) -> Child:
    child = db.get(Child, child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="child not found")
    return child


@router.get(
    "/{child_id}/screening/questionnaire", response_model=QuestionnaireOut
)
def screening_questionnaire(
    child_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Age-relevant screening instrument for this child (blueprint L1)."""
    child = get_child_or_404(child_id, db)
    return get_questionnaire(age_in_months(child.dob))


@router.post(
    "/{child_id}/screening",
    response_model=ScreeningResultOut,
    status_code=201,
)
def submit_screening(
    child_id: uuid.UUID,
    payload: ScreeningSubmission,
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate parent answers deterministically and persist the assessment."""
    child = get_child_or_404(child_id, db)
    evaluation = evaluate_screening(
        age_months=age_in_months(child.dob),
        red_flag_answers=payload.red_flag_answers,
        vocabulary_checked=payload.vocabulary_checked,
        intelligibility=payload.intelligibility,
    )
    assessment = Assessment(
        child_id=child.id,
        type=AssessmentType.SCREENING.value,
        raw_json={
            "answers": payload.model_dump(),
            "evaluation": evaluation,
        },
        severity=evaluation["severity"],
        red_flags=evaluation["red_flags"],
    )
    db.add(assessment)
    db.commit()
    return {**evaluation, "assessment_id": assessment.id}


@router.get("/{child_id}/phoneme-heatmap", response_model=HeatmapOut)
def phoneme_heatmap(
    child_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """T2 — latest score per (letter × position) cell for the heatmap."""
    get_child_or_404(child_id, db)
    return build_heatmap(db, child_id)


@router.get("/{child_id}/parent-summary", response_model=ParentSummaryOut)
def parent_summary(
    child_id: uuid.UUID, db: Session = Depends(get_db)
) -> dict:
    """Streak, weekly practice time, and simplified weekly report (P1/P3)."""
    get_child_or_404(child_id, db)
    return build_parent_summary(db, child_id)


@router.post(
    "/{child_id}/plans/generate",
    response_model=TreatmentPlanOut,
    status_code=201,
)
def generate_plan(
    child_id: uuid.UUID, db: Session = Depends(get_db)
) -> TreatmentPlan:
    """phoneme_profiles → PlanGeneratorService → draft treatment plan (§7)."""
    get_child_or_404(child_id, db)
    try:
        return plan_generator.generate_for_child(db, child_id)
    except NoTherapyTargetsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("", response_model=ChildOut, status_code=201)
def create_child(payload: ChildCreate, db: Session = Depends(get_db)) -> Child:
    if db.get(User, payload.guardian_id) is None:
        raise HTTPException(status_code=404, detail="guardian not found")
    child = Child(
        guardian_id=payload.guardian_id,
        dob=payload.dob,
        sex=payload.sex.value,
        dialect=payload.dialect,
        consent_flags=payload.consent_flags,
    )
    db.add(child)
    db.commit()
    return child


@router.get("", response_model=list[ChildOut])
def list_children(
    guardian_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[Child]:
    query = select(Child).order_by(Child.created_at)
    if guardian_id is not None:
        query = query.where(Child.guardian_id == guardian_id)
    return list(db.scalars(query))


@router.get("/{child_id}", response_model=ChildOut)
def get_child(child_id: uuid.UUID, db: Session = Depends(get_db)) -> Child:
    return get_child_or_404(child_id, db)


@router.patch("/{child_id}", response_model=ChildOut)
def update_child(
    child_id: uuid.UUID, payload: ChildUpdate, db: Session = Depends(get_db)
) -> Child:
    child = get_child_or_404(child_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "sex" in changes and changes["sex"] is not None:
        changes["sex"] = changes["sex"].value
    for field, value in changes.items():
        setattr(child, field, value)
    db.commit()
    return child


@router.delete("/{child_id}", status_code=204)
def delete_child(child_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    child = get_child_or_404(child_id, db)
    db.delete(child)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="child has linked records and cannot be deleted"
        )
    return Response(status_code=204)
