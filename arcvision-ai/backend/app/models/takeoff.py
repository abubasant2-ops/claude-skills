import uuid

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamped, UUIDPk


class TakeoffItem(UUIDPk, Timestamped, Base):
    """Aggregated, reviewable quantity line."""

    __tablename__ = "takeoff_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    # concrete | rebar | block | plaster | paint | tile | marble | door | window | cable | pipe ...
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, nullable=False)  # m3 | ton | m2 | m | no
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    original_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    source_element_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # pending | approved | edited | rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
