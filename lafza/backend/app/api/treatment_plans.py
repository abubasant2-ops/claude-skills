import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Child, TreatmentPlan, User
from app.schemas.treatment_plan import (
    TreatmentPlanCreate,
    TreatmentPlanOut,
    TreatmentPlanUpdate,
)

router = APIRouter(prefix="/treatment-plans", tags=["treatment-plans"])


def get_plan_or_404(plan_id: uuid.UUID, db: Session) -> TreatmentPlan:
    plan = db.get(TreatmentPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="treatment plan not found")
    return plan


def check_approver(approved_by: uuid.UUID | None, db: Session) -> None:
    if approved_by is not None and db.get(User, approved_by) is None:
        raise HTTPException(status_code=404, detail="approver not found")


@router.post("", response_model=TreatmentPlanOut, status_code=201)
def create_plan(
    payload: TreatmentPlanCreate, db: Session = Depends(get_db)
) -> TreatmentPlan:
    if db.get(Child, payload.child_id) is None:
        raise HTTPException(status_code=404, detail="child not found")
    check_approver(payload.approved_by, db)
    plan = TreatmentPlan(
        child_id=payload.child_id,
        author=payload.author.value,
        goals=payload.goals,
        target_phonemes=payload.target_phonemes,
        status=payload.status.value,
        approved_by=payload.approved_by,
    )
    db.add(plan)
    db.commit()
    return plan


@router.get("", response_model=list[TreatmentPlanOut])
def list_plans(
    child_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[TreatmentPlan]:
    query = select(TreatmentPlan).order_by(TreatmentPlan.created_at)
    if child_id is not None:
        query = query.where(TreatmentPlan.child_id == child_id)
    return list(db.scalars(query))


@router.get("/{plan_id}", response_model=TreatmentPlanOut)
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db)) -> TreatmentPlan:
    return get_plan_or_404(plan_id, db)


@router.patch("/{plan_id}", response_model=TreatmentPlanOut)
def update_plan(
    plan_id: uuid.UUID, payload: TreatmentPlanUpdate, db: Session = Depends(get_db)
) -> TreatmentPlan:
    plan = get_plan_or_404(plan_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "approved_by" in changes:
        check_approver(changes["approved_by"], db)
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    for field, value in changes.items():
        setattr(plan, field, value)
    db.commit()
    return plan


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    plan = get_plan_or_404(plan_id, db)
    db.delete(plan)
    db.commit()
    return Response(status_code=204)
