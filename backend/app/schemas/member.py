"""Member schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MemberBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    grade: int = Field(default=4, ge=1, le=12)
    windows_username: str | None = None
    avatar: str | None = None


class MemberCreate(MemberBase):
    role: str = "child"
    parent_password: str | None = Field(default=None, min_length=4)


class MemberUpdate(BaseModel):
    name: str | None = None
    grade: int | None = Field(default=None, ge=1, le=12)
    windows_username: str | None = None
    avatar: str | None = None


class MemberOut(MemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    role: str
    created_at: datetime
