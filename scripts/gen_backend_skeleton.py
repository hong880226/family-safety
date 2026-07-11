"""Generate complete backend skeleton for P1."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")
TESTS = BACKEND / "tests"
ALEMBIC = BACKEND / "alembic" / "versions"

for d in [
    BACKEND / "app" / "api" / "v1",
    BACKEND / "app" / "core",
    BACKEND / "app" / "db",
    BACKEND / "app" / "llm",
    BACKEND / "app" / "models",
    BACKEND / "app" / "schemas",
    BACKEND / "app" / "services",
    TESTS,
    ALEMBIC,
]:
    d.mkdir(parents=True, exist_ok=True)


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ============== requirements.txt ==============
write("requirements.txt", """fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
aiosqlite==0.20.0
alembic==1.14.0
pydantic==2.10.4
pydantic-settings==2.7.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.20
httpx==0.28.1
loguru==0.7.3
redis==5.2.1
apscheduler==3.11.0
""")

write("requirements-dev.txt", """pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
ruff==0.8.4
mypy==1.14.0
""")

# ============== pyproject.toml ==============
write("pyproject.toml", """[project]
name = "familysafety-backend"
version = "0.1.0"
description = "FamilySafety backend service"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "B", "UP", "C4", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
""")


# ============== app/__init__.py ==============
write("app/__init__.py", """\"\"\"FamilySafety backend.\"\"\"
__version__ = "0.1.0"
""")


# ============== app/core/config.py ==============
write("app/core/__init__.py", "")
write("app/core/config.py", """\"\"\"Application settings loaded from environment variables.\"\"\"
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FamilySafety Backend"
    app_version: str = "0.1.0"
    environment: Literal["dev", "test", "prod"] = "dev"
    debug: bool = True

    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(
        default="sqlite+aiosqlite:///./familysafety.db",
        description="Database connection URL (async)",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    jwt_secret: str = Field(default="change-me-in-prod-please-32chars-min")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    llm_base_url: str = Field(default="https://api.deepseek.com/v1")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="deepseek-chat")
    llm_timeout_seconds: int = 30

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
""")


# ============== app/db/session.py ==============
write("app/db/__init__.py", "")
write("app/db/session.py", """\"\"\"Async SQLAlchemy session management.\"\"\"
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    from app.models import (  # noqa: F401  ensure models are registered
        family,
        member,
        device,
        rule,
        quiz_config,
        usage_record,
        quiz_session,
        content_rule,
        toxic_alert,
        subject_mastery,
        suggestion,
        weekly_report,
        notification_config,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
""")


# ============== app/models (one file per model) ==============
write("app/models/__init__.py", """\"\"\"SQLAlchemy ORM models.\"\"\"
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.device import Device
from app.models.rule import Rule
from app.models.quiz_config import QuizConfig, DistributionMode
from app.models.usage_record import UsageRecord
from app.models.quiz_session import QuizSession, QuizStatus
from app.models.content_rule import ContentRule, MatchType, ContentAction, ContentCategory
from app.models.toxic_alert import ToxicAlert
from app.models.subject_mastery import SubjectMastery
from app.models.suggestion import Suggestion, SuggestionType, SuggestionStatus
from app.models.weekly_report import WeeklyReport, PushStatus, PushChannel
from app.models.notification_config import NotificationConfig

__all__ = [
    "Family",
    "Member",
    "MemberRole",
    "Device",
    "Rule",
    "QuizConfig",
    "DistributionMode",
    "UsageRecord",
    "QuizSession",
    "QuizStatus",
    "ContentRule",
    "MatchType",
    "ContentAction",
    "ContentCategory",
    "ToxicAlert",
    "SubjectMastery",
    "Suggestion",
    "SuggestionType",
    "SuggestionStatus",
    "WeeklyReport",
    "PushStatus",
    "PushChannel",
    "NotificationConfig",
]
""")


write("app/models/family.py", """\"\"\"Family model.\"\"\"
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members = relationship("Member", back_populates="family", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="family", cascade="all, delete-orphan")
    notification_config = relationship(
        "NotificationConfig", back_populates="family", uselist=False, cascade="all, delete-orphan"
    )
""")


write("app/models/member.py", """\"\"\"Member (parent or child) model.\"\"\"
import enum
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MemberRole(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[MemberRole] = mapped_column(SAEnum(MemberRole), default=MemberRole.CHILD)
    grade: Mapped[int] = mapped_column(Integer, default=4, comment="1-12, used for quiz difficulty")
    windows_username: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Only for parents")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    family = relationship("Family", back_populates="members")
    rules = relationship("Rule", back_populates="member", cascade="all, delete-orphan")
""")


write("app/models/device.py", """\"\"\"Device (a Windows PC) model.\"\"\"
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), default="windows")
    device_id: Mapped[str] = mapped_column(String(36), unique=True, default=_new_uuid, index=True)
    computer_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    last_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    family = relationship("Family", back_populates="devices")
