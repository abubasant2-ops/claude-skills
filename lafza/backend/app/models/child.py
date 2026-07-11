import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import Sex


class Child(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "children"
    __table_args__ = (enum_check("sex", Sex),)

    guardian_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(8), nullable=False)
    dialect: Mapped[str] = mapped_column(String(16), nullable=False, default="gulf")
    consent_flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    guardian: Mapped["User"] = relationship(  # noqa: F821
        back_populates="children", foreign_keys=[guardian_id]
    )
    assessments: Mapped[list["Assessment"]] = relationship(  # noqa: F821
        back_populates="child"
    )
    phoneme_profiles: Mapped[list["PhonemeProfile"]] = relationship(  # noqa: F821
        back_populates="child"
    )
    treatment_plans: Mapped[list["TreatmentPlan"]] = relationship(  # noqa: F821
        back_populates="child", foreign_keys="TreatmentPlan.child_id"
    )
    sessions: Mapped[list["TherapySession"]] = relationship(  # noqa: F821
        back_populates="child"
    )
