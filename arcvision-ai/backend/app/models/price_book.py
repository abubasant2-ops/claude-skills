import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamped, UUIDPk


class PriceBookItem(UUIDPk, Timestamped, Base):
    """Organization-scoped price book (corporate pricing memory)."""

    __tablename__ = "price_book_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    material_rate: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    labor_rate: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    equipment_rate: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    waste_factor: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.05)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="market")
    # market | supplier | past_contract
    valid_from: Mapped[date | None] = mapped_column(Date)
    region: Mapped[str] = mapped_column(Text, nullable=False, default="sa")
