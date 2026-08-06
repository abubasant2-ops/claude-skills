"""Engine, session factory and the declarative base.

The ORM is written against the portable subset of SQLAlchemy so the same
models run on PostgreSQL in production and on SQLite for tests. Where the
two diverge -- JSON columns, ``now()`` defaults -- the portable spelling is
used and PostgreSQL-only optimisations live in ``db/schema.sql``.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False lets FastAPI's threadpool share the handle.
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or "mode=memory" in url:
            # Each connection to an in-memory SQLite database gets its own
            # private copy, so without a single shared connection the API
            # thread would find no tables at all.
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked, which would let the tests
    pass on data PostgreSQL would reject."""
    if "sqlite3" in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401  (registers the mappers)

    Base.metadata.create_all(bind=engine)
