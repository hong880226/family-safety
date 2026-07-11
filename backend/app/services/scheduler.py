"""Weekly scheduler using APScheduler."""
from __future__ import annotations

from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.notification_config import NotificationConfig
from app.models.weekly_report import WeeklyReport, PushChannel, PushStatus
from app.services.notification import render_weekly_report_email, send_email
from app.services.weekly_report import generate_weekly_report_content


async def _generate_for_member(
    db, family: Family, member: Member, week_start: date, week_end: date
):
    """Generate weekly report for one member; save to DB + try email."""
    summary, html, error = await generate_weekly_report_content(
        db, member, week_start, week_end
    )
    if error:
        logger.warning(
            "weekly report partial generation family={} member={} reason={}",
            family.id, member.id, error,
        )
    report = WeeklyReport(
        family_id=family.id,
        member_id=member.id,
        week_start=week_start,
        week_end=week_end,
        summary={**summary, "generation_error": error} if error else summary,
        ai_content=html,
        push_status=PushStatus.PENDING if html else PushStatus.FAILED,
        push_channel=PushChannel.DASHBOARD,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Try email
    stmt = select(NotificationConfig).where(NotificationConfig.family_id == family.id)
    cfg_res = await db.execute(stmt)
    cfg = cfg_res.scalar_one_or_none()
    if cfg and cfg.enable_weekly_email:
        subject, html_body, plain_body = render_weekly_report_email(
            family_name=family.name,
            child_name=member.name,
            week_start=week_start,
            week_end=week_end,
            summary=summary,
            ai_html=html,
        )
        ok = await send_email(cfg, subject, html_body, plain_body)
        report.push_status = PushStatus.SENT if ok else PushStatus.FAILED
        report.push_channel = PushChannel.EMAIL if ok else PushChannel.DASHBOARD
        await db.commit()


async def weekly_report_job() -> None:
    """Generate weekly reports for all families. Runs Sun 20:00."""
    async with AsyncSessionLocal() as db:
        try:
            today = date.today()
            # Last complete week (Mon-Sun)
            week_end = today - timedelta(days=today.weekday() + 1)
            week_start = week_end - timedelta(days=6)
            logger.info(f"Generating weekly reports for {week_start} ~ {week_end}")

            stmt = select(Family)
            result = await db.execute(stmt)
            families = list(result.scalars().all())
            for family in families:
                stmt = select(Member).where(
                    Member.family_id == family.id,
                    Member.role == MemberRole.CHILD,
                )
                result = await db.execute(stmt)
                for member in result.scalars():
                    try:
                        await _generate_for_member(db, family, member, week_start, week_end)
                    except Exception as e:
                        logger.exception(f"Report for member {member.id} failed: {e}")
        except Exception as e:
            logger.exception(f"Weekly report job failed: {e}")


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """Start the background scheduler (called from FastAPI lifespan)."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        weekly_report_job,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_report",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Background scheduler started (weekly report: Sun 20:00)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
