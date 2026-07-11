"""Tests for screenshot ingestion + parent viewer (PR-C).

Coverage:
- happy path: agent uploads JPEG → 201, DB row, file on disk
- cross-family isolation: family A's parent cannot read family B's shot
- bad magic bytes → 422
- too small / too large → 422 / 413
- missing device auth → 401
- parent GET /image returns the original bytes
- path-traversal in storage_path is rejected by the store

Privacy boundary: tests never check another family's row even by accident.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
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
from app.models.family import Family  # noqa: E402
from app.models.member import Member, MemberRole  # noqa: E402
from app.models.screenshot import Screenshot  # noqa: E402
from app.services.screenshot_store import open_jpeg, save_jpeg  # noqa: E402


# ---- Minimal valid JPEG (1x1 white pixel). Hand-built so the test has no
# dependency on Pillow. The magic bytes are b"\xff\xd8\xff\xe0..." but we only
# need the SOI marker + enough payload to clear the 256-byte minimum.
def _tiny_jpeg() -> bytes:
    head = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    body = b"\x00" * 300  # pad so we exceed the 256-byte floor
    return head + body + b"\xff\xd9"


def _tiny_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 300 + b"IEND"


@pytest_asyncio.fixture
async def test_engine(tmp_path):
    """Per-test engine + redirected screenshots dir."""
    # The Linux default /var/lib/... doesn't exist on the Windows runner; pin
    # the test root into tmp_path so each test gets an isolated, writable dir.
    get_settings.cache_clear()
    shot_dir = tmp_path / "screenshots"
    shot_dir.mkdir()
    os.environ["SCREENSHOTS_DIR"] = str(shot_dir)
    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine, shot_dir
    await engine.dispose()


@pytest_asyncio.fixture
async def db(test_engine):
    engine, _ = test_engine
    session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_local() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine):
    """ASGI client with get_db overridden to the test engine."""
    engine, _ = test_engine

    async def _override_get_db():
        session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
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
async def live_device(db: AsyncSession):
    """A registered, non-revoked device with a known API key."""
    family = Family(name="Test Family")
    db.add(family)
    await db.commit()
    await db.refresh(family)

    plain_key = f"plain-{uuid.uuid4().hex}"
    device = Device(
        family_id=family.id,
        name="test-device",
        device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_key),
        api_key_prefix=plain_key[:8],
        online=False,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return {"device": device, "api_key": plain_key, "family": family}


def _parent_cookie(parent: Member) -> dict[str, str]:
    """Build the auth_token cookie value for a parent. Mirrors web/routes.py."""
    token = create_access_token({
        "sub": str(parent.id),
        "family_id": parent.family_id,
        "role": parent.role.value,
    })
    return {"auth_token": token}


@pytest_asyncio.fixture
async def two_families(db: AsyncSession):
    """Two families, each with a parent. Returns the relevant ids."""
    fam_a = Family(name="FamA")
    fam_b = Family(name="FamB")
    db.add_all([fam_a, fam_b])
    await db.commit()
    for f in (fam_a, fam_b):
        await db.refresh(f)

    parent_a = Member(family_id=fam_a.id, name="parent_a", role=MemberRole.PARENT)
    parent_b = Member(family_id=fam_b.id, name="parent_b", role=MemberRole.PARENT)
    db.add_all([parent_a, parent_b])
    await db.commit()
    for m in (parent_a, parent_b):
        await db.refresh(m)

    # Each family gets a device + child member, so the upload endpoint can
    # happily bind screenshots to (family, device) in both worlds.
    plain_a = f"plain-a-{uuid.uuid4().hex}"
    plain_b = f"plain-b-{uuid.uuid4().hex}"
    dev_a = Device(
        family_id=fam_a.id, name="dev-a", device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_a), api_key_prefix=plain_a[:8],
    )
    dev_b = Device(
        family_id=fam_b.id, name="dev-b", device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_b), api_key_prefix=plain_b[:8],
    )
    db.add_all([dev_a, dev_b])
    await db.commit()
    for d in (dev_a, dev_b):
        await db.refresh(d)

    return {
        "fam_a": fam_a, "fam_b": fam_b,
        "parent_a": parent_a, "parent_b": parent_b,
        "dev_a": dev_a, "dev_b": dev_b,
        "api_key_a": plain_a, "api_key_b": plain_b,
    }


# ---- Happy path ----

@pytest.mark.asyncio
async def test_upload_screenshot_happy_path(client, db, live_device, test_engine):
    _, shot_dir = test_engine
    payload = _tiny_jpeg()
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", payload, "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sha256_hex"] and len(body["sha256_hex"]) == 64
    assert body["bytes"] == len(payload)
    assert body["id"] > 0

    # DB row exists with the expected family + device linkage.
    from sqlalchemy import select
    stmt = select(Screenshot).where(Screenshot.id == body["id"])
    shot = (await db.execute(stmt)).scalar_one()
    assert shot.family_id == live_device["family"].id
    assert shot.device_id == live_device["device"].id
    assert shot.trigger_type == "parent_now"
    assert shot.bytes_size == len(payload)

    # File exists on disk under {shot_dir}/{family}/{device}/<uuid>.jpg.
    rel = shot.storage_path
    assert (shot_dir / rel).is_file()
    assert (shot_dir / rel).read_bytes() == payload


@pytest.mark.asyncio
async def test_upload_png_accepted(client, live_device):
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.png", _tiny_png(), "image/png")},
        data={"trigger_type": "scheduled"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["bytes"] == len(_tiny_png())


# ---- Auth ----

@pytest.mark.asyncio
async def test_upload_screenshot_requires_auth(client, live_device):
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"trigger_type": "parent_now"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_upload_screenshot_rejects_bad_trigger_type(client, live_device):
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"trigger_type": "invented_reason"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 400


# ---- Payload validation ----

@pytest.mark.asyncio
async def test_upload_rejects_bad_magic_bytes(client, live_device):
    bogus = b"GIF89a" + b"\x00" * 300  # GIF magic, not JPEG/PNG
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.bin", bogus, "application/octet-stream")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_too_small(client, live_device):
    tiny = b"\xff\xd8\xff\xe0"  # JPEG magic but only 4 bytes
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", tiny, "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_too_large(client, live_device):
    # 8 MiB + 1 byte. Avoid allocating the whole buffer where possible: a
    # huge valid-magic prefix + zeros is enough to hit the size check.
    too_big = b"\xff\xd8\xff\xe0" + b"\x00" * (8 * 1024 * 1024 + 1)
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", too_big, "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 413


# ---- Cross-family isolation on the viewer ----

@pytest.mark.asyncio
async def test_parent_in_other_family_cannot_fetch_image(client, two_families):
    # Family A's agent uploads.
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {two_families['api_key_a']}"},
    )
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]

    # Family B's parent tries to fetch — must be 404 (existence is hidden).
    cookies = _parent_cookie(two_families["parent_b"])
    r2 = await client.get(
        f"/web/screenshots/{shot_id}/image",
        cookies=cookies,
        headers={"Accept": "image/jpeg"},
    )
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_image_endpoint_returns_original_bytes(client, two_families):
    payload = _tiny_jpeg()
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", payload, "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {two_families['api_key_a']}"},
    )
    assert r.status_code == 201
    shot_id = r.json()["id"]

    cookies = _parent_cookie(two_families["parent_a"])
    r2 = await client.get(
        f"/web/screenshots/{shot_id}/image",
        cookies=cookies,
        headers={"Accept": "image/jpeg"},
    )
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("image/jpeg")
    assert r2.content == payload
    assert r2.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_unauthenticated_image_request_is_redirected_or_401(client, two_families):
    r = await client.post(
        "/api/v1/agent/screenshot",
        files={"file": ("screen.jpg", _tiny_jpeg(), "image/jpeg")},
        data={"trigger_type": "parent_now"},
        headers={"Authorization": f"Bearer {two_families['api_key_a']}"},
    )
    shot_id = r.json()["id"]
    r2 = await client.get(f"/web/screenshots/{shot_id}/image")
    # require_parent_or_redirect would be 303, but the image endpoint uses
    # require_parent (not the redirect variant) so an unauthenticated browser
    # gets 401, not a redirect loop. Either way: not 200.
    assert r2.status_code in (401, 303)


# ---- Store-level safety: path traversal is rejected ----

@pytest.mark.asyncio
async def test_store_rejects_absolute_storage_path(test_engine):
    _, _shot_dir = test_engine
    with pytest.raises(ValueError):
        await open_jpeg("/etc/passwd")


@pytest.mark.asyncio
async def test_store_rejects_traversal_storage_path(test_engine):
    _, _shot_dir = test_engine
    with pytest.raises(ValueError):
        await open_jpeg("../../etc/passwd")


@pytest.mark.asyncio
async def test_store_rejects_missing_file(test_engine):
    _, _shot_dir = test_engine
    with pytest.raises(FileNotFoundError):
        await open_jpeg("99/99/does-not-exist.jpg")


@pytest.mark.asyncio
async def test_save_jpeg_creates_uuid_named_file(test_engine, live_device):
    """Two consecutive saves must produce different filenames (no overwrite)."""
    _, shot_dir = test_engine
    payload = _tiny_jpeg()
    rel1, sha1, _ = await save_jpeg(
        live_device["family"].id, live_device["device"].id, payload
    )
    rel2, sha2, _ = await save_jpeg(
        live_device["family"].id, live_device["device"].id, payload
    )
    assert rel1 != rel2, "uploads must not collide on filename"
    assert sha1 == sha2  # same bytes -> same hash
    assert (shot_dir / rel1).is_file()
    assert (shot_dir / rel2).is_file()
    # Layout: {family_id}/{device_id}/{uuid}.jpg
    parts = Path(rel1).parts
    assert parts[0] == str(live_device["family"].id)
    assert parts[1] == str(live_device["device"].id)
    assert parts[2].endswith(".jpg")
