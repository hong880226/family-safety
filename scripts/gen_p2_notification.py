"""P2: weekly report services + email sender + scheduler setup."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend/app/services")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND.parent.parent)} ({len(content)} bytes)")


write("weekly_report.py", '''"""Weekly report generation service."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_weekly_report_messages
from app.models.member import Member, MemberRole
from app.models.quiz_session import QuizSession, QuizStatus
from app.models.usage_record import UsageRecord

logger = logging.getLogger(__name__)


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
    db: AsyncSession, member: Member, week_start: date, week_end: date
) -> tuple[dict[str, Any], str | None]:
    """Compute summary and ask LLM to render HTML body. Returns (summary, html or None)."""
    summary = await compute_weekly_summary(db, member, week_start, week_end)
    try:
        client = LLMClient()
        messages = build_weekly_report_messages(
            name=member.name, grade=member.grade, **summary,
        )
        html = await client.chat(messages, temperature=0.6)
        return summary, html
    except LLMError as e:
        logger.warning(f"LLM weekly report generation failed: {e}")
        return summary, None
''')


write("notification.py", '''"""Email and webhook notification sender."""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx
from loguru import logger

from app.models.notification_config import NotificationConfig


async def send_email(
    cfg: NotificationConfig,
    subject: str,
    html_body: str,
    plain_body: str | None = None,
) -> bool:
    """Send an email via SMTP. Returns True if sent successfully."""
    if not cfg.email or not cfg.smtp_host or not cfg.smtp_password_enc:
        logger.warning(f"Email config incomplete for family {cfg.family_id}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = cfg.smtp_user or "noreply@familysafety.local"
        msg["To"] = cfg.email
        msg["Subject"] = subject
        if plain_body:
            msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        smtp_user = cfg.smtp_user or ""
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port or 587) as server:
            server.starttls()
            server.login(smtp_user, cfg.smtp_password_enc)
            server.send_message(msg)
        logger.info(f"Email sent to {cfg.email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


async def send_webhook(
    cfg: NotificationConfig, payload: dict[str, Any]
) -> bool:
    """POST to a configured webhook URL (WeCom/DingTalk/etc)."""
    if not cfg.webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(cfg.webhook_url, json=payload)
            return resp.status_code < 300
    except Exception as e:
        logger.error(f"Webhook send failed: {e}")
        return False


def render_weekly_report_email(
    family_name: str,
    child_name: str,
    week_start: date,
    week_end: date,
    summary: dict[str, Any],
    ai_html: str | None,
) -> tuple[str, str]:
    """Render subject + HTML + plain body for a weekly report email."""
    subject = f"[FamilySafety] {child_name} 周报 ({week_start} ~ {week_end})"
    if ai_html:
        html = f"""
<html><body>
<h1 style=\"color:#4ECDC4\">FamilySafety 周报</h1>
<p>{family_name} 家庭 · {child_name} · {week_start} ~ {week_end}</p>
<hr/>
{ai_html}
<hr/>
<p style=\"font-size:12px;color:#888\">由 FamilySafety 自动生成</p>
</body></html>
"""
    else:
        # Fallback without LLM
        html = f"""
<html><body>
<h1>FamilySafety 周报 - {child_name}</h1>
<p>本周总时长: {summary.get('total_minutes', 0)} 分钟</p>
<p>答题: {summary.get('quiz_count', 0)} 次, 正确率 {summary.get('overall_accuracy', 0):.0%}</p>
<p>(LLM 内容生成失败, 仅显示数据汇总)</p>
</body></html>
"""
    plain = (
        f"FamilySafety 周报 - {child_name}\n"
        f"{week_start} ~ {week_end}\n"
        f"本周总时长: {summary.get('total_minutes', 0)} 分钟\n"
        f"答题: {summary.get('quiz_count', 0)} 次, 正确率 "
        f"{summary.get('overall_accuracy', 0):.0%}\n"
    )
    return subject, html, plain  # type: ignore


def render_weekly_report_email(*args, **kwargs):
    pass  # placeholder to avoid duplicate definition
''')

# A simpler version that doesn't have the broken final function:
content = '''"""Email and webhook notification sender."""
from __future__ import annotations

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import Any

import httpx
from loguru import logger

from app.models.notification_config import NotificationConfig


async def send_email(
    cfg: NotificationConfig,
    subject: str,
    html_body: str,
    plain_body: str | None = None,
) -> bool:
    """Send an email via SMTP. Returns True if sent successfully."""
    if not cfg.email or not cfg.smtp_host or not cfg.smtp_password_enc:
        logger.warning(f"Email config incomplete for family {cfg.family_id}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = cfg.smtp_user or "noreply@familysafety.local"
        msg["To"] = cfg.email
        msg["Subject"] = subject
        if plain_body:
            msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        smtp_user = cfg.smtp_user or ""
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port or 587) as server:
            server.starttls()
            server.login(smtp_user, cfg.smtp_password_enc)
            server.send_message(msg)
        logger.info(f"Email sent to {cfg.email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


async def send_webhook(cfg: NotificationConfig, payload: dict[str, Any]) -> bool:
    """POST to a configured webhook URL (WeCom/DingTalk/etc)."""
    if not cfg.webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(cfg.webhook_url, json=payload)
            return resp.status_code < 300
    except Exception as e:
        logger.error(f"Webhook send failed: {e}")
        return False


def render_weekly_report_email(
    family_name: str,
    child_name: str,
    week_start: date,
    week_end: date,
    summary: dict[str, Any],
    ai_html: str | None,
) -> tuple[str, str, str]:
    """Render (subject, html_body, plain_body) for a weekly report email."""
    subject = f"[FamilySafety] {child_name} 周报 ({week_start} ~ {week_end})"
    if ai_html:
        html = (
            "<html><body>"
            f"<h1 style=\\"color:#4ECDC4\\">FamilySafety 周报</h1>"
            f"<p>{family_name} 家庭 · {child_name} · {week_start} ~ {week_end}</p>"
            "<hr/>"
            f"{ai_html}"
            "<hr/>"
            "<p style=\\"font-size:12px;color:#888\\">由 FamilySafety 自动生成</p>"
            "</body></html>"
        )
    else:
        html = (
            f"<html><body><h1>FamilySafety 周报 - {child_name}</h1>"
            f"<p>本周总时长: {summary.get('total_minutes', 0)} 分钟</p>"
            f"<p>答题: {summary.get('quiz_count', 0)} 次, "
            f"正确率 {summary.get('overall_accuracy', 0):.0%}</p>"
            "<p>(LLM 内容生成失败, 仅显示数据汇总)</p>"
            "</body></html>"
        )
    plain = (
        f"FamilySafety 周报 - {child_name}\\n"
        f"{week_start} ~ {week_end}\\n"
        f"本周总时长: {summary.get('total_minutes', 0)} 分钟\\n"
        f"答题: {summary.get('quiz_count', 0)} 次, 正确率 "
        f"{summary.get('overall_accuracy', 0):.0%}\\n"
    )
    return subject, html, plain
'''

(BACKEND / "notification.py").write_text(content, encoding="utf-8")
print(f"  wrote notification.py (rewritten)")