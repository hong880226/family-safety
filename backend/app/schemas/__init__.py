"""Pydantic schemas for API request/response."""
from app.schemas.auth import LoginRequest, LoginResponse, TokenPayload
from app.schemas.agent import (
    RegisterRequest,
    RegisterResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    UsageRecordIn,
    UsageBatchRequest,
)
from app.schemas.family import FamilyOut
from app.schemas.member import MemberCreate, MemberUpdate, MemberOut
from app.schemas.device import DeviceOut
from app.schemas.rule import RuleCreate, RuleUpdate, RuleOut, QuizConfigIn, QuizConfigOut
from app.schemas.usage import UsageSummaryOut, DashboardSummaryOut
from app.schemas.content import ContentRuleIn, ContentRuleOut, ToxicAlertOut
from app.schemas.quiz import (
    QuizStartRequest,
    QuizStartResponse,
    QuizQuestionOut,
    QuizSubmitRequest,
    QuizSubmitResponse,
)

__all__ = [
    "LoginRequest", "LoginResponse", "TokenPayload",
    "RegisterRequest", "RegisterResponse",
    "HeartbeatRequest", "HeartbeatResponse",
    "UsageRecordIn", "UsageBatchRequest",
    "FamilyOut",
    "MemberCreate", "MemberUpdate", "MemberOut",
    "DeviceOut",
    "RuleCreate", "RuleUpdate", "RuleOut", "QuizConfigIn", "QuizConfigOut",
    "UsageSummaryOut", "DashboardSummaryOut",
    "ContentRuleIn", "ContentRuleOut", "ToxicAlertOut",
    "QuizStartRequest", "QuizStartResponse", "QuizQuestionOut",
    "QuizSubmitRequest", "QuizSubmitResponse",
]
