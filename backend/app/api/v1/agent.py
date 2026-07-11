"""Agent-facing endpoints: register, heartbeat, usage."""
import asyncio
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_device
from app.core.security import hash_api_key, hash_password, verify_api_key
from app.db import session as session_mod
from app.models.device import Device
from app.models.device_command import DeviceCommand
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.notification_config import NotificationConfig
from app.models.rule import Rule
from app.models.screenshot import Screenshot
from app.models.toxic_alert import ToxicAlert
from app.models.usage_record import UsageRecord
from app.schemas.agent import (
    HeartbeatRequest,
    HeartbeatResponse,
    RegisterRequest,
    RegisterResponse,
    SyncParentPasswordRequest,
    SyncParentPasswordResponse,
    UsageBatchRequest,
)
from app.services.content_classifier import classify_content
from app.services.resolver import resolve_member_for_device, resolve_rule
from app.services.schedule import now_in_window
from app.services.screenshot_store import save_jpeg
from app.services.toxic_judge import judge_toxic

router = APIRouter(prefix="/agent", tags=["agent"])


def _new_api_key() -> str:
    return secrets.token_urlsafe(32)


async def _resolve_any_device(request: Request, db: AsyncSession) -> Device | None:
    """Look up the calling device by API key without filtering on revoked.

    `current_device` in deps.py hides revoked devices entirely (returning
    None). Some endpoints need to distinguish a bad key (401) from a revoked
    device (403), so this helper includes revoked rows in the candidate set.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    api_key = auth[7:].strip()
    if not api_key or len(api_key) < 8:
        return None
    prefix = api_key[:8]
    stmt = select(Device).where(Device.api_key_prefix == prefix)
    candidates = list((await db.execute(stmt)).scalars())
    for d in candidates:
        if verify_api_key(api_key, d.api_key_hash):
            return d
    return None


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
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
            # Rotate api_key on re-register so a leaked previous key can be
            # invalidated. The plaintext is returned exactly once.
            new_plain = secrets.token_urlsafe(32)
            device.api_key_hash = hash_api_key(new_plain)
            device.api_key_prefix = new_plain[:8]
            await db.commit()
            return RegisterResponse(
                device_id=device.device_id,
                api_key=new_plain,
                family_id=device.family_id,
                member_id=device.member_id,
                message="Re-registered existing device; api_key rotated",
            )

    # Case 2: family_setup_token provided -> join existing family.
    # Token format: "FAM-<family_id>.<base64url-secret>". Secret is verified
    # against the family's hashed setup_token. Without the secret, the token
    # is useless — knowing family_id alone does not grant join.
    family = None
    if req.family_setup_token:
        try:
            from app.core.security import verify_setup_token
            family = await verify_setup_token(db, req.family_setup_token)
        except Exception:
            family = None

    family_was_created = False
    if family is None:
        # Create new family with a default parent. Parent gets a random
        # temporary password returned in the response (one-time) so the
        # /web/login flow has no hard-coded backdoor.
        from app.core.security import mint_setup_token
        setup_token, setup_token_hash = mint_setup_token()
        family = Family(
            name=f"{req.name}'s Family",
            setup_token_hash=setup_token_hash,
        )
        db.add(family)
        await db.commit()
        await db.refresh(family)

        # Mint a per-family unique parent username to avoid cross-family
        # collisions when multiple families coexist in one DB.
        parent_username = f"parent_{family.id}"
        parent_password = secrets.token_urlsafe(12)
        parent = Member(
            family_id=family.id,
            name=parent_username,
            role=MemberRole.PARENT,
            grade=0,
            password_hash=hash_password(parent_password),
        )
        db.add(parent)
        await db.commit()
        await db.refresh(parent)
        # Stash the generated password on the request context so the response
        # can carry it (one-time delivery).
        request.state.initial_parent_password = parent_password
        request.state.initial_setup_token = setup_token
        family_was_created = True

    # If a windows_username was supplied, ensure a child Member exists for it
    if req.windows_username:
        stmt = select(Member).where(
            Member.family_id == family.id,
            Member.windows_username == req.windows_username,
        )
        result = await db.execute(stmt)
        existing_member = result.scalar_one_or_none()
        if existing_member is None:
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

    plain_api_key = _new_api_key()
    device = Device(
        family_id=family.id,
        member_id=member.id if member else None,
        name=req.name,
        device_type=req.device_type,
        device_id=req.device_id or secrets.token_urlsafe(16),
        computer_model=req.computer_model,
        api_key_hash=hash_api_key(plain_api_key),
        api_key_prefix=plain_api_key[:8],
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
        api_key=plain_api_key,
        family_id=device.family_id,
        member_id=device.member_id,
        parent_username=parent.name if family_was_created else None,
        initial_parent_password=getattr(request.state, "initial_parent_password", None),
        family_setup_token=getattr(request.state, "initial_setup_token", None),
        message=msg,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    req: HeartbeatRequest,
    device: Device = Depends(require_device),
    db: AsyncSession = Depends(get_db),
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
    rule_obj = None
    if device.member_id:
        member = await db.get(Member, device.member_id)
        if member:
            rule_obj = await resolve_rule(db, member, username, model)
            if rule_obj:
                rule_dict = {
                    "id": rule_obj.id,
                    "name": rule_obj.name,
                    "daily_limit_minutes": rule_obj.daily_limit_minutes,
                    "monitored_apps": rule_obj.monitored_apps,
                    "bedtime_start": rule_obj.bedtime_start.isoformat() if rule_obj.bedtime_start else None,
                    "bedtime_end": rule_obj.bedtime_end.isoformat() if rule_obj.bedtime_end else None,
                    "default_action": rule_obj.default_action,
                    "time_windows": [
                        {
                            "weekday_mask": w.weekday_mask,
                            "start_time": w.start_time.strftime("%H:%M"),
                            "end_time": w.end_time.strftime("%H:%M"),
                            "action": w.action,
                            "cap_minutes": w.cap_minutes,
                            "priority": w.priority,
                        }
                        for w in sorted(
                            rule_obj.time_windows or [],
                            key=lambda w: (-w.priority, w.id),
                        )
                    ],
                    "questions_per_session": rule_obj.questions_per_session,
                    "max_reward_minutes": rule_obj.max_reward_minutes,
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
                "message": "还剩 5 分钟，请保存进度",
            })

    # ---- PR-A: weekly schedule + queued commands + content gating ----

    # Schedule: if a TimeWindow applies right now and denies or caps, surface
    # the appropriate force_quiz reason BEFORE the daily-limit check above.
    if rule_obj is not None:
        try:
            allowed, cap = now_in_window(rule_obj, now)
        except Exception:
            logger.exception("schedule evaluation failed")
            allowed, cap = True, None
        if not allowed:
            commands.insert(0, {"type": "force_quiz", "reason": "outside_window"})
        elif cap is not None:
            cap_sec = cap * 60
            if req.used_seconds_today >= cap_sec:
                commands.insert(
                    0,
                    {"type": "force_quiz", "reason": "window_cap_exceeded"},
                )

    # ---- Device commands (lock_screen / shutdown / reboot / force_quiz) ----
    # Mark unconsumed+unexpired rows as consumed and append to the response.
    cmd_stmt = select(DeviceCommand).where(
        DeviceCommand.device_id == device.id,
        DeviceCommand.consumed_at.is_(None),
    )
    pending = list((await db.execute(cmd_stmt)).scalars())
    consumed_any = False
    now_naive = now.replace(tzinfo=None)
    for c in pending:
        exp = c.expires_at
        if exp is not None:
            if exp.tzinfo is not None:
                exp = exp.replace(tzinfo=None)
            if exp <= now_naive:
                continue
        cmd_payload = {"type": c.type}
        if c.payload:
            cmd_payload.update(c.payload)
        commands.append(cmd_payload)
        c.consumed_at = now
        consumed_any = True
    if consumed_any:
        await db.commit()

    # ---- Toxicity gating (LLM-flagged content triggers force_quiz) ----
    if req.current_app or req.window_title:
        try:
            cls = await classify_content(
                db, device.family_id, req.current_app or "", req.window_title or ""
            )
        except Exception:
            logger.exception("content classification failed")
            cls = None
        if cls is not None and cls.action == "flag_for_llm":
            try:
                family_id = device.family_id
                member_pk = device.member_id
                app_name = req.current_app or ""
                title = req.window_title or ""

                async def _judge_and_maybe_alert() -> None:
                    try:
                        session_local = getattr(
                            session_mod, "AsyncSessionLocal", None
                        )
                        if session_local is None:
                            return
                        async with session_local() as s2:
                            verdict = await judge_toxic(app_name, title)
                            threshold = 0.7
                            cfg_stmt = select(NotificationConfig).where(
                                NotificationConfig.family_id == family_id
                            )
                            cfg = (await s2.execute(cfg_stmt)).scalar_one_or_none()
                            if cfg and cfg.toxic_alert_threshold is not None:
                                threshold = cfg.toxic_alert_threshold
                            is_toxic = bool(verdict.get("is_toxic"))
                            conf = float(verdict.get("confidence", 0.0))
                            if is_toxic and conf >= threshold:
                                alert = ToxicAlert(
                                    member_id=member_pk,
                                    device_id=device.id,
                                    window_title=title[:500],
                                    app_name=app_name[:255],
                                    category=str(verdict.get("category", "other")),
                                    confidence=conf,
                                    llm_judgment=verdict,
                                    reason=str(verdict.get("reason", ""))[:500],
                                    notified=False,
                                    parent_acknowledged=False,
                                )
                                s2.add(alert)
                                await s2.commit()
                    except Exception:
                        logger.exception("background toxic judge failed")

                asyncio.create_task(_judge_and_maybe_alert())
            except Exception:
                logger.exception("failed to schedule toxic judge task")

    return HeartbeatResponse(
        matched_rule=rule_dict,
        matched_member_id=matched_member_id,
        commands=commands,
        server_time=now,
    )


@router.post("/usage", status_code=201)
async def report_usage(
    req: UsageBatchRequest,
    device: Device = Depends(require_device),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk insert usage records."""
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


