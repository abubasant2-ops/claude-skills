import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssessmentType


class AssessmentCreate(BaseModel):
    child_id: uuid.UUID
    type: AssessmentType
    raw_json: dict = Field(default_factory=dict)
    severity: int | None = Field(default=None, ge=0, le=4)
    red_flags: list = Field(default_factory=list)


class AssessmentUpdate(BaseModel):
    raw_json: dict | None = None
    severity: int | None = Field(default=None, ge=0, le=4)
    red_flags: list | None = None


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    type: AssessmentType
    raw_json: dict
    severity: int | None
    red_flags: list
    created_at: datetime
