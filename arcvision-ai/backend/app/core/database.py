from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db(organization_id: str | None = None) -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and sets RLS tenant context."""
    db = SessionLocal()
    try:
        if organization_id:
            db.execute(text("SET LOCAL app.current_org = :org"), {"org": organization_id})
        yield db
    finally:
        db.close()


@contextmanager
def session_scope(organization_id: str | None = None) -> Generator[Session, None, None]:
    """Context manager for workers / scripts."""
    db = SessionLocal()
    try:
        if organization_id:
            db.execute(text("SET LOCAL app.current_org = :org"), {"org": organization_id})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
