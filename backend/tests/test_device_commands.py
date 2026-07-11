"""Tests for device_commands:

  * Heartbeat picks up unconsumed+unexpired commands.
  * After consumption, the same command is not re-sent.
  * Expired commands are silently skipped.
  * Cross-family parents cannot enqueue commands for another family's device.
  * The web ``/web/devices/{id}/lock-screen|shutdown|reboot`` endpoints enqueue
    with the right ``type`` payload and require CSRF.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Force the test environment BEFORE importing the app so settings pick it up.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_api_key  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.device_command import DeviceCommand  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.member import Member, MemberRole  # noqa: E402

# ---- fixtures ----


@pytest_asyncio.fixture
async def engine():
    get_settings.cache_clear()
    e = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db(engine):
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # noqa: N806
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine):
    from app.db.session import get_db

    async def _override():
        SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # noqa: N806
        async with SessionLocal() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_family_with_device(
    db: AsyncSession, *, name: str = "fam",
) -> tuple[Family, Member, Member, Device, str]:
    family = Family(name=name)
    db.add(family)
    await db.commit()
    await db.refresh(family)

    parent = Member(
        family_id=family.id, name=f"parent-{name}",
        role=MemberRole.PARENT, grade=0,
    )
    child = Member(
        family_id=family.id, name=f"child-{name}",
        role=MemberRole.CHILD, grade=4,
    )
    db.add_all([parent, child])
    await db.commit()
    await db.refresh(parent)
    await db.refresh(child)

    plain_key = f"plain-{uuid.uuid4().hex}"
    device = Device(
        family_id=family.id,
        member_id=child.id,
        name="test-device",
        device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_key),
        api_key_prefix=plain_key[:8],
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return family, parent, child, device, plain_key


def _heartbeat_body(**over) -> dict:
    body = {
        "timestamp": datetime.now(UTC).isoformat(),
        "windows_username": "child",
        "computer_model": "test-model",
        "used_seconds_today": 0,
        "used_seconds_this_week": 0,
        "uptime_seconds": 0,
    }
    body.update(over)
    return body


# ---- Heartbeat delivery ----


@pytest.mark.asyncio
async def test_heartbeat_delivers_unconsumed_command(client, db):
    family, parent, child, device, key = await _make_family_with_device(db)
    cmd = DeviceCommand(
        device_id=device.id, family_id=family.id,
        type="lock_screen", payload={}, created_by=parent.id,
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_heartbeat_body(),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    types = [c["type"] for c in body["commands"]]
    assert "lock_screen" in types, body

    # Reload the row — consumed_at must be set.
    await db.refresh(cmd)
    assert cmd.consumed_at is not None


@pytest.mark.asyncio
async def test_heartbeat_skips_already_consumed_command(client, db):
    family, parent, child, device, key = await _make_family_with_device(db)
    cmd = DeviceCommand(
        device_id=device.id, family_id=family.id,
        type="lock_screen", payload={}, created_by=parent.id,
        consumed_at=datetime.now(UTC),
    )
    db.add(cmd)
    await db.commit()

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_heartbeat_body(),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    types = [c["type"] for c in r.json()["commands"]]
    assert "lock_screen" not in types


@pytest.mark.asyncio
async def test_heartbeat_skips_expired_command(client, db):
    family, parent, child, device, key = await _make_family_with_device(db)
    cmd = DeviceCommand(
        device_id=device.id, family_id=family.id,
        type="shutdown", payload={"delay_seconds": 60},
        created_by=parent.id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_heartbeat_body(),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    body = r.json()
    types = [c["type"] for c in body["commands"]]
    assert "shutdown" not in types


@pytest.mark.asyncio
async def test_heartbeat_payload_is_merged_into_command(client, db):
    """The ``payload`` JSON should be merged into the command dict so the
    agent sees ``type`` AND its extras (delay_seconds, message, ...)."""
    family, parent, child, device, key = await _make_family_with_device(db)
    cmd = DeviceCommand(
        device_id=device.id, family_id=family.id,
        type="shutdown", payload={"delay_seconds": 60, "message": "parent says"},
        created_by=parent.id,
    )
    db.add(cmd)
    await db.commit()

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_heartbeat_body(),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    cmds = [c for c in r.json()["commands"] if c["type"] == "shutdown"]
    assert len(cmds) == 1
    assert cmds[0]["delay_seconds"] == 60
    assert cmds[0]["message"] == "parent says"


# ---- Cross-family isolation ----


@pytest.mark.asyncio
async def test_cannot_enqueue_command_for_other_family_device(db):
    """A DeviceCommand with device_id pointing at another family's device
    must never be created via the web endpoints. We test the helper logic
    directly because the HTTP tests below rely on auth cookies."""
    family_a, parent_a, child_a, dev_a, _ = await _make_family_with_device(
        db, name="a"
    )
    family_b, parent_b, child_b, dev_b, _ = await _make_family_with_device(
        db, name="b"
    )

    # Parent B tries to enqueue against dev_a. The web route's helper raises
    # 404; we mirror that logic here.
    from fastapi import HTTPException

    from app.web.routes import _resolve_parent_device_or_404

    with pytest.raises(HTTPException) as excinfo:
        await _resolve_parent_device_or_404(parent_b, dev_a.id, db)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_only_sees_commands_for_its_own_device(client, db):
    """Device A should not receive commands enqueued for device B."""
    fa, pa, ca, dev_a, key_a = await _make_family_with_device(db, name="alpha")
    fb, pb, cb, dev_b, _ = await _make_family_with_device(db, name="beta")

    cmd_for_b = DeviceCommand(
        device_id=dev_b.id, family_id=fb.id,
        type="lock_screen", payload={}, created_by=pb.id,
    )
    db.add(cmd_for_b)
    await db.commit()

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_heartbeat_body(windows_username=ca.windows_username or "child"),
        headers={"Authorization": f"Bearer {key_a}"},
    )
    assert r.status_code == 200
    types = [c["type"] for c in r.json()["commands"]]
    assert "lock_screen" not in types


# ---- Web routes ----


async def _login_parent(client: httpx.AsyncClient, parent: Member) -> None:
    """Inject the auth_token cookie + CSRF header for a parent login."""
    from app.core.security import create_access_token
    token = create_access_token({
        "sub": str(parent.id),
        "family_id": parent.family_id,
        "role": parent.role.value,
    })
    client.cookies.set("auth_token", token)
    csrf = await _fetch_csrf(client)
    client.headers["X-CSRF-Token"] = csrf


async def _fetch_csrf(client: httpx.AsyncClient) -> str:
    r = await client.get("/web/login")
    # _layout injects csrf via meta; we read the cookie-less login page form
    # token from the html body instead.
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert m, r.text[:500]
    return m.group(1)


@pytest.mark.asyncio
async def test_lock_screen_web_enqueues_command(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    await _login_parent(client, parent)
    r = await client.post(
        f"/web/devices/{device.id}/lock-screen",
        headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "lock_screen"
    assert cmd.family_id == family.id
    assert cmd.created_by == parent.id


@pytest.mark.asyncio
async def test_shutdown_web_enqueues_with_payload(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    await _login_parent(client, parent)
    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "shutdown"
    assert cmd.payload.get("delay_seconds") == 60


@pytest.mark.asyncio
async def test_reboot_web_enqueues_with_payload(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    await _login_parent(client, parent)
    r = await client.post(
        f"/web/devices/{device.id}/reboot",
        headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "reboot"


@pytest.mark.asyncio
async def test_lock_screen_rejects_other_family_device(client, db):
    """Parent A tries to enqueue a command on family B's device."""
    fa, pa, ca, dev_a, _ = await _make_family_with_device(db, name="alpha")
    fb, pb, cb, dev_b, _ = await _make_family_with_device(db, name="beta")

    await _login_parent(client, pa)
    await client.post(
        f"/web/devices/{dev_b.id}/lock-screen",
        headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]},
        follow_redirects=False,
    )
    # 404 (or 303 to /web/devices with warn flash). Either way: no command
    # must be enqueued for dev_b.
    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == dev_b.id)
    )).scalars())
    assert cmds == [], "no command must be enqueued for a foreign-family device"
