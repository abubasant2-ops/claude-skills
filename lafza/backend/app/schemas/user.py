import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import UserRole


class UserCreate(BaseModel):
    role: UserRole
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    locale: str = Field(default="ar", max_length=8)
    password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_contact(self) -> "UserCreate":
        if not self.phone and not self.email:
            raise ValueError("either phone or email is required")
        return self


class UserUpdate(BaseModel):
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    locale: str | None = Field(default=None, max_length=8)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    phone: str | None
    email: str | None
    locale: str
    created_at: datetime
