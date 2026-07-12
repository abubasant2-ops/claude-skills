from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin, enum_check
from app.models.enums import ActivityLevel, PhonemePosition


class Activity(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Therapy library item: one vocalized Arabic stimulus for a letter."""

    __tablename__ = "activities"
    __table_args__ = (
        enum_check("position", PhonemePosition),
        enum_check("level", ActivityLevel),
    )

    letter: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    text_ar: Mapped[str] = mapped_column(Text, nullable=False)  # fully vocalized
    image_ref: Mapped[str | None] = mapped_column(String(512))
    audio_ref: Mapped[str | None] = mapped_column(String(512))
