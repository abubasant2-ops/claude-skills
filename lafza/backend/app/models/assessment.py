import uuid

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import AssessmentType


class Assessment(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "assessments"
    __table_args__ = (enum_check("type", AssessmentType),)

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 0–4 per domain (blueprint §11.3); null until scored
    severity: Mapped[int | None] = mapped_column(SmallInteger)
    red_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    child: Mapped["Child"] = relationship(back_populates="assessments")  # noqa: F821
