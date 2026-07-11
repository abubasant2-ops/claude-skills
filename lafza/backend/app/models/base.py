import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def enum_check(column: str, values: type[enum.StrEnum]) -> CheckConstraint:
    """CHECK constraint restricting a String column to a StrEnum's values.

    Enum values live in Python (see enums.py) rather than native PG enum types,
    so adding a value later is a plain constraint swap, not a type migration.
    """
    quoted = ", ".join(f"'{v.value}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=f"ck_{column}_valid")
