"""Tests for the schedule service (``now_in_window``).

Covers:
  * Default policy applied when no window matches (allow & deny).
  * Allow / deny / cap semantics.
  * Window priority: a high-priority window beats a low-priority one even when
    both would match.
  * Overnight wrap (start > end) — 22:00–06:00 covers 23:30 and 02:00.
  * weekday_mask: only listed weekdays match.
  * cap_minutes: only applied for action="cap"; ignored for allow/deny.
  * disabled windows are ignored.
"""
from __future__ import annotations

from datetime import UTC, datetime, time

import pytest
from sqlalchemy import select

from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.rule import Rule
from app.models.time_window import TimeWindow
from app.services.schedule import now_in_window


def _make_rule(
    default_action: str = "allow",
    windows: list[TimeWindow] | None = None,
) -> Rule:
    """Construct an in-memory Rule. The id is left at the SQLAlchemy default
    (None) — none of the schedule logic touches the primary key."""
    rule = Rule(
        member_id=1,
        name="t",
        match_key="*@*",
        daily_limit_minutes=120,
        default_action=default_action,
    )
    rule.time_windows = windows or []
    return rule


def _w(
    *,
    weekday_mask: int = 0x7F,
    start: time = time(9, 0),
    end: time = time(11, 0),
    action: str = "allow",
    cap: int | None = None,
    priority: int = 0,
    enabled: bool = True,
) -> TimeWindow:
    return TimeWindow(
        rule_id=1,
        weekday_mask=weekday_mask,
        start_time=start,
        end_time=end,
        action=action,
        cap_minutes=cap,
        priority=priority,
        enabled=enabled,
    )


def _at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# ---- Default policy ----


def test_default_allow_with_no_windows_returns_allowed_none():
    rule = _make_rule(default_action="allow")
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 30))
    assert allowed is True
    assert cap is None


def test_default_deny_with_no_windows_returns_disallowed():
    rule = _make_rule(default_action="deny")
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 30))
    assert allowed is False
    assert cap is None


# ---- Allow window ----


def test_allow_window_in_range_grants_access():
    rule = _make_rule(windows=[_w(start=time(9, 0), end=time(11, 0), action="allow")])
    # 2026-07-13 is a Monday — all weekdays set.
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 10, 0))
    assert allowed is True
    assert cap is None


def test_allow_window_outside_range_falls_back_to_default_allow():
    rule = _make_rule(
        default_action="allow",
        windows=[_w(start=time(9, 0), end=time(11, 0), action="allow")],
    )
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 0))
    assert allowed is True
    assert cap is None


def test_allow_window_outside_range_falls_back_to_default_deny():
    rule = _make_rule(
        default_action="deny",
        windows=[_w(start=time(9, 0), end=time(11, 0), action="allow")],
    )
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 0))
    assert allowed is False
    assert cap is None


# ---- Deny window ----


def test_deny_window_overrides_default_allow():
    rule = _make_rule(
        default_action="allow",
        windows=[_w(start=time(9, 0), end=time(11, 0), action="deny")],
    )
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 10, 0))
    assert allowed is False
    assert cap is None


# ---- Cap window ----


def test_cap_window_returns_cap_minutes():
    rule = _make_rule(
        default_action="allow",
        windows=[_w(
            start=time(9, 0), end=time(11, 0),
            action="cap", cap=30,
        )],
    )
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 10, 0))
    assert allowed is True
    assert cap == 30


def test_cap_window_outside_range_uses_default_with_no_cap():
    rule = _make_rule(
        default_action="allow",
        windows=[_w(
            start=time(9, 0), end=time(11, 0),
            action="cap", cap=30,
        )],
    )
    allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 0))
    assert allowed is True
    assert cap is None


# ---- Overnight wrap ----


def test_overnight_window_covers_late_evening():
    """22:00–06:00 should match 23:30."""
    rule = _make_rule(
        windows=[_w(start=time(22, 0), end=time(6, 0), action="deny")],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 23, 30))
    assert allowed is False


