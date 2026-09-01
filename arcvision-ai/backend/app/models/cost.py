import uuid

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamped, UUIDPk


class CostLine(UUIDPk, Timestamped, Base):
    __tablename__ = "cost_lines"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    takeoff_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("takeoff_items.id", ondelete="CASCADE"), nullable=False
    )
    price_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("price_book_items.id", ondelete="SET NULL")
    )
    material_cost: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    labor_cost: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    equipment_cost: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(16, 2), nullable=False, default=0)
