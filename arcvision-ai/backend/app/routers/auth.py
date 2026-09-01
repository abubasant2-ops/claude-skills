from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.models.user import User
from app.schemas.common import LoginIn, RefreshIn, TokenOut, UserOut

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(_db)) -> TokenOut:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access = create_access_token(
        sub=str(user.id), org=str(user.organization_id), role=user.role
    )
    refresh = create_refresh_token(sub=str(user.id), org=str(user.organization_id))
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn, db: Session = Depends(_db)) -> TokenOut:
    try:
        data = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if data.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")
    user = db.get(User, data["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    access = create_access_token(
        sub=str(user.id), org=str(user.organization_id), role=user.role
    )
    new_refresh = create_refresh_token(sub=str(user.id), org=str(user.organization_id))
    return TokenOut(
        access_token=access,
        refresh_token=new_refresh,
        user=UserOut.model_validate(user),
    )
