"""SubjectMastery update service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_session import QuizSession, QuizStatus
from app.models.subject_mastery import SubjectMastery


async def update_mastery(
    db: AsyncSession, member_id: int, subject: str
) -> SubjectMastery | None:
    """Recompute mastery stats for (member, subject) from last 30 days of quiz data.

    Updates in place (or creates a new row).
    Returns the updated mastery, or None if insufficient data.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = select(QuizSession).where(
        QuizSession.member_id == member_id,
        QuizSession.status == QuizStatus.COMPLETED,
        QuizSession.completed_at >= since,
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    total = 0
    correct = 0
    last_quiz_at: datetime | None = None
    for s in sessions:
        for q in s.questions or []:
            qsubj = q.get("subject") if isinstance(q, dict) else None
            if qsubj != subject:
                continue
            total += 1
            per_q = q.get("result") or {}
            if per_q.get("is_correct"):
                correct += 1
            if s.completed_at and (last_quiz_at is None or s.completed_at > last_quiz_at):
                last_quiz_at = s.completed_at

    if total == 0:
        return None

    accuracy = correct / total
    is_weak = total >= 10 and accuracy < 0.6

    stmt = select(SubjectMastery).where(
        SubjectMastery.member_id == member_id,
        SubjectMastery.subject == subject,
    )
    result = await db.execute(stmt)
    mastery = result.scalar_one_or_none()
    if mastery is None:
        mastery = SubjectMastery(
            member_id=member_id,
            subject=subject,
        )
        db.add(mastery)

    mastery.total_answered = total
    mastery.total_correct = correct
    mastery.accuracy = accuracy
    mastery.last_quiz_at = last_quiz_at
    mastery.is_weak = is_weak
    mastery.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(mastery)
    return mastery


async def get_all_mastery(
    db: AsyncSession, member_id: int
) -> dict[str, dict]:
    """Return all SubjectMastery rows for a member as a dict."""
    stmt = select(SubjectMastery).where(SubjectMastery.member_id == member_id)
    result = await db.execute(stmt)
    out = {}
    for m in result.scalars():
        out[m.subject] = {
            "accuracy": m.accuracy,
            "total": m.total_answered,
            "correct": m.total_correct,
            "is_weak": m.is_weak,
        }
    return out
