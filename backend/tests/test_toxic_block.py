"""Tests for the toxicity gating in /api/v1/agent/heartbeat.

The heartbeat inspects ``current_app`` and ``window_title``, runs the regex
classifier, and on ``action='flag_for_llm'`` schedules an asyncio task that
asks the LLM to judge. When the verdict is "toxic" and confidence ≥ threshold,
the heartbeat:

  * writes a ``ToxicAlert`` row;
  * (this PR-A only verifies the DB write — the force_quiz push via a new
    command happens inside the background task; a follow-up PR may push it
    via a DeviceCommand row instead).

We mock ``judge_toxic`` and assert that:
  * flag_for_llm triggers the background task,
  * non-flag content does NOT trigger,
  * is_toxic=True + conf ≥ threshold → ToxicAlert row inserted,
  * is_toxic=False OR conf < threshold → no alert,
  * LLM exceptions are swallowed (heartbeat still 200).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_api_key  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.member import Member, MemberRole  # noqa: E402
from app.models.notification_config import NotificationConfig  # noqa: E402
from app.models.toxic_alert import ToxicAlert  # noqa: E402


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
async def client(engine, monkeypatch):
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
    # Make the background task in heartbeat() see the same in-memory engine
    # as the request-scoped session. Without this, AsyncSessionLocal() opens
    # a fresh in-memory SQLite that has no tables and the task fails.
    TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # noqa: N806
    monkeypatch.setattr("app.db.session.AsyncSessionLocal", TestSessionLocal)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_family_with_device(db: AsyncSession):
    family = Family(name="toxic-fam")
    db.add(family)
    await db.commit()
    await db.refresh(family)
    parent = Member(family_id=family.id, name="parent", role=MemberRole.PARENT)
    child = Member(family_id=family.id, name="child", role=MemberRole.CHILD, grade=4)
    db.add_all([parent, child])
    await db.commit()
    await db.refresh(parent)
    await db.refresh(child)
    plain_key = f"plain-{uuid.uuid4().hex}"
    device = Device(
        family_id=family.id, member_id=child.id,
        name="dev", device_id=str(uuid.uuid4()),
        api_key_hash=hash_api_key(plain_key),
        api_key_prefix=plain_key[:8],
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return family, parent, child, device, plain_key


def _hb(**over) -> dict:
    body = {
        "timestamp": datetime.now(UTC).isoformat(),
        "windows_username": "child",
        "computer_model": "test",
        "used_seconds_today": 0,
        "used_seconds_this_week": 0,
        "uptime_seconds": 0,
    }
    body.update(over)
    return body


async def _wait_for_alert(db: AsyncSession, device_id: int, expected: int,
                          timeout: float = 2.0) -> list[ToxicAlert]:
    """Poll the alerts table until ``expected`` rows appear (or timeout)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        rows = list((await db.execute(
            select(ToxicAlert).where(ToxicAlert.device_id == device_id)
        )).scalars())
        if len(rows) >= expected:
            return rows
        await asyncio.sleep(0.05)
    return list((await db.execute(
        select(ToxicAlert).where(ToxicAlert.device_id == device_id)
    )).scalars())


# ---- Tests ----


@pytest.mark.asyncio
async def test_heartbeat_flags_toxic_window_and_writes_alert(client, db, monkeypatch):
    """When classify_content returns flag_for_llm and the LLM confirms toxic
    above threshold, a ToxicAlert is written."""
    family, parent, child, device, key = await _make_family_with_device(db)
    cfg = NotificationConfig(family_id=family.id, toxic_alert_threshold=0.7)
    db.add(cfg)
    await db.commit()

    # The regex classifier sees the toxic window title pattern.
    async def fake_judge(*args, **kwargs):
        return {
            "is_toxic": True,
            "category": "violence",
            "confidence": 0.92,
            "reason": "血腥内容",
        }

    monkeypatch.setattr(
        "app.api.v1.agent.judge_toxic", fake_judge,
    )

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_hb(current_app="chrome.exe", window_title="极端血腥暴力片段"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text

    rows = await _wait_for_alert(db, device.id, expected=1)
    assert len(rows) == 1
    assert rows[0].category == "violence"
    assert rows[0].confidence == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_heartbeat_no_alert_when_not_toxic(client, db, monkeypatch):
    family, parent, child, device, key = await _make_family_with_device(db)
    db.add(NotificationConfig(family_id=family.id, toxic_alert_threshold=0.7))
    await db.commit()

    async def fake_judge(*args, **kwargs):
        return {
            "is_toxic": False, "category": "other",
            "confidence": 0.1, "reason": "ok",
        }

    monkeypatch.setattr("app.api.v1.agent.judge_toxic", fake_judge)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_hb(current_app="chrome.exe", window_title="暴力片段"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200

    rows = await _wait_for_alert(db, device.id, expected=0, timeout=1.0)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_heartbeat_no_alert_when_confidence_below_threshold(client, db, monkeypatch):
    family, parent, child, device, key = await _make_family_with_device(db)
    db.add(NotificationConfig(family_id=family.id, toxic_alert_threshold=0.9))
    await db.commit()

    async def fake_judge(*args, **kwargs):
        return {
            "is_toxic": True, "category": "violence",
            "confidence": 0.5, "reason": "borderline",
        }

    monkeypatch.setattr("app.api.v1.agent.judge_toxic", fake_judge)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_hb(current_app="chrome.exe", window_title="暴力片段"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200

    rows = await _wait_for_alert(db, device.id, expected=0, timeout=1.0)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_heartbeat_survives_llm_exception(client, db, monkeypatch):
    """A thrown LLMError must NOT bubble up — heartbeat stays 200."""
    family, parent, child, device, key = await _make_family_with_device(db)
    db.add(NotificationConfig(family_id=family.id, toxic_alert_threshold=0.7))
    await db.commit()

    async def fake_judge(*args, **kwargs):
        raise RuntimeError("LLM is on fire")

    monkeypatch.setattr("app.api.v1.agent.judge_toxic", fake_judge)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_hb(current_app="chrome.exe", window_title="暴力片段"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    # No alert written.
    rows = await _wait_for_alert(db, device.id, expected=0, timeout=0.5)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_heartbeat_skips_llm_when_action_not_flag(client, db, monkeypatch):
    """If classify_content returns action='monitor', the LLM judge must NOT
    be invoked at all."""
    family, parent, child, device, key = await _make_family_with_device(db)
    db.add(NotificationConfig(family_id=family.id, toxic_alert_threshold=0.7))
    await db.commit()

    called = {"n": 0}

    async def fake_judge(*args, **kwargs):
        called["n"] += 1
        return {"is_toxic": True, "confidence": 1.0, "category": "x", "reason": ""}

    monkeypatch.setattr("app.api.v1.agent.judge_toxic", fake_judge)

    r = await client.post(
        "/api/v1/agent/heartbeat",
        json=_hb(current_app="chrome.exe", window_title="普通学习视频"),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200
    # Give the background task a chance to run (it shouldn't).
    await asyncio.sleep(0.2)
    assert called["n"] == 0
    rows = await _wait_for_alert(db, device.id, expected=0, timeout=0.3)
    assert len(rows) == 0
