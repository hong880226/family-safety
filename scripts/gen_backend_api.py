"""Generate schemas and API endpoints for P1."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ============== Schemas ==============
write("app/schemas/auth.py", """\"\"\"Auth schemas.\"\"\"
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    family_id: int | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    member_id: int
    role: str


class TokenPayload(BaseModel):
    sub: str  # member id
    family_id: int
    role: str
    exp: int
""")


write("app/schemas/family.py", """\"\"\"Family schemas.\"\"\"
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
""")


write("app/schemas/member.py", """\"\"\"Member schemas.\"\"\"
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
""")


write("app/schemas/device.py", """\"\"\"Device schemas.\"\"\"
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_id: int
    member_id: int | None
    name: str
    device_type: str
    device_id: str
    computer_model: str | None
    last_username: str | None
    last_seen: datetime | None
    online: bool
    created_at: datetime
""")


write("app/schemas/agent.py", """\"\"\"Agent-facing schemas (register, heartbeat, usage).\"\"\"
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
""")


write("app/schemas/rule.py", """\"\"\"Rule and QuizConfig schemas.\"\"\"
from datetime import datetime, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


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
""")


write("app/schemas/usage.py", """\"\"\"Dashboard summary schemas.\"\"\"
from datetime import date
from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    today_minutes: int
    week_minutes: int
    overtime_count_this_week: int
    top_apps: list[dict]
    last_quiz_at: str | None = None
    current_streak_days: int = 0
    used_vs_limit_percent: float


class UsageSummaryOut(BaseModel):
    date: date
    total_minutes: int
    by_app: list[dict]
    by_category: dict
""")


write("app/schemas/content.py", """\"\"\"Content rule + toxic alert schemas.\"\"\"
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
""")


write("app/schemas/quiz.py", """\"\"\"Quiz session schemas.\"\"\"
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class QuizStartRequest(BaseModel):
    subject: Literal["math", "chinese", "english", "science", "mix"] | None = None


class QuizQuestionOut(BaseModel):
    id: int
    subject: str
    grade: int
    difficulty: int
    question: str
    options: list[str]


class QuizStartResponse(BaseModel):
    token: str
    questions: list[QuizQuestionOut]
    config_used: dict
    expires_in: int = 600


class QuizSubmitRequest(BaseModel):
    token: str
    answers: dict[int, str] = Field(
        description="Map question_id -> chosen option letter (A/B/C/D)"
    )


class QuizSubmitResponse(BaseModel):
    score: int
    total: int
    correct_rate: float
    reward_minutes: int
    explanations: list[str]
    remaining_minutes: int | None = None
""")


# ============== Resolver service ==============
write("app/services/__init__.py", "")
write("app/services/resolver.py", """\"\"\"Match a (username, computer_model) pair to a Rule.

Priority (highest first):
  1. exact match (no wildcards)
  2. username wildcard match
  3. model wildcard match
  4. full wildcard fallback
\"\"\"
from __future__ import annotations

import fnmatch
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.member import Member
from app.models.rule import Rule


def _score_match(match_key: str, candidate: str) -> int:
    \"\"\"Lower score = more specific (preferred).\"\"\"
    if match_key == candidate:
        return 0
    if "*" not in match_key:
        return 99
    parts = match_key.split("@", 1)
    if len(parts) != 2:
        return 99
    user_part, model_part = parts
    user_wild = "*" in user_part
    model_wild = "*" in model_part
    if user_wild and model_wild:
        return 30
    if user_wild:
        return 20
    if model_wild:
        return 10
    return 99


async def resolve_member_for_device(
    db: AsyncSession, device: Device, windows_username: str | None
) -> Member | None:
    \"\"\"Find the member who is currently using this device.\"\"\"
    if windows_username:
        stmt = select(Member).where(
            Member.family_id == device.family_id,
            Member.windows_username == windows_username,
        )
        result = await db.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            return member
    return None


async def resolve_rule(
    db: AsyncSession,
    member: Member,
    windows_username: str | None,
    computer_model: str | None,
) -> Rule | None:
    \"\"\"Pick the highest-priority rule for this (member, username, model).\"\"\"
    if not windows_username:
        windows_username = ""
    if not computer_model:
        computer_model = ""
    match_key = f"{windows_username}@{computer_model}"

    stmt = (
        select(Rule)
        .where(Rule.member_id == member.id, Rule.enabled.is_(True))
        .order_by(Rule.match_priority.desc(), Rule.id.asc())
    )
    result = await db.execute(stmt)
    rules: Iterable[Rule] = result.scalars().all()

    best: tuple[int, Rule] | None = None
    for rule in rules:
        if fnmatch.fnmatch(match_key, rule.match_key):
            score = _score_match(match_key, rule.match_key)
            if best is None or score < best[0]:
                best = (score, rule)

    if best:
        return best[1]
    for rule in rules:
        if rule.match_key == "*@*":
            return rule
    return rules[0] if rules else None
