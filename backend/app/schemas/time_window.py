"""TimeWindow request / response schemas."""
from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WindowAction = Literal["allow", "deny", "cap"]


class TimeWindowIn(BaseModel):
    """Inbound payload for create / full-replace of a single time window.

    ``id`` is intentionally absent: the rule-edit endpoint replaces the
    rule's full window list atomically. Server assigns primary keys.
    """

    weekday_mask: int = Field(default=0x7F, ge=0, le=0x7F)
    start_time: time
    end_time: time
    action: WindowAction = "allow"
    cap_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    enabled: bool = True
    priority: int = Field(default=0, ge=-1000, le=1000)


class TimeWindowOut(TimeWindowIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int


class TimeWindowPatch(BaseModel):
    """Partial update of one window's fields. Used by future PATCH endpoints."""

    weekday_mask: int | None = Field(default=None, ge=0, le=0x7F)
    start_time: time | None = None
    end_time: time | None = None
    action: WindowAction | None = None
    cap_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=-1000, le=1000)
