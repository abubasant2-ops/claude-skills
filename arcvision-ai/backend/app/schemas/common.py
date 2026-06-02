from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshIn(BaseModel):
    refresh_token: str


# ---------- Users ----------
class UserOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    role: str


# ---------- Projects ----------
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    client_name: str | None = None
    project_type: str | None = None
    location_city: str | None = None
    gross_area_m2: Decimal | None = None
    sbc_profile: str | None = None


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    client_name: str | None
    project_type: str | None
    location_city: str | None
    gross_area_m2: Decimal | None
    status: str
    sbc_profile: str | None
    created_at: datetime


# ---------- Documents ----------
class DocumentOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    file_name: str
    file_type: str
    discipline: str | None
    status: str
    page_count: int | None
    processing_meta: dict[str, Any] | None
    error_message: str | None
    created_at: datetime


# ---------- Takeoff ----------
class TakeoffItemOut(ORMModel):
    id: uuid.UUID
    category: str
    description: str | None
    unit: str
    quantity: Decimal
    original_quantity: Decimal | None
    confidence: Decimal
    review_status: str
    source_element_ids: list[uuid.UUID] | None


class TakeoffPatch(BaseModel):
    quantity: Decimal | None = None
    review_status: str | None = Field(None, pattern="^(approved|edited|rejected|pending)$")


class TakeoffSummary(BaseModel):
    items: list[TakeoffItemOut]
    total_items: int
    low_confidence: int
    approved: int


# ---------- Price Book ----------
class PriceBookItemIn(BaseModel):
    category: str
    description: str | None = None
    unit: str
    material_rate: Decimal = Decimal("0")
    labor_rate: Decimal = Decimal("0")
    equipment_rate: Decimal = Decimal("0")
    waste_factor: Decimal = Decimal("0.05")
    source: str = "market"


class PriceBookItemOut(ORMModel):
    id: uuid.UUID
    category: str
    description: str | None
    unit: str
    material_rate: Decimal
    labor_rate: Decimal
    equipment_rate: Decimal
    waste_factor: Decimal
    source: str


# ---------- Cost ----------
class CostParamsIn(BaseModel):
    indirect_pct: Decimal = Decimal("0.08")
    contingency_pct: Decimal = Decimal("0.05")
    margin_pct: Decimal = Decimal("0.14")


class CostSummaryOut(BaseModel):
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


TokenOut.model_rebuild()
