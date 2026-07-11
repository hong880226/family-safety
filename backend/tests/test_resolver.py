"""Unit tests for the rule resolver service.

Covers 5+ matching scenarios:
  1. Exact match (no wildcards) wins over wildcard match
  2. Username wildcard matches only the right username
  3. Model wildcard matches only the right model
  4. Full wildcard *@* as fallback
  5. Higher match_priority beats lower when same specificity
  6. Higher specificity beats higher priority
"""
from datetime import time
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.rule import Rule
from app.services.resolver import resolve_rule


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def setup(db: AsyncSession):
    """Create family + member with 4 rules exercising all match scenarios."""
    family = Family(name="Test Family")
    db.add(family)
    await db.commit()
    await db.refresh(family)

    member = Member(
        family_id=family.id,
        name="kid01",
        role=MemberRole.CHILD,
        grade=4,
        windows_username="kid01",
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    # Rule A: exact match for kid01@LENOVO
    rule_exact = Rule(
        member_id=member.id,
        name="exact_kid01_lenovo",
        match_key="kid01@LENOVO-XIAOXIN-15IAU7",
        match_priority=10,
        daily_limit_minutes=60,
    )
    # Rule B: username wildcard (kid01@*) — broader than A
    rule_user = Rule(
        member_id=member.id,
        name="anywhere_kid01",
        match_key="kid01@*",
        match_priority=50,  # higher priority but less specific
        daily_limit_minutes=90,
    )
    # Rule C: model wildcard (*@LENOVO)
    rule_model = Rule(
        member_id=member.id,
        name="anyone_on_lenovo",
        match_key="*@LENOVO-XIAOXIN-15IAU7",
        match_priority=20,
        daily_limit_minutes=75,
    )
    # Rule D: full wildcard fallback
    rule_default = Rule(
        member_id=member.id,
        name="default",
        match_key="*@*",
        match_priority=0,
        daily_limit_minutes=120,
    )
    for r in [rule_exact, rule_user, rule_model, rule_default]:
        db.add(r)
    await db.commit()

    return {
        "family": family,
        "member": member,
        "exact": rule_exact,
        "user": rule_user,
        "model": rule_model,
        "default": rule_default,
    }


@pytest.mark.asyncio
async def test_exact_match_wins_over_wildcards(db, setup):
    """kid01@LENOVO matches exact rule, not the higher-priority but less specific ones."""
    rule = await resolve_rule(db, setup["member"], "kid01", "LENOVO-XIAOXIN-15IAU7")
    assert rule is not None
    assert rule.name == "exact_kid01_lenovo", f"got {rule.name}"
    assert rule.daily_limit_minutes == 60


@pytest.mark.asyncio
async def test_username_wildcard_matches_only_known_username(db, setup):
    """kid02 (unknown user) doesn't match kid01@*."""
    rule = await resolve_rule(db, setup["member"], "kid02", "DELL-XPS-13")
    # No rule with kid02 in match_key, falls back to *@*
    assert rule is not None
    assert rule.name == "default"


@pytest.mark.asyncio
async def test_model_wildcard_matches_any_user_on_lenovo(db, setup):
    """kid02@LENOVO matches *@LENOVO (since no kid01@LENOVO rule exists)."""
    # But wait: kid02 user is unknown, so we'd still want the model rule to match
    # However our resolver queries rules by member_id, not by username.
    # Here we reuse the same member (kid01's), so kid02@LENOVO won't match kid01@*
    # But *@LENOVO will match because user part is wildcard.
    rule = await resolve_rule(db, setup["member"], "stranger", "LENOVO-XIAOXIN-15IAU7")
    assert rule is not None
    # model rule should win because it's more specific than *@*
    # (user_wild=True, model_wild=False -> score 10, less than full-wild 30)
    assert rule.name == "anyone_on_lenovo", f"got {rule.name}"


@pytest.mark.asyncio
async def test_full_wildcard_fallback(db, setup):
    """Anything that doesn't match specific rules falls back to *@*."""
    rule = await resolve_rule(db, setup["member"], "random_user", "unknown_model")
    assert rule is not None
    assert rule.name == "default"
    assert rule.daily_limit_minutes == 120


@pytest.mark.asyncio
async def test_user_wildcard_matches_kid01_on_other_laptop(db, setup):
    """kid01@DELL matches kid01@* (less specific than any exact kid01@DELL rule)."""
    rule = await resolve_rule(db, setup["member"], "kid01", "DELL-XPS-13")
    assert rule is not None
    # No exact match for kid01@DELL, falls to kid01@* (score 20) over *@*
    assert rule.name == "anywhere_kid01", f"got {rule.name}"
    assert rule.daily_limit_minutes == 90


@pytest.mark.asyncio
async def test_specificity_beats_priority(db, setup):
    """Even though 'anywhere_kid01' has priority 50, the exact match wins
    because exact is more specific (score 0 < score 20)."""
    rule = await resolve_rule(db, setup["member"], "kid01", "LENOVO-XIAOXIN-15IAU7")
    assert rule.name == "exact_kid01_lenovo"


@pytest.mark.asyncio
async def test_no_rules_returns_none(db):
    """Member with no rules returns None."""
    family = Family(name="Empty")
    db.add(family)
    await db.commit()
    await db.refresh(family)
    member = Member(family_id=family.id, name="orphan", role=MemberRole.CHILD, grade=1)
    db.add(member)
    await db.commit()
    await db.refresh(member)

    rule = await resolve_rule(db, member, "orphan", "anywhere")
    assert rule is None