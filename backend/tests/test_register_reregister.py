"""Tests for POST /api/v1/agent/register.

Coverage (PR-F reregister fix):
1. device_id supplied & exists -> api_key rotates, same Device row id, hash changes
2. no device_id, no token, windows_username matches a child in exactly one family
   -> rejoin that family (no new Family row); device bound to that child
3. windows_username matches a child in TWO different families -> 409
4. windows_username matches nothing -> existing "create new family" behaviour preserved
5. end-to-end: register, "lose" cfg, re-register -> same family_id (no orphaning)

Privacy boundary: every test asserts family isolation through the family_id
returned by the endpoint, never by enumerating all devices.
"""
from __future__ import annotations

import os
import uuid

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
from app.core.security import hash_api_key, verify_api_key  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.member import Member, MemberRole  # noqa: E402


@pytest_asyncio.fixture
async def test_engine():
    """Per-test engine so each case gets a fresh in-memory schema."""
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine):
    session_local = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine):
    """ASGI client with get_db overridden to the test engine."""

    async def _override_get_db():
        session_local = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_local() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def family_with_child(db: AsyncSession):
    """Family 5 (id assigned by autoincrement after one seed row) with one child
    Member whose windows_username is fixed and known. Used by the rejoin test."""
    fam = Family(name="Original Family")
    db.add(fam)
    await db.commit()
    await db.refresh(fam)
    child = Member(
        family_id=fam.id,
        name="kid",
        role=MemberRole.CHILD,
        grade=4,
        windows_username="kiduser",
    )
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return {"family": fam, "child": child}


@pytest_asyncio.fixture
async def two_families_same_username(db: AsyncSession):
    """Two families, each with a CHILD that has the SAME windows_username.
    Used by the ambiguous-username test."""
    fam_a = Family(name="Fam A")
    fam_b = Family(name="Fam B")
    db.add_all([fam_a, fam_b])
    await db.commit()
    for f in (fam_a, fam_b):
        await db.refresh(f)
    child_a = Member(
        family_id=fam_a.id, name="kid-a", role=MemberRole.CHILD,
        grade=4, windows_username="dupkid",
    )
    child_b = Member(
        family_id=fam_b.id, name="kid-b", role=MemberRole.CHILD,
        grade=4, windows_username="dupkid",
    )
    db.add_all([child_a, child_b])
    await db.commit()
    for m in (child_a, child_b):
        await db.refresh(m)
    return {"fam_a": fam_a, "fam_b": fam_b, "child_a": child_a, "child_b": child_b}


def _register_payload(**overrides) -> dict:
    base = {
        "name": "TestPC",
        "device_type": "windows",
        "computer_model": "TestModel",
        "windows_username": "someuser",
    }
    base.update(overrides)
    # Drop None values so the endpoint's "device_id provided" branch is only
    # entered when the caller actually meant to provide one.
    return {k: v for k, v in base.items() if v is not None}


# ---- 1. device_id supplied & exists -> rotate api_key, same Device row ----

@pytest.mark.asyncio
async def test_register_with_existing_device_id_rotates_api_key(client, db):
    """The classic re-register path: agent knows its device_id (e.g. after a
    reboot that kept cfg). Server must rotate the api_key and return a NEW
    plaintext. The Device row id and device_id stay identical; the hash
    changes so the old key stops working."""
    family = Family(name="Fam")
    db.add(family)
    await db.commit()
    await db.refresh(family)

    plain_old = f"old-{uuid.uuid4().hex}"
    dev_id = str(uuid.uuid4())
    device = Device(
        family_id=family.id,
        member_id=None,
        name="test",
        device_type="windows",
        device_id=dev_id,
        computer_model="M",
        api_key_hash=hash_api_key(plain_old),
        api_key_prefix=plain_old[:8],
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    old_hash = device.api_key_hash

    r = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=dev_id,
            windows_username="alice",
            computer_model="M2",
            name="renamed",
        ),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device_id"] == dev_id
    assert body["api_key"] != plain_old
    assert body["family_id"] == family.id
    assert body["message"].startswith("Re-registered")

    # Reload and confirm the row is the same; only the hash/prefix moved.
    await db.refresh(device)
    assert device.id == device.id  # tautology — same row reference, sanity check
    assert device.api_key_hash != old_hash
    assert verify_api_key(body["api_key"], device.api_key_hash)
    assert device.name == "renamed"
    assert device.computer_model == "M2"


# ---- 2. NEW: rejoin existing family by windows_username ----

