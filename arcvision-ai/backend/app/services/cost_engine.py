"""Cost Engine — deterministic pricing from takeoff + price book.

Formula (PRD §11.1):
    line   = qty * (1 + waste) * (material_rate + labor_rate + equipment_rate)
    direct = Σ line
    indirect = direct * indirect_pct
    contingency = (direct + indirect) * contingency_pct        # tied to Risk Score in V1
    total = direct + indirect + contingency
    bid_price = total * (1 + margin_pct)
    cost_per_m2 = total / gross_area_m2
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.cost import CostLine
from app.models.price_book import PriceBookItem
from app.models.project import Project
from app.models.takeoff import TakeoffItem


@dataclass
class CostBreakdown:
    direct: Decimal
    indirect: Decimal
    contingency: Decimal
    total: Decimal
    bid_price: Decimal
    margin_amount: Decimal
    cost_per_m2: Decimal | None
    by_category: dict[str, Decimal]
    line_count: int
    priced_count: int
    unpriced_categories: list[str]


@dataclass
class CostParams:
    indirect_pct: Decimal = Decimal("0.08")
    contingency_pct: Decimal = Decimal("0.05")
    margin_pct: Decimal = Decimal("0.14")


def _q(x: Decimal | float | int | str) -> Decimal:
    return Decimal(str(x))


def recalculate_project_cost(
    db: Session,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    params: CostParams | None = None,
) -> CostBreakdown:
    params = params or CostParams()

    # Wipe existing cost lines (they're derived).
    db.query(CostLine).filter(CostLine.project_id == project_id).delete(synchronize_session=False)

    items: Iterable[TakeoffItem] = (
        db.query(TakeoffItem)
        .filter(
            TakeoffItem.project_id == project_id,
            TakeoffItem.review_status.in_(["approved", "edited", "pending"]),
        )
        .all()
    )

    # Index price book by (category, unit) preferring most recent / past_contract source.
    prices: dict[tuple[str, str], PriceBookItem] = {}
    pb_rows = (
        db.query(PriceBookItem)
        .filter(PriceBookItem.organization_id == organization_id)
        .order_by(PriceBookItem.created_at.desc())
        .all()
    )
    for p in pb_rows:
        key = (p.category, p.unit)
        if key not in prices:
            prices[key] = p

    direct = Decimal("0")
    by_cat: dict[str, Decimal] = {}
    priced = 0
    unpriced: set[str] = set()

    for item in items:
        key = (item.category, item.unit)
        price = prices.get(key)
        if price is None:
            unpriced.add(item.category)
            continue

        qty = _q(item.quantity) * (Decimal("1") + _q(price.waste_factor))
        mat = qty * _q(price.material_rate)
        lab = qty * _q(price.labor_rate)
        eq = qty * _q(price.equipment_rate)
        line_total = (mat + lab + eq).quantize(Decimal("0.01"))

        db.add(
            CostLine(
                organization_id=organization_id,
                project_id=project_id,
                takeoff_item_id=item.id,
                price_source_id=price.id,
                material_cost=mat.quantize(Decimal("0.01")),
                labor_cost=lab.quantize(Decimal("0.01")),
                equipment_cost=eq.quantize(Decimal("0.01")),
                line_total=line_total,
            )
        )
        direct += line_total
        by_cat[item.category] = by_cat.get(item.category, Decimal("0")) + line_total
        priced += 1

    indirect = (direct * params.indirect_pct).quantize(Decimal("0.01"))
    contingency = ((direct + indirect) * params.contingency_pct).quantize(Decimal("0.01"))
    total = (direct + indirect + contingency).quantize(Decimal("0.01"))
    bid_price = (total * (Decimal("1") + params.margin_pct)).quantize(Decimal("0.01"))
    margin_amount = (bid_price - total).quantize(Decimal("0.01"))

    project = db.get(Project, project_id)
    cost_per_m2: Decimal | None = None
    if project and project.gross_area_m2:
        area = _q(project.gross_area_m2)
        if area > 0:
            cost_per_m2 = (total / area).quantize(Decimal("0.01"))

    db.flush()

    return CostBreakdown(
        direct=direct.quantize(Decimal("0.01")),
        indirect=indirect,
        contingency=contingency,
        total=total,
        bid_price=bid_price,
        margin_amount=margin_amount,
        cost_per_m2=cost_per_m2,
        by_category={k: v.quantize(Decimal("0.01")) for k, v in by_cat.items()},
        line_count=len(items) if isinstance(items, list) else priced + len(unpriced),
        priced_count=priced,
        unpriced_categories=sorted(unpriced),
    )
