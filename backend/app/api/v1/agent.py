"""Agent-facing endpoints: register, heartbeat, usage."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import current_device, require_device, get_db
from app.core.security import hash_api_key, hash_password
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
