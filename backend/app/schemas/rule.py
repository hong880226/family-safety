"""Rule and QuizConfig schemas."""
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.time_window import TimeWindowOut


class RuleBase(BaseModel):
    name: str = "default"
    match_key: str = Field(default="*@*", max_length=255)
    match_priority: int = 0
    daily_limit_minutes: int = Field(default=120, ge=0)
    weekday_limit_minutes: int | None = None
    weekend_limit_minutes: int | None = None
    bedtime_start: time | None = None
    bedtime_end: time | None = None
    monitored_apps: list[str] = Field(default_factory=list)
    blocked_websites: list[str] = Field(default_factory=list)
    # Verdict used when no TimeWindow matches the current time. Default "allow"
    # preserves legacy behaviour (legacy rules had no schedule at all).
    default_action: Literal["allow", "deny"] = "allow"
    questions_per_session: int = Field(default=3, ge=1, le=20)
    reward_ratio: float = Field(default=0.2, ge=0, le=1)
    max_reward_minutes: int = Field(default=20, ge=0)
    enabled: bool = True


class RuleCreate(RuleBase):
    member_id: int


class RuleUpdate(BaseModel):
    name: str | None = None
    match_key: str | None = None
    match_priority: int | None = None
    daily_limit_minutes: int | None = None
    weekday_limit_minutes: int | None = None
    weekend_limit_minutes: int | None = None
    bedtime_start: time | None = None
    bedtime_end: time | None = None
    monitored_apps: list[str] | None = None
    blocked_websites: list[str] | None = None
    default_action: Literal["allow", "deny"] | None = None
    questions_per_session: int | None = None
    reward_ratio: float | None = None
    max_reward_minutes: int | None = None
    enabled: bool | None = None


class RuleOut(RuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    created_at: datetime
    updated_at: datetime


class RuleOutWithWindows(RuleOut):
    """RuleOut variant that eagerly exposes the rule's weekly time windows."""

    windows: list[TimeWindowOut] = Field(default_factory=list)


class QuizConfigIn(BaseModel):
    total_questions: int = Field(default=3, ge=1, le=20)
    difficulty: int = Field(default=3, ge=1, le=5)
    subjects: list[str] = Field(default_factory=lambda: ["math", "chinese"])
    distribution: dict = Field(default_factory=dict)
    distribution_mode: Literal["manual", "auto", "weakness_first"] = "auto"
    auto_weak_threshold: float = Field(default=0.6, ge=0, le=1)
    weak_subjects: list[str] = Field(default_factory=list)


class QuizConfigOut(QuizConfigIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    updated_at: datetime