# ---- Parent-password cloud sync ----

# Minimum interval between accepted syncs from the same device. Agents push
# every N heartbeats; capping at 1/min keeps a buggy / hostile agent from
# turning this into a write-storm DB pressure.
_PARENT_PW_SYNC_MIN_INTERVAL_SEC = 60


@router.post("/sync-parent-password", response_model=SyncParentPasswordResponse)
async def sync_parent_password(
    req: SyncParentPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SyncParentPasswordResponse:
    """Accept a PBKDF2 verifier from the agent for cloud-side recovery.

    The plaintext password is never transmitted — only (hash, salt, iterations).
    The server stores it per-device; the web UI does not expose it. A future
    feature (re-install recovery) will let the parent authorise a fresh device
    to pull this verifier.
    """
    # Authenticate without the revoked filter so we can distinguish 401 (bad
    # key) from 403 (key valid but device revoked).
    device = await _resolve_any_device(request, db)
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
    if device.revoked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device revoked")

    # SQLite strips tzinfo on read; Postgres preserves it. Normalise so the
    # subtraction below never raises TypeError.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last = device.parent_pw_synced_at
    if last is not None:
        if last.tzinfo is not None:
            last = last.replace(tzinfo=None)
        if (now - last).total_seconds() < _PARENT_PW_SYNC_MIN_INTERVAL_SEC:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="sync too frequent",
                headers={"Retry-After": str(_PARENT_PW_SYNC_MIN_INTERVAL_SEC)},
            )

    device.parent_pw_hash = req.hash
    device.parent_pw_salt = req.salt
    device.parent_pw_iterations = req.iterations
    device.parent_pw_synced_at = now
    await db.commit()
    return SyncParentPasswordResponse(synced_at=now)


