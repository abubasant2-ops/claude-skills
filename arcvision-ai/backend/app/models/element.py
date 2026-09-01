import uuid

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._mixins import Timestamped, UUIDPk


class ExtractedElement(UUIDPk, Timestamped, Base):
    """Unified Element Model (UEM) — one row per element parsed from any source."""

    __tablename__ = "extracted_elements"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    element_type: Mapped[str] = mapped_column(Text, nullable=False)
    # wall | slab | column | beam | footing | door | window | space | cable | pipe | hvac_unit ...
    discipline: Mapped[str | None] = mapped_column(Text)
    geometry: Mapped[dict | None] = mapped_column(JSONB)
    # e.g. {"length_m": 4.2, "height_m": 3.0, "thickness_m": 0.2, "area_m2": 12.6, "volume_m3": 2.52}
    source_ref: Mapped[dict | None] = mapped_column(JSONB)
    # IFC: {"ifc_guid": "...", "ifc_type": "IfcWall"}
    # PDF: {"page": 4, "bbox": [x,y,w,h]}
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)  # ifc | aps | vision_llm | ocr