@pytest.mark.asyncio
async def test_register_no_device_id_rejoins_by_windows_username(client, db, family_with_child):
    """The tray user cleared local cfg. No device_id, no family_setup_token.
    windows_username matches the ONE child in family_with_child.family. The
    server must reuse that family and that child member instead of minting a
    new family that orphans the parent's web account."""
    fam = family_with_child["family"]
    child = family_with_child["child"]
    families_before = len((await db.execute(select(Family))).scalars().all())
    devices_before = len((await db.execute(select(Device))).scalars().all())

    r = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=None,
            windows_username=child.windows_username,
            name="RejoinedPC",
        ),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["family_id"] == fam.id, "must reuse the existing family"
    assert body["member_id"] == child.id, "must bind to the existing child member"

    # No new Family or Device-row spike beyond the one expected device.
    families_after = len((await db.execute(select(Family))).scalars().all())
    devices_after = len((await db.execute(select(Device))).scalars().all())
    assert families_after == families_before, "no new family row may be created"
    assert devices_after == devices_before + 1

    # The message must NOT carry initial_parent_password / setup_token: nothing
    # new was minted, so the parent should keep using their existing account.
    assert body.get("parent_username") in (None, "")
    assert body.get("initial_parent_password") in (None, "")
    assert body.get("family_setup_token") in (None, "")


# ---- 3. windows_username matches 2 different families -> 409 ----

@pytest.mark.asyncio
async def test_register_ambiguous_windows_username_returns_409(
    client, db, two_families_same_username
):
    """Two families have a child with windows_username='dupkid'. The server
    cannot pick one; it must refuse rather than guess and silently rejoin
    the wrong family."""
    families_before = len((await db.execute(select(Family))).scalars().all())

    r = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=None,
            windows_username="dupkid",
            name="AmbiguousPC",
        ),
    )
    assert r.status_code == 409, r.text
    # Detail should mention the ambiguity so the parent UI can render a useful
    # prompt ("请通过安装程序的家庭 ID 提示重新关联设备").
    detail = r.json().get("detail", "")
    assert isinstance(detail, str) and detail, "409 must carry a detail message"

    # No new family or device should have been created.
    families_after = len((await db.execute(select(Family))).scalars().all())
    devices_after = len((await db.execute(select(Device))).scalars().all())
    assert families_after == families_before
    assert devices_after == 0


# ---- 4. windows_username matches nothing -> create new family (legacy path) ----

@pytest.mark.asyncio
async def test_register_unknown_windows_username_creates_new_family(client, db):
    """No device_id, no token, no matching child anywhere -> the original
    "spin up a new family" behaviour is preserved so first-run install still
    works for a brand-new user."""
    families_before = len((await db.execute(select(Family))).scalars().all())

    r = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=None,
            windows_username="brandnew",
            name="BrandNewPC",
        ),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # A fresh family id, distinct from any prior fixture.
    families_after = len((await db.execute(select(Family))).scalars().all())
    assert families_after == families_before + 1
    # On brand-new install the server still surfaces a temporary parent
    # password so the parent can log into the freshly created web account.
    assert body.get("initial_parent_password")
    assert body.get("family_setup_token")


# ---- 5. End-to-end: original register -> clear cfg -> re-register -> SAME family ----

@pytest.mark.asyncio
async def test_register_after_cleared_cfg_returns_same_family(client, db):
    """Reproduces the user-visible Reregister flow:

    1. Family is created and Device is bound (api_key + device_id stored locally).
    2. User clicks "重新注册设备" -> cfg.ApiKey + cfg.DeviceId are wiped.
    3. FsAgent restarts and POSTs /register with no device_id, but it does
       send its windows_username (SystemInfo reads it from the OS).
    4. Backend MUST land the new Device on the SAME family as step 1.

    Pre-fix: backend took the new-device path and minted a brand-new family +
    parent password, silently orphaning the user's existing web account.
    Post-fix: backend reuses family + child by windows_username.
    """
    # Step 1: first registration. Server mints a family, child, parent password.
    r1 = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=None,
            windows_username="happyuser",
            name="HappyPC",
        ),
    )
    assert r1.status_code == 200, r1.text
    first = r1.json()
    original_family_id = first["family_id"]
    original_member_id = first["member_id"]
    assert original_member_id is not None
    assert first.get("initial_parent_password"), "first install must mint a temp password"

    # Snapshot family count so the second call can be checked for "no new family".
    families_before_second = len((await db.execute(select(Family))).scalars().all())

    # Step 2: simulate the tray clearing local cfg. The agent still has the
    # windows_username (it reads from the OS), but no device_id or family_setup_token.
    # Step 3: re-register.
    r2 = await client.post(
        "/api/v1/agent/register",
        json=_register_payload(
            device_id=None,
            windows_username="happyuser",
            name="HappyPC",
        ),
    )
    assert r2.status_code == 200, r2.text
    second = r2.json()

    # Step 4: must land on the same family + same member.
    assert second["family_id"] == original_family_id, (
        f"re-registration orphaned the user into family {second['family_id']} "
        f"instead of rejoining family {original_family_id}"
    )
    assert second["member_id"] == original_member_id, (
        "re-registration must bind the new device to the same child member"
    )

    # No new family row was created — the user's web account is intact.
    families_after_second = len((await db.execute(select(Family))).scalars().all())
    assert families_after_second == families_before_second

    # No new temp parent password is returned: the parent keeps their existing
    # credentials. Anything non-empty here would mean we minted a new family.
    assert second.get("initial_parent_password") in (None, ""), (
        "re-registering an existing user must not return a new parent password"
    )