# ---- Screenshot ingestion ----
#
# Privacy boundary (architecture §5.3): the v1.0 rule was "no screenshots".
# This endpoint is the deliberate first crack — minimal backend only. There
# is no agent-side capture yet (PR-D) and no parent-side trigger button yet
# (PR-E); the agent can already POST here once those land.

_ALLOWED_TRIGGER_TYPES = frozenset({"parent_now", "scheduled", "auto_toxic"})
# 8 MiB hard cap. A full-HD JPEG rarely exceeds 2 MiB; 8 leaves headroom for
# PNG screenshots from Edge/Chromium without making disk-fill DoS trivial.
_SCREENSHOT_MAX_BYTES = 8 * 1024 * 1024
# Anything smaller than this is almost certainly not a real screenshot —
# reject early so an agent bug doesn't pollute the table with garbage rows.
_SCREENSHOT_MIN_BYTES = 256
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@router.post("/screenshot", status_code=201)
async def upload_screenshot(
    file: UploadFile = File(...),
    trigger_type: str = Form("parent_now"),
    device: Device = Depends(require_device),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept a JPEG/PNG screenshot uploaded by an agent.

    The agent authenticated itself with the device API key (``require_device``);
    the family is therefore whichever family owns that device. Files are written
    under ``settings.screenshots_dir`` keyed by uuid4 (no caller-controlled
    path components), hashed, and recorded in ``device_screenshots``.
    """
    if trigger_type not in _ALLOWED_TRIGGER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid trigger_type"
        )

    payload = await file.read()
    if len(payload) > _SCREENSHOT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="image too large",
        )
    if len(payload) < _SCREENSHOT_MIN_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image too small",
        )
    if not (payload.startswith(_JPEG_MAGIC) or payload.startswith(_PNG_MAGIC)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="not a valid JPEG/PNG",
        )

    rel_path, sha_hex, size = await save_jpeg(
        device.family_id, device.id, payload
    )
    shot = Screenshot(
        family_id=device.family_id,
        device_id=device.id,
        trigger_type=trigger_type,
        bytes_size=size,
        storage_path=rel_path,
        sha256_hex=sha_hex,
    )
    db.add(shot)
    await db.commit()
    await db.refresh(shot)
    return {"id": shot.id, "sha256_hex": sha_hex, "bytes": size}
