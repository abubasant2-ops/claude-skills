import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Sex


class ChildCreate(BaseModel):
    guardian_id: uuid.UUID
    dob: date
    sex: Sex
    dialect: str = Field(default="gulf", max_length=16)
    consent_flags: dict = Field(default_factory=dict)

    @field_validator("dob")
    @classmethod
    def dob_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("dob cannot be in the future")
        return v


class ChildUpdate(BaseModel):
    dob: date | None = None
    sex: Sex | None = None
    dialect: str | None = Field(default=None, max_length=16)
    consent_flags: dict | None = None


class ChildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    guardian_id: uuid.UUID
    dob: date
    sex: Sex
    dialect: str
    consent_flags: dict
    created_at: datetime
