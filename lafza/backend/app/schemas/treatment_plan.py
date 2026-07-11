import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PlanAuthor, PlanStatus


class TreatmentPlanCreate(BaseModel):
    child_id: uuid.UUID
    author: PlanAuthor
    goals: list = Field(default_factory=list)
    target_phonemes: list[str] = Field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    approved_by: uuid.UUID | None = None


class TreatmentPlanUpdate(BaseModel):
    goals: list | None = None
    target_phonemes: list[str] | None = None
    status: PlanStatus | None = None
    approved_by: uuid.UUID | None = None


class TreatmentPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    author: PlanAuthor
    goals: list
    target_phonemes: list[str]
    status: PlanStatus
    approved_by: uuid.UUID | None
    created_at: datetime
