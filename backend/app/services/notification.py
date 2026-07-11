"""Email and webhook notification sender."""
from __future__ import annotations

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from typing import Any

import httpx
from loguru import logger

from app.core.security import decrypt_str
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
    password = decrypt_str(cfg.smtp_password_enc)
    if not password:
        logger.error("SMTP password decryption failed family={}", cfg.family_id)
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
            server.login(smtp_user, password)
            server.send_message(msg)
        logger.info(f"Email sent to {cfg.email}: {subject}")
        return True
    except Exception as e:
        logger.exception("Email send failed")
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
            f"<h1 style=\"color:#4ECDC4\">FamilySafety 周报</h1>"
            f"<p>{family_name} 家庭 · {child_name} · {week_start} ~ {week_end}</p>"
            "<hr/>"
            f"{ai_html}"
            "<hr/>"
            "<p style=\"font-size:12px;color:#888\">由 FamilySafety 自动生成</p>"
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
        f"FamilySafety 周报 - {child_name}\n"
        f"{week_start} ~ {week_end}\n"
        f"本周总时长: {summary.get('total_minutes', 0)} 分钟\n"
        f"答题: {summary.get('quiz_count', 0)} 次, 正确率 "
        f"{summary.get('overall_accuracy', 0):.0%}\n"
    )
    return subject, html, plain
