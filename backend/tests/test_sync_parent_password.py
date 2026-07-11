"""Tests for POST /api/v1/agent/sync-parent-password.

The agent pushes a PBKDF2 verifier (hash+salt+iterations) so the parent can
recover the password on a fresh install. The endpoint must:
- reject without a valid device API key (401)
- reject revoked devices (403)
- reject empty/too-short fields (422)
- accept a valid sync (200) and persist the verifier
- rate-limit repeats within 60s (429)
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
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
from app.models.family import Family  # noqa: E402


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
async def client(test_engine, monkeypatch):
    """ASGI transport client whose get_db dependency uses our test engine."""

    async def _override_get_db():
        session_local = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_local() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[__import__("app.db.session", fromlist=["get_db"]).get_db] = _override_get_db
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


def _valid_payload():
    return {
        "hash": "aGVsbG8td29ybGQ=",  # base64 'hello-world', 12 chars
        "salt": "AAAAAAAAAAAAAAAAAAAAAA==",  # 16 raw bytes -> 24 base64 chars
        "iterations": 100_000,
    }


# ---- Happy path ----

@pytest.mark.asyncio
async def test_sync_parent_password_happy_path(client, db, live_device):
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=_valid_payload(),
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "synced_at" in body

    # Verify it was persisted.
    await db.refresh(live_device["device"])
    assert live_device["device"].parent_pw_hash == "aGVsbG8td29ybGQ="
    assert live_device["device"].parent_pw_salt == "AAAAAAAAAAAAAAAAAAAAAA=="
    assert live_device["device"].parent_pw_iterations == 100_000
    assert live_device["device"].parent_pw_synced_at is not None


# ---- Auth ----

@pytest.mark.asyncio
async def test_sync_parent_password_requires_auth(client, live_device):
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=_valid_payload(),
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_sync_parent_password_rejects_revoked_device(client, db, live_device):
    live_device["device"].revoked = True
    await db.commit()
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=_valid_payload(),
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 403


# ---- Input validation ----

@pytest.mark.asyncio
async def test_sync_parent_password_rejects_short_salt(client, live_device):
    body = _valid_payload()
    body["salt"] = "short"
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=body,
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sync_parent_password_rejects_low_iterations(client, live_device):
    body = _valid_payload()
    body["iterations"] = 100  # below the 10_000 floor
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=body,
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sync_parent_password_rejects_empty_hash(client, live_device):
    body = _valid_payload()
    body["hash"] = ""
    r = await client.post(
        "/api/v1/agent/sync-parent-password",
        json=body,
        headers={"Authorization": f"Bearer {live_device['api_key']}"},
    )
    assert r.status_code == 422


# ---- Rate limit ----

@pytest.mark.asyncio
async def test_sync_parent_password_rate_limited_within_window(client, live_device):
    headers = {"Authorization": f"Bearer {live_device['api_key']}"}
    r1 = await client.post(
        "/api/v1/agent/sync-parent-password", json=_valid_payload(), headers=headers
    )
    assert r1.status_code == 200, r1.text

    # Immediate second call must be 429 with a Retry-After header.
    r2 = await client.post(
        "/api/v1/agent/sync-parent-password", json=_valid_payload(), headers=headers
    )
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers
