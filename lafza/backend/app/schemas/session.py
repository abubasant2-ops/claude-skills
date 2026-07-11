import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PhonemePosition


class SessionCreate(BaseModel):
    child_id: uuid.UUID
    plan_id: uuid.UUID | None = None
    activity_ids: list = Field(default_factory=list)
    duration_sec: int | None = Field(default=None, ge=0)
    scores_json: dict = Field(default_factory=dict)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    plan_id: uuid.UUID | None
    activity_ids: list
    duration_sec: int | None
    scores_json: dict
    adherence: float | None
    created_at: datetime


class UtteranceScoreOut(BaseModel):
    """§6 scoring contract + the persisted profile row id."""

    phoneme: str
    position: PhonemePosition
    gop_score: int = Field(ge=0, le=100)
    error_type: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    phoneme_profile_id: uuid.UUID
    child_id: uuid.UUID
