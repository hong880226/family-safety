"""Tests for the /health endpoint (legacy alias of /healthz).

The Windows ConfigUI 'test connection' button calls GET /health. The backend
historically only exposed /healthz, so the button always returned 404 even
when the service was up. /health is now a documented alias; both routes
return the same shape.
"""
from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core.config import get_settings  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    get_settings.cache_clear()
    e = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def client(engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.db.session import get_db

    async def _override():
        session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_local() as s:
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


@pytest.mark.asyncio
async def test_healthz_returns_ok(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_health_alias_returns_ok(client):
    """The ConfigUI 'test connection' button calls GET /health."""
    r = await client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_health_and_healthz_return_same_shape(client):
    a = (await client.get("/healthz")).json()
    b = (await client.get("/health")).json()
    assert a.keys() == b.keys()
    assert a["status"] == b["status"] == "ok"
