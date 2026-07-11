"""Match a (username, computer_model) pair to a Rule.

Priority (highest first):
  1. exact match (no wildcards)
  2. username wildcard match
  3. model wildcard match
  4. full wildcard fallback
"""
from __future__ import annotations

import fnmatch
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.member import Member
from app.models.rule import Rule


def _score_match(match_key: str, candidate: str) -> int:
    """Lower score = more specific (preferred)."""
    if match_key == candidate:
        return 0
    if "*" not in match_key:
        return 99
    parts = match_key.split("@", 1)
    if len(parts) != 2:
        return 99
    user_part, model_part = parts
    user_wild = "*" in user_part
    model_wild = "*" in model_part
    if user_wild and model_wild:
        return 30
    if user_wild:
        return 20
    if model_wild:
        return 10
    return 99


async def resolve_member_for_device(
    db: AsyncSession, device: Device, windows_username: str | None
) -> Member | None:
    """Find the member who is currently using this device."""
    if windows_username:
        stmt = select(Member).where(
            Member.family_id == device.family_id,
            Member.windows_username == windows_username,
        )
        result = await db.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            return member
    return None


async def resolve_rule(
    db: AsyncSession,
    member: Member,
    windows_username: str | None,
    computer_model: str | None,
) -> Rule | None:
    """Pick the highest-priority rule for this (member, username, model)."""
    if not windows_username:
        windows_username = ""
    if not computer_model:
        computer_model = ""
    match_key = f"{windows_username}@{computer_model}"

    stmt = (
        select(Rule)
        .where(Rule.member_id == member.id, Rule.enabled.is_(True))
        .order_by(Rule.match_priority.desc(), Rule.id.asc())
    )
    result = await db.execute(stmt)
    rules: Iterable[Rule] = result.scalars().all()

    best: tuple[int, Rule] | None = None
    for rule in rules:
        if fnmatch.fnmatch(match_key, rule.match_key):
            score = _score_match(match_key, rule.match_key)
            if best is None or score < best[0]:
                best = (score, rule)

    if best:
        return best[1]
    for rule in rules:
        if rule.match_key == "*@*":
            return rule
    return rules[0] if rules else None
