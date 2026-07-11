"""Tests for the web-side remote-command surface (PR-E).

These tests target the parent-facing endpoints that the new devices-page
buttons drive:

  POST /web/devices/{id}/lock-screen
  POST /web/devices/{id}/shutdown   (delay_seconds, default 60, max 3600)
  POST /web/devices/{id}/reboot     (delay_seconds, default 60, max 3600)
  POST /web/devices/{id}/capture-now

Coverage:

- happy path for every endpoint → 302 + a row in ``device_commands``
- delay_seconds out of [0, 3600] → 422
- delay_seconds default (omitted) is 60
- cross-family parent → no command enqueued (the helper is tested directly in
  test_device_commands; here we verify the HTTP path doesn't leak either)
- capture_now emits type=capture_screen with trigger_type=parent_now
- happy-path requires CSRF (no token → 403)
"""
from __future__ import annotations

import os
import re
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Force test env BEFORE importing the app so settings pick it up.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core.config import get_settings  # noqa: E402
from app.core.security import create_access_token, hash_api_key  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.device_command import DeviceCommand  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.member import Member, MemberRole  # noqa: E402


# ---- fixtures & helpers ----


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
        name=f"device-{name}",
        device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_key),
        api_key_prefix=plain_key[:8],
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return family, parent, child, device, plain_key


async def _fetch_csrf(client: httpx.AsyncClient) -> str:
    """Pull a fresh CSRF token from the login form."""
    r = await client.get("/web/login")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    assert m, r.text[:500]
    return m.group(1)


async def _login_parent(client: httpx.AsyncClient, parent: Member) -> str:
    """Inject auth cookie + CSRF for a parent. Returns the CSRF token."""
    token = create_access_token({
        "sub": str(parent.id),
        "family_id": parent.family_id,
        "role": parent.role.value,
    })
    client.cookies.set("auth_token", token)
    csrf = await _fetch_csrf(client)
    return csrf


def _headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


# ---- happy path ----


@pytest.mark.asyncio
async def test_lock_screen_parent_to_own_device(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/lock-screen",
        headers=_headers(csrf),
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
async def test_shutdown_default_delay_is_60(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "shutdown"
    assert cmd.payload.get("delay_seconds") == 60


@pytest.mark.asyncio
async def test_shutdown_accepts_explicit_delay_seconds(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        data={"delay_seconds": "120"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.payload.get("delay_seconds") == 120


@pytest.mark.asyncio
async def test_reboot_accepts_explicit_delay_seconds(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/reboot",
        data={"delay_seconds": "300"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "reboot"
    assert cmd.payload.get("delay_seconds") == 300


@pytest.mark.asyncio
async def test_capture_now_enqueues_capture_screen_command(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/capture-now",
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.type == "capture_screen"
    assert cmd.payload.get("trigger_type") == "parent_now"
    assert cmd.created_by == parent.id


# ---- validation: delay_seconds out of range ----


@pytest.mark.asyncio
async def test_shutdown_delay_over_max_returns_422(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        data={"delay_seconds": "9999"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code == 422, r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalars())
    assert cmds == []


@pytest.mark.asyncio
async def test_shutdown_negative_delay_returns_422(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        data={"delay_seconds": "-1"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code == 422, r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalars())
    assert cmds == []


@pytest.mark.asyncio
async def test_reboot_delay_zero_is_allowed(client, db):
    """0 seconds means "do it now"; legitimate use case for parents in a hurry."""
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/reboot",
        data={"delay_seconds": "0"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text

    cmd = (await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalar_one()
    assert cmd.payload.get("delay_seconds") == 0


@pytest.mark.asyncio
async def test_shutdown_non_numeric_delay_returns_422(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.post(
        f"/web/devices/{device.id}/shutdown",
        data={"delay_seconds": "soon"},
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code == 422, r.text


# ---- cross-family isolation ----


@pytest.mark.asyncio
async def test_capture_now_cross_family_does_not_enqueue(client, db):
    fa, pa, ca, dev_a, _ = await _make_family_with_device(db, name="alpha")
    fb, pb, cb, dev_b, _ = await _make_family_with_device(db, name="beta")

    csrf = await _login_parent(client, pa)
    r = await client.post(
        f"/web/devices/{dev_b.id}/capture-now",
        headers=_headers(csrf),
        follow_redirects=False,
    )
    # Either a 404 or a 303-to-devices-with-warn-toast; both are acceptable.
    # What matters: NO command was enqueued for dev_b.
    assert r.status_code in (302, 303, 404), r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == dev_b.id)
    )).scalars())
    assert cmds == [], "no command must be enqueued for a foreign-family device"


@pytest.mark.asyncio
async def test_lock_screen_cross_family_does_not_enqueue(client, db):
    fa, pa, ca, dev_a, _ = await _make_family_with_device(db, name="alpha")
    fb, pb, cb, dev_b, _ = await _make_family_with_device(db, name="beta")

    csrf = await _login_parent(client, pa)
    r = await client.post(
        f"/web/devices/{dev_b.id}/lock-screen",
        headers=_headers(csrf),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303, 404), r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == dev_b.id)
    )).scalars())
    assert cmds == []


# ---- CSRF guard ----


@pytest.mark.asyncio
async def test_lock_screen_without_csrf_rejected(client, db):
    """A missing/invalid CSRF token must be rejected with 403, and no command
    must be enqueued — the gate is enforced before the DB write."""
    family, parent, child, device, _ = await _make_family_with_device(db)

    # Log in but DO NOT send a CSRF header.
    token = create_access_token({
        "sub": str(parent.id),
        "family_id": parent.family_id,
        "role": parent.role.value,
    })
    client.cookies.set("auth_token", token)

    r = await client.post(
        f"/web/devices/{device.id}/lock-screen",
        follow_redirects=False,
    )
    assert r.status_code == 403, r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalars())
    assert cmds == []


@pytest.mark.asyncio
async def test_capture_now_without_csrf_rejected(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)

    token = create_access_token({
        "sub": str(parent.id),
        "family_id": parent.family_id,
        "role": parent.role.value,
    })
    client.cookies.set("auth_token", token)

    r = await client.post(
        f"/web/devices/{device.id}/capture-now",
        follow_redirects=False,
    )
    assert r.status_code == 403, r.text

    cmds = list((await db.execute(
        select(DeviceCommand).where(DeviceCommand.device_id == device.id)
    )).scalars())
    assert cmds == []


# ---- devices page renders the action column ----


@pytest.mark.asyncio
async def test_devices_page_renders_action_buttons(client, db):
    family, parent, child, device, _ = await _make_family_with_device(db)
    csrf = await _login_parent(client, parent)

    r = await client.get("/web/devices", headers=_headers(csrf))
    assert r.status_code == 200, r.text
    html = r.text
    # Column header + a row of action affordances.
    assert "远程操作" in html
    # Lock-screen + capture-now POSTs are static <form action=...>; check both.
    assert "/lock-screen" in html
    assert "/capture-now" in html
    # Shutdown/reboot are button-driven — only the per-row data attrs are
    # in the rendered HTML; the actual POST URL is built in JS.
    assert 'data-action="shutdown"' in html
    assert 'data-action="reboot"' in html
    assert 'data-shutdown="' in html  # button binding
    # The modal markup + helper must be present.
    assert 'id="shutdownModal"' in html
    assert "showShutdownModal" in html