""")


write("app/models/rule.py", """\"\"\"Rule model with match_key for (username, computer_model) matching.\"\"\"
from datetime import datetime, time

from sqlalchemy import String, Integer, ForeignKey, DateTime, Time, Float, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="default")

    match_key: Mapped[str] = mapped_column(
        String(255), default="*@*",
        comment="Format: <windows_username>@<computer_model>, supports * wildcard",
    )
    match_priority: Mapped[int] = mapped_column(Integer, default=0)

    daily_limit_minutes: Mapped[int] = mapped_column(Integer, default=120)
    weekday_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekend_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    bedtime_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    bedtime_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    monitored_apps: Mapped[list] = mapped_column(JSON, default=list)
    blocked_websites: Mapped[list] = mapped_column(JSON, default=list)

    questions_per_session: Mapped[int] = mapped_column(Integer, default=3)
    reward_ratio: Mapped[float] = mapped_column(Float, default=0.2)
    max_reward_minutes: Mapped[int] = mapped_column(Integer, default=20)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    member = relationship("Member", back_populates="rules")
    quiz_config = relationship(
        "QuizConfig", back_populates="rule", uselist=False, cascade="all, delete-orphan"
    )
""")


write("app/models/quiz_config.py", """\"\"\"QuizConfig: per-rule quiz settings (subjects, difficulty, distribution).\"\"\"
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DistributionMode(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"
    WEAKNESS_FIRST = "weakness_first"


class QuizConfig(Base):
    __tablename__ = "quiz_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("rules.id"), unique=True, index=True
    )

    total_questions: Mapped[int] = mapped_column(Integer, default=3)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, comment="1-5")
    subjects: Mapped[list] = mapped_column(JSON, default=lambda: ["math", "chinese"])
    distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    distribution_mode: Mapped[DistributionMode] = mapped_column(
        SAEnum(DistributionMode), default=DistributionMode.AUTO
    )
    auto_weak_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    weak_subjects: Mapped[list] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rule = relationship("Rule", back_populates="quiz_config")
""")


write("app/models/usage_record.py", """\"\"\"UsageRecord: a chunk of time spent on an app.\"\"\"
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True, index=True)
    member_grade: Mapped[int] = mapped_column(Integer, default=0)

    app_name: Mapped[str] = mapped_column(String(255), index=True)
    window_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    sub_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Integer, default=0.0)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
""")


write("app/models/quiz_session.py", """\"\"\"QuizSession model.\"\"\"
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class QuizStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(50), default="mix")
    grade: Mapped[int] = mapped_column(Integer, default=4)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    reward_minutes: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[QuizStatus] = mapped_column(SAEnum(QuizStatus), default=QuizStatus.PENDING)
    explanations: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
