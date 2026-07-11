import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Recording(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """Pointer to encrypted child audio in object storage — never raw audio here.

    retention_until drives the purge job (CLAUDE.md rule 5: hard-delete support).
    """

    __tablename__ = "recordings"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    audio_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    retention_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    session: Mapped["TherapySession"] = relationship(  # noqa: F821
        back_populates="recordings"
    )
