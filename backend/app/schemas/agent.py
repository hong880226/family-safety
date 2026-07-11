"""Agent-facing schemas (register, heartbeat, usage)."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class RegisterRequest(BaseModel):
    device_id: str | None = Field(
        default=None,
        description="Client-generated UUID. If null, server creates one.",
    )
    name: str = Field(min_length=1, max_length=100, description="Device display name")
    device_type: Literal["windows", "android"] = "windows"
    computer_model: str | None = Field(default=None, max_length=255)
    windows_username: str | None = Field(default=None, max_length=100)
    family_setup_token: str | None = Field(
        default=None,
        description="If provided, joins existing family; else creates new family.",
    )


class RegisterResponse(BaseModel):
    device_id: str
    api_key: str
    family_id: int
    member_id: int | None
    parent_username: str | None = None
    initial_parent_password: str | None = None
    family_setup_token: str | None = None
    message: str


class HeartbeatRequest(BaseModel):
    timestamp: datetime
    windows_username: str | None = None
    computer_model: str | None = None
    current_app: str | None = None
    window_title: str | None = None
    used_seconds_today: int = 0
    used_seconds_this_week: int = 0
    uptime_seconds: int = 0


class HeartbeatResponse(BaseModel):
    matched_rule: dict | None
    matched_member_id: int | None
    commands: list[dict] = Field(default_factory=list)
    server_time: datetime


class UsageRecordIn(BaseModel):
    app_name: str = Field(max_length=255)
    window_title: str | None = Field(default=None, max_length=500)
    start_at: datetime
    end_at: datetime
    duration_seconds: int = Field(ge=0)
    category: str | None = None
    sub_label: str | None = None
    confidence: float | None = None
    is_overtime: bool = False


class UsageBatchRequest(BaseModel):
    records: list[UsageRecordIn] = Field(min_length=1, max_length=500)


class UsageSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_name: str
    category: str
    duration_seconds: int
    start_at: datetime
    end_at: datetime
