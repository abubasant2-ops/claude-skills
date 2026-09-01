import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.rbac import Permission
from app.models.takeoff import TakeoffItem
from app.schemas.common import TakeoffItemOut, TakeoffPatch, TakeoffSummary
from app.services.audit import log_action

router = APIRouter(prefix="/v1", tags=["takeoff"])

_LOW_CONF_THRESHOLD = Decimal("0.85")


@router.get("/projects/{project_id}/takeoff", response_model=TakeoffSummary)
def list_takeoff(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TakeoffSummary:
    items = (
        db.query(TakeoffItem)
        .filter(TakeoffItem.project_id == project_id)
        .order_by(TakeoffItem.category, TakeoffItem.created_at)
        .all()
    )
    low = sum(1 for i in items if i.confidence < _LOW_CONF_THRESHOLD)
    approved = sum(1 for i in items if i.review_status == "approved")
    return TakeoffSummary(
        items=[TakeoffItemOut.model_validate(i) for i in items],
        total_items=len(items),
        low_confidence=low,
        approved=approved,
    )


@router.patch("/takeoff/{item_id}", response_model=TakeoffItemOut)
def update_takeoff(
    item_id: uuid.UUID,
    patch: TakeoffPatch,
    user: CurrentUser = Depends(require_permission(Permission.REVIEW_TAKEOFF)),
    db: Session = Depends(get_db),
) -> TakeoffItem:
    item = db.get(TakeoffItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Takeoff item not found")

    before = {"quantity": float(item.quantity), "review_status": item.review_status}

    if patch.quantity is not None and patch.quantity != item.quantity:
        if item.original_quantity is None:
            item.original_quantity = item.quantity
        item.quantity = patch.quantity
        if patch.review_status is None:
            item.review_status = "edited"

    if patch.review_status is not None:
        item.review_status = patch.review_status

    item.reviewed_by = uuid.UUID(user.user_id)

    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="update",
        entity_type="takeoff_item",
        entity_id=item.id,
        before=before,
        after={"quantity": float(item.quantity), "review_status": item.review_status},
    )
    db.commit()
    db.refresh(item)
    return item


@router.post("/projects/{project_id}/takeoff/approve")
def approve_all(
    project_id: uuid.UUID,
    user: CurrentUser = Depends(require_permission(Permission.APPROVE_TAKEOFF)),
    db: Session = Depends(get_db),
) -> dict:
    updated = (
        db.query(TakeoffItem)
        .filter(
            TakeoffItem.project_id == project_id,
            TakeoffItem.review_status == "pending",
        )
        .update(
            {"review_status": "approved", "reviewed_by": uuid.UUID(user.user_id)},
            synchronize_session=False,
        )
    )
    log_action(
        db,
        organization_id=user.organization_id,
        user_id=user.user_id,
        action="approve_all",
        entity_type="takeoff",
        entity_id=project_id,
        after={"approved_count": updated},
    )
    db.commit()
    return {"approved": updated}