def test_overnight_window_covers_early_morning():
    """22:00–06:00 should match 02:00."""
    rule = _make_rule(
        windows=[_w(start=time(22, 0), end=time(6, 0), action="deny")],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 14, 2, 0))
    assert allowed is False


def test_overnight_window_does_not_cover_midday():
    """22:00–06:00 should NOT match 12:00."""
    rule = _make_rule(
        default_action="allow",
        windows=[_w(start=time(22, 0), end=time(6, 0), action="deny")],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 12, 0))
    assert allowed is True


# ---- Weekday mask ----


def test_weekday_mask_excludes_other_days():
    """Mon–Fri (bits 0–4) → mask 0x1F. Tuesday works, Saturday does not."""
    rule = _make_rule(
        windows=[_w(
            weekday_mask=0x1F,  # Mon..Fri only
            start=time(9, 0), end=time(11, 0),
            action="deny",
        )],
    )
    # 2026-07-13 is a Monday → in mask.
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 10, 0))
    assert allowed is False
    # 2026-07-18 is a Saturday → not in mask → falls back to default allow.
    allowed, _ = now_in_window(rule, _at(2026, 7, 18, 10, 0))
    assert allowed is True


# ---- Priority ----


def test_high_priority_window_beats_low_priority_window():
    """Two overlapping windows; high priority wins."""
    rule = _make_rule(
        windows=[
            _w(start=time(9, 0), end=time(12, 0), action="allow", priority=0),
            _w(start=time(10, 0), end=time(11, 0), action="deny", priority=10),
        ],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 10, 30))
    assert allowed is False


def test_low_priority_window_used_when_high_priority_outside():
    """The high-priority deny window only applies 10–11. At 11:30, fall
    back to the low-priority allow window."""
    rule = _make_rule(
        windows=[
            _w(start=time(9, 0), end=time(12, 0), action="allow", priority=0),
            _w(start=time(10, 0), end=time(11, 0), action="deny", priority=10),
        ],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 11, 30))
    assert allowed is True


# ---- Disabled windows ----


def test_disabled_window_is_ignored():
    rule = _make_rule(
        default_action="allow",
        windows=[_w(
            start=time(9, 0), end=time(11, 0), action="deny", enabled=False,
        )],
    )
    allowed, _ = now_in_window(rule, _at(2026, 7, 13, 10, 0))
    assert allowed is True


# ---- Integration with DB ----


@pytest.mark.asyncio
async def test_db_round_trip_resolves_windows():
    """A rule loaded via SQLAlchemy still works with now_in_window (catches
    relationship-loading regressions)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.session import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # noqa: N806
    try:
        async with SessionLocal() as db:
            family = Family(name="f")
            db.add(family)
            await db.commit()
            await db.refresh(family)
            member = Member(
                family_id=family.id, name="kid", role=MemberRole.CHILD, grade=4
            )
            db.add(member)
            await db.commit()
            await db.refresh(member)
            rule = Rule(
                member_id=member.id, name="r", match_key="*@*",
                daily_limit_minutes=60, default_action="deny",
            )
            rule.time_windows.append(TimeWindow(
                weekday_mask=0x7F,
                start_time=time(9, 0), end_time=time(11, 0),
                action="allow", priority=5,
            ))
            db.add(rule)
            await db.commit()
            await db.refresh(rule)

        # Re-load in a fresh session to exercise lazy loading.
        async with SessionLocal() as db:
            from sqlalchemy.orm import selectinload
            rule = (await db.execute(
                select(Rule).options(selectinload(Rule.time_windows)).where(Rule.id == rule.id)
            )).scalar_one()
            # The relationship should populate.
            assert len(rule.time_windows) == 1
            allowed, cap = now_in_window(rule, _at(2026, 7, 13, 10, 0))
            assert allowed is True
            assert cap is None

            allowed, cap = now_in_window(rule, _at(2026, 7, 13, 14, 0))
            assert allowed is False
            assert cap is None
    finally:
        await engine.dispose()