""")


# ============== Auth ==============
write("app/core/security.py", """\"\"\"JWT + password hashing utilities.\"\"\"
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    to_encode = {**payload, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
""")


# ============== API Deps ==============
write("app/api/deps.py", """\"\"\"Common FastAPI dependencies.\"\"\"
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.device import Device


async def get_current_device(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> Device:
    \"\"\"Authenticate Agent by Bearer api_key.\"\"\"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    api_key = authorization.split(" ", 1)[1].strip()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty api key")

    stmt = select(Device).where(Device.api_key == api_key, Device.revoked.is_(False))
    result = await db.execute(stmt)
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid api key")
    return device


async def get_current_member(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    \"\"\"Authenticate parent dashboard user via JWT.\"\"\"
    from app.models.member import Member, MemberRole

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    member_id = int(payload["sub"])
    stmt = select(Member).where(Member.id == member_id)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if not member or member.role != MemberRole.PARENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Parent role required")
    return member


CurrentDevice = Annotated[Device, Depends(get_current_device)]
CurrentMember = Annotated[Member, Depends(get_current_member)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
""")


write("app/api/__init__.py", "")
write("app/api/v1/__init__.py", "")
write("app/api/v1/agent.py", """\"\"\"Agent-facing endpoints: register, heartbeat, usage.\"\"\"
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentDevice, DBSession
from app.models.device import Device
from app.models.member import Member, MemberRole
from app.models.family import Family
from app.models.rule import Rule
from app.models.usage_record import UsageRecord
from app.schemas.agent import (
    HeartbeatRequest,
    HeartbeatResponse,
    RegisterRequest,
    RegisterResponse,
    UsageBatchRequest,
)
from app.services.resolver import resolve_member_for_device, resolve_rule
from sqlalchemy import select

router = APIRouter(prefix="/agent", tags=["agent"])


def _new_api_key() -> str:
    return secrets.token_urlsafe(32)


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, db: DBSession) -> RegisterResponse:
    # Case 1: device_id provided and already exists -> re-register
    if req.device_id:
        stmt = select(Device).where(Device.device_id == req.device_id)
        result = await db.execute(stmt)
        device = result.scalar_one_or_none()
        if device:
            device.name = req.name
            device.computer_model = req.computer_model
            device.last_username = req.windows_username
            device.online = True
            await db.commit()
            return RegisterResponse(
                device_id=device.device_id,
                api_key=device.api_key,
                family_id=device.family_id,
                member_id=device.member_id,
                message="Re-registered existing device",
            )

    # Case 2: family_setup_token provided -> join existing family
    family = None
    if req.family_setup_token:
        # For demo: token format "FAM-{family_id}-{secret}"
        try:
            parts = req.family_setup_token.split("-")
            if len(parts) >= 2 and parts[0] == "FAM":
                fid = int(parts[1])
                stmt = select(Family).where(Family.id == fid)
                result = await db.execute(stmt)
                family = result.scalar_one_or_none()
        except (ValueError, IndexError):
            pass

    if family is None:
        # Create new family with a default parent
        family = Family(name=f"{req.name}'s Family")
        db.add(family)
        await db.commit()
        await db.refresh(family)

        parent = Member(
            family_id=family.id,
            name="家长",
            role=MemberRole.PARENT,
            grade=0,
        )
        db.add(parent)
        await db.commit()
        await db.refresh(parent)

        # Try to auto-link to a child member by windows_username
        if req.windows_username:
            child = Member(
                family_id=family.id,
                name=req.windows_username,
                role=MemberRole.CHILD,
                grade=4,
                windows_username=req.windows_username,
            )
            db.add(child)
            await db.commit()
            await db.refresh(child)

            default_rule = Rule(
                member_id=child.id,
                name="default",
                match_key=f"{req.windows_username}@{req.computer_model or '*'}",
                match_priority=10,
                daily_limit_minutes=120,
            )
            db.add(default_rule)
            await db.commit()

    # Try to resolve member
    member = None
    if req.windows_username:
        stmt = select(Member).where(
            Member.family_id == family.id,
            Member.windows_username == req.windows_username,
            Member.role == MemberRole.CHILD,
        )
        result = await db.execute(stmt)
        member = result.scalar_one_or_none()

    device = Device(
        family_id=family.id,
        member_id=member.id if member else None,
        name=req.name,
        device_type=req.device_type,
        device_id=req.device_id or secrets.token_urlsafe(16),
        computer_model=req.computer_model,
        api_key=_new_api_key(),
        last_username=req.windows_username,
        online=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    msg = (
        f"Registered new device. Family #{family.id} created."
        if not req.family_setup_token
        else f"Joined family #{family.id}."
    )

    return RegisterResponse(
        device_id=device.device_id,
        api_key=device.api_key,
        family_id=device.family_id,
        member_id=device.member_id,
        message=msg,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    req: HeartbeatRequest,
    device: CurrentDevice,
    db: DBSession,
) -> HeartbeatResponse:
    now = datetime.now(timezone.utc)
    device.last_seen = now
    device.online = True

    username = req.windows_username or device.last_username
    model = req.computer_model or device.computer_model

    if username and username != device.last_username:
        device.last_username = username
        member = await resolve_member_for_device(db, device, username)
        if member:
            device.member_id = member.id

    rule_dict = None
    matched_member_id = device.member_id
    if device.member_id:
        member = await db.get(Member, device.member_id)
        if member:
            rule = await resolve_rule(db, member, username, model)
            if rule:
                rule_dict = {
                    "id": rule.id,
                    "name": rule.name,
                    "daily_limit_minutes": rule.daily_limit_minutes,
                    "monitored_apps": rule.monitored_apps,
                    "bedtime_start": rule.bedtime_start.isoformat() if rule.bedtime_start else None,
                    "bedtime_end": rule.bedtime_end.isoformat() if rule.bedtime_end else None,
                    "questions_per_session": rule.questions_per_session,
                    "max_reward_minutes": rule.max_reward_minutes,
                }

    await db.commit()

    commands: list[dict] = []
    if rule_dict:
        limit_sec = rule_dict["daily_limit_minutes"] * 60
        if req.used_seconds_today >= limit_sec:
            commands.append({"type": "force_quiz", "reason": "overtime"})
        elif limit_sec - req.used_seconds_today <= 300 and req.used_seconds_today > 0:
            commands.append({
                "type": "show_warning",
                "message": f"还剩 5 分钟，请保存进度",
            })

    return HeartbeatResponse(
        matched_rule=rule_dict,
        matched_member_id=matched_member_id,
        commands=commands,
        server_time=now,
    )


@router.post("/usage", status_code=201)
async def report_usage(
    req: UsageBatchRequest,
    device: CurrentDevice,
    db: DBSession,
) -> dict:
    \"\"\"Bulk insert usage records.\"\"\"
    inserted = 0
    for rec in req.records:
        record = UsageRecord(
            device_id=device.id,
            member_id=device.member_id,
            member_grade=0,
            app_name=rec.app_name,
            window_title=rec.window_title,
            category=rec.category or "unknown",
            sub_label=rec.sub_label,
            confidence=rec.confidence or 0.0,
            start_at=rec.start_at,
            end_at=rec.end_at,
            duration_seconds=rec.duration_seconds,
            is_overtime=rec.is_overtime,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(record)
        inserted += 1
    await db.commit()
    return {"inserted": inserted}
""")


# ============== Main app ==============
write("app/main.py", """\"\"\"FastAPI application entry.\"\"\"
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import agent
from app.core.config import get_settings
from app.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": settings.app_version}


@app.get("/readyz")
async def readyz() -> dict:
    from sqlalchemy import text
    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as e:
        return {"status": "not_ready", "error": str(e)}


app.include_router(agent.router, prefix=settings.api_v1_prefix)
""")


write(".env.example", """# FamilySafety backend environment
ENVIRONMENT=dev
DEBUG=true

DATABASE_URL=sqlite+aiosqlite:///./familysafety.db
# For production: postgresql+asyncpg://user:pass@host:5432/dbname
REDIS_URL=redis://localhost:6379/0

JWT_SECRET=change-me-please-this-is-not-secure-32chars
JWT_EXPIRE_MINUTES=10080

# LLM (any OpenAI-compatible endpoint)
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-key-here
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=30

CORS_ORIGINS=["*"]
""")


print("\nSchemas + API + Main generated.")
print("Verifying everything imports together...")

import subprocess
result = subprocess.run(
    ["python", "smoke_test.py"],
    cwd=str(BACKEND),
    capture_output=True,
    text=True,
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    raise SystemExit(1)