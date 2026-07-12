import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CaseloadRowOut(BaseModel):
    """T1 — one caseload table row."""

    child_id: uuid.UUID
    dob: date
    sex: str
    dialect: str
    attempts: int
    adherence: float  # practiced days / 7 over the last week, 0..1
    gop_mean: int | None  # mean of latest score per (phoneme, position)
    gop_delta_30d: int | None  # latest-mean minus earliest-mean, 30-day window
    plan_status: str | None
    last_activity_at: datetime | None


class HeatmapCellOut(BaseModel):
    """T2 — latest score for one (letter × position) cell."""

    phoneme: str
    position: str
    gop_score: int
    error_type: str | None
    created_at: datetime


class HeatmapOut(BaseModel):
    child_id: uuid.UUID
    cells: list[HeatmapCellOut]
