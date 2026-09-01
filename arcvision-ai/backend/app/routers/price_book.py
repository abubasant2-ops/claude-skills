import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, get_current_user, get_db, require_permission
from app.core.rbac import Permission
from app.models.price_book import PriceBookItem
from app.schemas.common import PriceBookItemIn, PriceBookItemOut

router = APIRouter(prefix="/v1/org/price-book", tags=["price-book"])


@router.get("", response_model=list[PriceBookItemOut])
def list_items(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PriceBookItem]:
    return (
        db.query(PriceBookItem)
        .order_by(PriceBookItem.category, PriceBookItem.created_at.desc())
        .all()
    )


@router.post("", response_model=PriceBookItemOut, status_code=201)
def create_item(
    payload: PriceBookItemIn,
    user: CurrentUser = Depends(require_permission(Permission.MANAGE_PRICE_BOOK)),
    db: Session = Depends(get_db),
) -> PriceBookItem:
    item = PriceBookItem(
        organization_id=uuid.UUID(user.organization_id),
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
