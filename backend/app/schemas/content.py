"""Content rule + toxic alert schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ContentRuleIn(BaseModel):
    match_type: str = Field(pattern="^(process|window_title|url|domain)$")
    pattern: str = Field(min_length=1, max_length=500)
    category: str
    sub_label: str | None = None
    action: str = Field(default="monitor", pattern="^(monitor|warn|block|flag_for_llm)$")
    enabled: bool = True


class ContentRuleOut(ContentRuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    created_at: datetime


class ToxicAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    device_id: int
    window_title: str
    app_name: str
    category: str
    confidence: float
    reason: str | None
    notified: bool
    parent_acknowledged: bool
    created_at: datetime