""")


write("app/models/content_rule.py", """\"\"\"Content classification rules.\"\"\"
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MatchType(str, enum.Enum):
    PROCESS = "process"
    WINDOW_TITLE = "window_title"
    URL = "url"
    DOMAIN = "domain"


class ContentCategory(str, enum.Enum):
    GAME_NATIVE = "game_native"
    GAME_WEB = "game_web"
    SHORT_VIDEO = "short_video"
    VIDEO_LONG = "video_long"
    SOCIAL = "social"
    STUDY = "study"
    SEARCH = "search"
    NEWS = "news"
    BROWSER = "browser"
    TOXIC_CONTENT = "toxic_content"
    UNKNOWN = "unknown"


class ContentAction(str, enum.Enum):
    MONITOR = "monitor"
    WARN = "warn"
    BLOCK = "block"
    FLAG_FOR_LLM = "flag_for_llm"


class ContentRule(Base):
    __tablename__ = "content_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)

    match_type: Mapped[MatchType] = mapped_column(SAEnum(MatchType))
    pattern: Mapped[str] = mapped_column(String(500))
    category: Mapped[ContentCategory] = mapped_column(SAEnum(ContentCategory))
    sub_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[ContentAction] = mapped_column(
        SAEnum(ContentAction), default=ContentAction.MONITOR
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
""")


write("app/models/toxic_alert.py", """\"\"\"ToxicAlert: LLM-judged potentially harmful content.\"\"\"
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, Boolean, JSON, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ToxicAlert(Base):
    __tablename__ = "toxic_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    window_title: Mapped[str] = mapped_column(String(500))
    app_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    llm_judgment: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
""")


write("app/models/subject_mastery.py", """\"\"\"Per-member per-subject mastery statistics.\"\"\"
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SubjectMastery(Base):
    __tablename__ = "subject_mastery"
    __table_args__ = (UniqueConstraint("member_id", "subject", name="uq_member_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    subject: Mapped[str] = mapped_column(String(50), index=True)

    total_answered: Mapped[int] = mapped_column(Integer, default=0)
    total_correct: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=1.0)
    last_quiz_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_weak: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
""")


write("app/models/suggestion.py", """\"\"\"LLM-generated suggestions for parents.\"\"\"
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, JSON, Enum as SAEnum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SuggestionType(str, enum.Enum):
    LIMIT = "limit"
    SUBJECTS = "subjects"
    DIFFICULTY = "difficulty"
    ENCOURAGEMENT = "encouragement"
    SCHEDULE = "schedule"


class SuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)

    type: Mapped[SuggestionType] = mapped_column(SAEnum(SuggestionType))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SuggestionStatus] = mapped_column(
        SAEnum(SuggestionStatus), default=SuggestionStatus.PENDING
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
""")


write("app/models/weekly_report.py", """\"\"\"WeeklyReport: weekly digest for parents.\"\"\"
import enum
from datetime import datetime, date

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Date, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PushStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class PushChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    DASHBOARD = "dashboard"


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)

    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)

    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    push_status: Mapped[PushStatus] = mapped_column(
        SAEnum(PushStatus), default=PushStatus.PENDING
    )
    push_channel: Mapped[PushChannel] = mapped_column(
        SAEnum(PushChannel), default=PushChannel.DASHBOARD
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
""")


write("app/models/notification_config.py", """\"\"\"NotificationConfig: how to notify parents (email, webhook).\"\"\"
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), unique=True, index=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)

    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    enable_weekly_email: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_toxic_alert: Mapped[bool] = mapped_column(Boolean, default=True)
    toxic_alert_threshold: Mapped[float] = mapped_column(Integer, default=0.7)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    family = relationship("Family", back_populates="notification_config")
""")


# ============== Schemas ==============
write("app/schemas/__init__.py", """\"\"\"Pydantic schemas for API request/response.\"\"\"
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
""")

# Schemas will be defined in P1 separately
print("\nDone P1 skeleton. Models and config in place.")
print("Schemas and API endpoints will be added next.")