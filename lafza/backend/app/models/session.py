import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class TherapySession(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """One practice sitting by a child, executing activities from a plan."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "adherence IS NULL OR (adherence >= 0 AND adherence <= 1)",
            name="ck_adherence_range",
        ),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("treatment_plans.id"), index=True
    )
    activity_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    scores_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    adherence: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0

    child: Mapped["Child"] = relationship(back_populates="sessions")  # noqa: F821
    plan: Mapped["TreatmentPlan | None"] = relationship(  # noqa: F821
        back_populates="sessions"
    )
    recordings: Mapped[list["Recording"]] = relationship(  # noqa: F821
        back_populates="session"
    )
