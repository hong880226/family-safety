"""Weekly report generation service."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_weekly_report_messages
from app.models.member import Member, MemberRole
from app.models.quiz_session import QuizSession, QuizStatus
from app.models.usage_record import UsageRecord


async def compute_weekly_summary(
    db: AsyncSession, member: Member, week_start: date, week_end: date
) -> dict[str, Any]:
    """Aggregate this member's data for the given week.

    Returns a dict matching the WeeklyReport.summary schema.
    """
    start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    prev_week_start = week_start - timedelta(days=7)

    # Usage records this week
    stmt = select(UsageRecord).where(
        UsageRecord.member_id == member.id,
        UsageRecord.start_at >= start_dt,
        UsageRecord.start_at <= end_dt,
    )
    result = await db.execute(stmt)
    records = list(result.scalars().all())

    total_seconds = sum(r.duration_seconds for r in records)
    overtime_count = sum(1 for r in records if r.is_overtime)

    # Top apps
    app_seconds: dict[str, int] = defaultdict(int)
    for r in records:
        app_seconds[r.app_name] += r.duration_seconds
    top_apps = sorted(
        [{"app": a, "minutes": s // 60} for a, s in app_seconds.items()],
        key=lambda x: -x["minutes"],
    )[:5]

    # By category
    by_cat: dict[str, int] = defaultdict(int)
    for r in records:
        by_cat[r.category] += r.duration_seconds

    # Last week delta
    stmt = select(UsageRecord).where(
        UsageRecord.member_id == member.id,
        UsageRecord.start_at >= datetime.combine(prev_week_start, datetime.min.time()).replace(tzinfo=timezone.utc),
        UsageRecord.start_at < start_dt,
    )
    result = await db.execute(stmt)
    prev_records = list(result.scalars().all())
    prev_total = sum(r.duration_seconds for r in prev_records)
    delta_minutes = (total_seconds - prev_total) // 60

    # Quiz this week
    stmt = select(QuizSession).where(
        QuizSession.member_id == member.id,
        QuizSession.status == QuizStatus.COMPLETED,
        QuizSession.completed_at >= start_dt,
        QuizSession.completed_at <= end_dt,
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())
    quiz_count = len(sessions)
    quiz_questions = 0
    total_correct = 0
    by_subject_acc: dict[str, list[float]] = defaultdict(list)
    for s in sessions:
        for q in (s.questions or []):
            if not isinstance(q, dict):
                continue
            quiz_questions += 1
            result_data = q.get("result") or {}
            is_corr = bool(result_data.get("is_correct"))
            total_correct += int(is_corr)
            subj = q.get("subject", "unknown")
            by_subject_acc[subj].append(1.0 if is_corr else 0.0)
    overall_accuracy = total_correct / quiz_questions if quiz_questions else 0.0
    by_subject = {
        subj: sum(accs) / len(accs)
        for subj, accs in by_subject_acc.items() if accs
    }

    # Weak subjects (from mastery table; lazy: read here)
    from app.models.subject_mastery import SubjectMastery
    stmt = select(SubjectMastery).where(
        SubjectMastery.member_id == member.id,
        SubjectMastery.is_weak.is_(True),
    )
    result = await db.execute(stmt)
    weak = [m.subject for m in result.scalars()]

    # Toxic alerts (count for the week)
    from app.models.toxic_alert import ToxicAlert
    stmt = select(ToxicAlert).where(
        ToxicAlert.member_id == member.id,
        ToxicAlert.created_at >= start_dt,
        ToxicAlert.created_at <= end_dt,
    )
    result = await db.execute(stmt)
    toxic_alerts_count = len(list(result.scalars()))

    return {
        "total_minutes": total_seconds // 60,
        "delta_minutes": int(delta_minutes),
        "overtime_count": overtime_count,
        "top_apps": top_apps,
        "category_breakdown": {k: v // 60 for k, v in by_cat.items()},
        "quiz_count": quiz_count,
        "quiz_questions": quiz_questions,
        "overall_accuracy": overall_accuracy,
        "by_subject": by_subject,
        "weak_subjects": weak,
        "toxic_alerts_count": toxic_alerts_count,
    }


async def generate_weekly_report_content(
    db: AsyncSession, member: Member, week_start: date, week_end: date,
) -> tuple[dict[str, Any], str | None, str | None]:
    """Compute summary and ask LLM to render HTML body.

    Returns (summary, html, error_reason).
    `error_reason` is non-None only when generation failed; callers should
    surface it on the dashboard so the parent knows why their report is empty.
    """
    summary = await compute_weekly_summary(db, member, week_start, week_end)
    if not summary.get("total_minutes"):
        return summary, None, "本周没有任何使用记录"
    try:
        client = LLMClient()
        messages = build_weekly_report_messages(
            name=member.name, grade=member.grade, **summary,
        )
        html = await client.chat(messages, temperature=0.6)
        if not html:
            return summary, None, "LLM 返回空内容"
        return summary, html, None
    except LLMError as e:
        logger.warning("LLM weekly report generation failed member={} err={}", member.id, e)
        return summary, None, f"AI 生成失败：{e}"
