"""FastAPI dependencies for shared auth/session concerns."""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.device import Device
from app.models.member import Member


# ---- Device (Agent) auth ----

async def current_device(request: Request, db: AsyncSession = Depends(get_db)) -> Device | None:
    """Resolve the device from Authorization: Bearer <api_key>.

    Implementation: hash lookup by prefix (small set), then bcrypt verify.
    Avoiding a full-table scan on every heartbeat.
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    api_key = auth[7:].strip()
    if not api_key or len(api_key) < 8:
        return None
    from sqlalchemy import select
    from app.core.security import verify_api_key
    from app.core.config import get_settings

    prefix = api_key[:8]
    # Candidate set: all non-revoked devices with this prefix. With
    # 32-char secrets and 8-char prefix, collisions are ~1 in 10^13 so this
    # is effectively a single row.
    stmt = select(Device).where(
        Device.api_key_prefix == prefix,
        Device.revoked.is_(False),
    )
    candidates = list((await db.execute(stmt)).scalars())
    for device in candidates:
        if verify_api_key(api_key, device.api_key_hash):
            # Best-effort usage tracking; ignore failures (don't break request).
            try:
                from datetime import datetime, timezone
                device.last_used_at = datetime.now(timezone.utc)
                await db.commit()
            except Exception:
                await db.rollback()
            return device
    return None


async def require_device(
    request: Request, db: AsyncSession = Depends(get_db),
) -> Device:
    device = await current_device(request, db)
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
    return device


# ---- Parent (web dashboard) auth ----

async def current_member(request: Request, db: AsyncSession = Depends(get_db)) -> Member | None:
    """Resolve the parent member from the auth_token cookie. None if missing/invalid."""
    token = request.cookies.get("auth_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    member = await db.get(Member, int(payload["sub"]))
    if not member:
        return None
    if "family_id" in payload and payload["family_id"] != member.family_id:
        return None
    return member


async def require_parent(
    request: Request, db: AsyncSession = Depends(get_db),
) -> Member:
    member = await current_member(request, db)
    if member is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return member


async def require_parent_or_redirect(
    request: Request, db: AsyncSession = Depends(get_db),
) -> Member:
    member = await current_member(request, db)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="redirect to login",
            headers={"Location": "/web/login"},
        )
    return member


# ---- Backwards-compatible aliases ----
# These names are imported by other modules. They MUST be raw types (not
# Annotated) so FastAPI's response-field introspection doesn't trip on them.
# Routes use the underlying `Depends(...)` calls instead of these aliases.
DBSession = AsyncSession  # type alias only used as annotation sugar
CurrentDevice = Device