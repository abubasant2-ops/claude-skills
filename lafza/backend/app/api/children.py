import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Child, User
from app.schemas.child import ChildCreate, ChildOut, ChildUpdate

router = APIRouter(prefix="/children", tags=["children"])


def get_child_or_404(child_id: uuid.UUID, db: Session) -> Child:
    child = db.get(Child, child_id)
    if child is None:
        raise HTTPException(status_code=404, detail="child not found")
    return child


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
