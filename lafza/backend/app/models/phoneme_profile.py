import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import PhonemePosition


class PhonemeProfile(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Time-series of per-phoneme scores; one row per scored utterance batch."""

    __tablename__ = "phoneme_profiles"
    __table_args__ = (
        enum_check("position", PhonemePosition),
        CheckConstraint(
            "gop_score >= 0 AND gop_score <= 100", name="ck_gop_score_range"
        ),
        Index("ix_phoneme_profiles_child_phoneme_position",
              "child_id", "phoneme", "position"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id"), nullable=False
    )
    phoneme: Mapped[str] = mapped_column(String(4), nullable=False)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    gop_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # free text: error patterns (§7) will grow beyond the initial stub set
    error_type: Mapped[str | None] = mapped_column(String(32))

    child: Mapped["Child"] = relationship(  # noqa: F821
        back_populates="phoneme_profiles"
    )
