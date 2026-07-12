import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import PlanAuthor, PlanStatus


class TreatmentPlan(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "treatment_plans"
    __table_args__ = (
        enum_check("author", PlanAuthor),
        enum_check("status", PlanStatus),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(8), nullable=False)
    goals: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    target_phonemes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PlanStatus.DRAFT.value
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    child: Mapped["Child"] = relationship(  # noqa: F821
        back_populates="treatment_plans", foreign_keys=[child_id]
    )
    approver: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[approved_by]
    )
    sessions: Mapped[list["TherapySession"]] = relationship(  # noqa: F821
        back_populates="plan"
    )
