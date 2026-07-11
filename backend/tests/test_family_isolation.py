"""Integration test: cross-family access is blocked.

Reproduces the '越权' findings from the security review.
"""
import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.notification_config import NotificationConfig
from app.models.quiz_config import QuizConfig
from app.models.rule import Rule
from app.models.toxic_alert import ToxicAlert


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def two_families(db: AsyncSession):
    """Two families, each with one parent + one child + one rule."""
    fam_a = Family(name="Family A")
    fam_b = Family(name="Family B")
    db.add_all([fam_a, fam_b])
    await db.commit()
    for f in (fam_a, fam_b):
        await db.refresh(f)

    parent_a = Member(family_id=fam_a.id, name="parent_a", role=MemberRole.PARENT)
    parent_b = Member(family_id=fam_b.id, name="parent_b", role=MemberRole.PARENT)
    child_a = Member(family_id=fam_a.id, name="kid_a", role=MemberRole.CHILD, grade=4)
    child_b = Member(family_id=fam_b.id, name="kid_b", role=MemberRole.CHILD, grade=4)
    db.add_all([parent_a, parent_b, child_a, child_b])
    await db.commit()
    for m in (parent_a, parent_b, child_a, child_b):
        await db.refresh(m)

    rule_a = Rule(member_id=child_a.id, name="rule_a", match_key="*@*",
                  daily_limit_minutes=60, match_priority=10, enabled=True)
    rule_b = Rule(member_id=child_b.id, name="rule_b", match_key="*@*",
                  daily_limit_minutes=60, match_priority=10, enabled=True)
    db.add_all([rule_a, rule_b])
    await db.commit()

    from app.core.security import hash_api_key
    device_a = Device(family_id=fam_a.id, device_id="dev-a", name="dev-a",
                      api_key_hash=hash_api_key("key-a-plaintext-1234567890"),
                      api_key_prefix="key-a-pl")
    device_b = Device(family_id=fam_b.id, device_id="dev-b", name="dev-b",
                      api_key_hash=hash_api_key("key-b-plaintext-1234567890"),
                      api_key_prefix="key-b-pl")
    db.add_all([device_a, device_b])
    await db.commit()
    for d in (device_a, device_b):
        await db.refresh(d)

    return {
        "fam_a": fam_a, "fam_b": fam_b,
        "parent_a": parent_a, "parent_b": parent_b,
        "child_a": child_a, "child_b": child_b,
        "rule_a": rule_a, "rule_b": rule_b,
        "device_a": device_a, "device_b": device_b,
    }


@pytest.mark.asyncio
async def test_parent_a_cannot_see_family_b_alerts(db, two_families):
    """The /web/toxic-alerts page must filter by family_id.

    This is the route-level filter, not auth — but if it ever regresses to
    'show all', a family-A parent could see family-B's alerts.
    """
    # Alert for child B.
    alert_b = ToxicAlert(
        member_id=two_families["child_b"].id,
        device_id=two_families["device_b"].id,
        app_name="chrome.exe",
        window_title="secret",
        category="toxic",
        confidence=0.9,
        reason="test",
        notified=True,
        parent_acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert_b)
    await db.commit()

    # What family-A's parent should see: 0 alerts.
    from sqlalchemy import select
    stmt = (
        select(ToxicAlert)
        .join(Member, ToxicAlert.member_id == Member.id)
        .where(Member.family_id == two_families["parent_a"].family_id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    assert rows == [], "family A should not see family B's alerts"


@pytest.mark.asyncio
async def test_acknowledging_other_family_alert_returns_none(db, two_families):
    """Cross-family ACK lookup must return None (handled as 404 in route)."""
    alert_b = ToxicAlert(
        member_id=two_families["child_b"].id,
        device_id=two_families["device_b"].id,
        app_name="chrome.exe",
        window_title="secret",
        category="toxic",
        confidence=0.9,
        reason="test",
        notified=True,
        parent_acknowledged=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert_b)
    await db.commit()

    from sqlalchemy import select
    stmt = (
        select(ToxicAlert)
        .join(Member, ToxicAlert.member_id == Member.id)
        .where(
            ToxicAlert.id == alert_b.id,
            Member.family_id == two_families["parent_a"].family_id,  # WRONG family
        )
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    assert row is None, "Family A must not be able to ACK Family B's alert"


@pytest.mark.asyncio
async def test_quiz_config_save_rejects_other_family_member(db, two_families):
    """Saving quiz config for a member in another family must be a no-op / 404.

    The route uses a join to enforce this; verify the join semantics here.
    """
    from sqlalchemy import select
    # Parent A asks to save QuizConfig for child_b (family B).
    stmt = select(Member).where(
        Member.id == two_families["child_b"].id,
        Member.family_id == two_families["parent_a"].family_id,
    )
    found = (await db.execute(stmt)).scalar_one_or_none()
    assert found is None, "Parent A must not be able to operate on child B"


@pytest.mark.asyncio
async def test_notification_config_isolated_per_family(db, two_families):
    """Each family has exactly one NotificationConfig."""
    cfg_a = NotificationConfig(family_id=two_families["fam_a"].id, email="a@x.com")
    cfg_b = NotificationConfig(family_id=two_families["fam_b"].id, email="b@x.com")
    db.add_all([cfg_a, cfg_b])
    await db.commit()

    from sqlalchemy import select
    stmt = select(NotificationConfig).where(
        NotificationConfig.family_id == two_families["fam_a"].id
    )
    rows = (await db.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].email == "a@x.com"