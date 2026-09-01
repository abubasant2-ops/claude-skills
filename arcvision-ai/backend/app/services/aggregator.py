"""Quantity Aggregation — turns extracted elements into reviewable takeoff lines.

Maps the Unified Element Model (UEM) → BOQ-style categories with units.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.element import ExtractedElement
from app.models.takeoff import TakeoffItem


@dataclass
class _Bucket:
    category: str
    unit: str
    description: str
    quantity: Decimal = Decimal("0")
    confidence_sum: Decimal = Decimal("0")
    count: int = 0
    element_ids: list[uuid.UUID] = field(default_factory=list)


# (element_type → (category, unit, geometry_field, description)).
# Concrete volumes are summed from slab/column/beam/footing/wall elements that carry volume_m3.
_RULES: dict[str, tuple[str, str, str, str]] = {
    "wall": ("block", "m2", "area_m2", "جدران بلوك"),
    "wall_concrete": ("concrete", "m3", "volume_m3", "خرسانة جدران"),
    "slab": ("concrete", "m3", "volume_m3", "خرسانة أسقف"),
    "column": ("concrete", "m3", "volume_m3", "خرسانة أعمدة"),
    "beam": ("concrete", "m3", "volume_m3", "خرسانة كمرات"),
    "footing": ("concrete", "m3", "volume_m3", "خرسانة أساسات"),
    "door": ("door", "no", "count", "أبواب"),
    "window": ("window", "no", "count", "نوافذ"),
    "space": ("finishing_floor", "m2", "area_m2", "تشطيب أرضيات"),
    "cable": ("cable", "m", "length_m", "كابلات كهرباء"),
    "pipe": ("pipe", "m", "length_m", "مواسير"),
    "hvac_unit": ("hvac_unit", "no", "count", "وحدات تكييف"),
}

# rough estimation: rebar tons per m3 of concrete (for residential/commercial).
# This is intentionally conservative; the user can edit in Takeoff Review.
_REBAR_TON_PER_M3_CONCRETE = Decimal("0.10")


def aggregate_project_takeoff(
    db: Session,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[TakeoffItem]:
    """Recomputes takeoff_items from extracted_elements for the project.

    Strategy:
      - Drop existing PENDING items (preserve approved/edited human work).
      - Rebuild PENDING items from current elements.
    """
    db.query(TakeoffItem).filter(
        TakeoffItem.project_id == project_id,
        TakeoffItem.review_status == "pending",
    ).delete(synchronize_session=False)

    elements: Iterable[ExtractedElement] = (
        db.query(ExtractedElement).filter(ExtractedElement.project_id == project_id).all()
    )

    buckets: dict[tuple[str, str], _Bucket] = {}
    concrete_volume = Decimal("0")

    for el in elements:
        rule = _RULES.get(el.element_type)
        if not rule:
            continue
        category, unit, geom_field, desc = rule
        geom = el.geometry or {}
        if geom_field == "count":
            qty = Decimal("1")
        else:
            raw = geom.get(geom_field)
            if raw is None:
                continue
            qty = Decimal(str(raw))
        if qty <= 0:
            continue

        key = (category, unit)
        b = buckets.get(key)
        if b is None:
            b = _Bucket(category=category, unit=unit, description=desc)
            buckets[key] = b
        b.quantity += qty
        b.confidence_sum += Decimal(str(el.confidence or 1.0))
        b.count += 1
        b.element_ids.append(el.id)
        if category == "concrete":
            concrete_volume += qty

    # Derive rebar from concrete (transparent rule — flagged with lower confidence).
    if concrete_volume > 0:
        key = ("rebar", "ton")
        b = _Bucket(category="rebar", unit="ton", description="حديد تسليح (تقدير من حجم الخرسانة)")
        b.quantity = (concrete_volume * _REBAR_TON_PER_M3_CONCRETE).quantize(Decimal("0.001"))
        b.confidence_sum = Decimal("0.6")
        b.count = 1
        buckets[key] = b

    items: list[TakeoffItem] = []
    for b in buckets.values():
        avg_conf = (b.confidence_sum / b.count) if b.count else Decimal("1")
        item = TakeoffItem(
            organization_id=organization_id,
            project_id=project_id,
            category=b.category,
            description=b.description,
            unit=b.unit,
            quantity=b.quantity.quantize(Decimal("0.001")),
            original_quantity=b.quantity.quantize(Decimal("0.001")),
            confidence=avg_conf.quantize(Decimal("0.001")),
            source_element_ids=b.element_ids or None,
            review_status="pending",
        )
        db.add(item)
        items.append(item)
    db.flush()
    return items
