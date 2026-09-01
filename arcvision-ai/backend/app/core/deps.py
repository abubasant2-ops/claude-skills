from dataclasses import dataclass
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.rbac import Permission, has_permission
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


@dataclass
class CurrentUser:
    user_id: str
    organization_id: str
    role: str


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> CurrentUser:
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="Wrong token type")
    return CurrentUser(
        user_id=payload["sub"],
        organization_id=payload["org"],
        role=payload["role"],
    )


def get_db(user: CurrentUser = Depends(get_current_user)) -> Generator[Session, None, None]:
    """Yields a tenant-scoped session — RLS will filter rows by app.current_org."""
    db = SessionLocal()
    try:
        db.execute(text("SET LOCAL app.current_org = :org"), {"org": user.organization_id})
        yield db
    finally:
        db.close()


def require_permission(perm: Permission):
    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(user.role, perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' lacks permission '{perm.value}'",
            )
        return user

    return _check
