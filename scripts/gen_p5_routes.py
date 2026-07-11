"""P5: web routes (Jinja2 + form posts)."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend/app/web")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND.parent.parent)} ({len(content)} bytes)")


write("routes.py", '''"""Server-rendered dashboard routes.

Session cookie auth (simple). For v0.1: cookie holds signed JWT.
"""
from __future__ import annotations

import io
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.models.content_rule import ContentRule
from app.models.device import Device
from app.models.family import Family
from app.models.member import Member, MemberRole
from app.models.notification_config import NotificationConfig
from app.models.rule import Rule
from app.models.quiz_config import QuizConfig
from app.models.subject_mastery import SubjectMastery
from app.models.suggestion import Suggestion, SuggestionStatus
from app.models.toxic_alert import ToxicAlert
from app.models.usage_record import UsageRecord
from app.models.weekly_report import WeeklyReport
from app.services.mastery import get_all_mastery

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/web", tags=["web"])


def _app_version() -> str:
    try:
        from app import __version__
        return __version__
    except Exception:
        return "0.1.0"


def _current_member(request: Request, db: AsyncSession) -> Member | None:
    """Get current parent from session cookie."""
    token = request.cookies.get("auth_token")
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    # Sync query via run_sync
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Member).where(Member.id == int(payload["sub"]))
            r = await s.execute(stmt)
            return r.scalar_one_or_none()
    import asyncio
    return asyncio.run(_fetch())


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Login: find a parent member whose password_hash matches.

    v0.1 simplified: any parent whose name == username; no password hashing yet.
    For real use, set parent_password at member creation.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine
    from app.core.security import verify_password

    async def _do():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Member).where(
                Member.role == MemberRole.PARENT,
                Member.name == username,
            )
            r = await s.execute(stmt)
            return r.scalar_one_or_none()

    import asyncio
    member = asyncio.run(_do())
    if not member:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "用户名不存在"},
            status_code=401,
        )
    # For v0.1 demo: accept any password if parent has no hash set
    if member.password_hash:
        if not verify_password(password, member.password_hash):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "密码错误"},
                status_code=401,
            )
    elif password != "admin":
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "默认密码是 admin（首次登录）"},
            status_code=401,
        )

    token = create_access_token({
        "sub": str(member.id),
        "family_id": member.family_id,
        "role": member.role.value if hasattr(member.role, "value") else str(member.role),
    })
    resp = RedirectResponse("/web/dashboard", status_code=302)
    resp.set_cookie("auth_token", token, httponly=True, max_age=7 * 24 * 3600)
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("auth_token")
    return resp


# ============ Pages ============

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch_summary():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            family_id = member.family_id
            today = date.today()
            today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            week_start = today_start - timedelta(days=today.weekday())

            stmt = select(UsageRecord).where(
                UsageRecord.member_id == member.id,
                UsageRecord.start_at >= week_start,
            )
            records = list((await s.execute(stmt)).scalars())
            today_minutes = sum(
                r.duration_seconds for r in records
                if r.start_at >= today_start
            ) // 60
            week_minutes = sum(r.duration_seconds for r in records) // 60
            overtime_count = sum(1 for r in records if r.is_overtime)

            app_seconds: dict[str, int] = {}
            cat_seconds: dict[str, int] = {}
            for r in records:
                app_seconds[r.app_name] = app_seconds.get(r.app_name, 0) + r.duration_seconds
                cat_seconds[r.category] = cat_seconds.get(r.category, 0) + r.duration_seconds

            top_apps = sorted(
                [{"name": a, "minutes": s // 60, "percent": 0} for a, s in app_seconds.items()],
                key=lambda x: -x["minutes"]
            )[:5]
            if top_apps:
                mx = max(a["minutes"] for a in top_apps)
                for a in top_apps:
                    a["percent"] = int(a["minutes"] * 100 / mx) if mx else 0

            cat_total = sum(cat_seconds.values()) or 1
            category_breakdown = {k: v // 60 for k, v in cat_seconds.items()}
            category_pct = {k: int(v * 100 / cat_total) for k, v in cat_seconds.items()}

            daily_limit = 120
            stmt = select(Rule).where(Rule.member_id == member.id, Rule.enabled.is_(True))
            rule = (await s.execute(stmt)).scalars().first()
            if rule:
                daily_limit = rule.daily_limit_minutes

            return {
                "today_minutes": today_minutes,
                "week_minutes": week_minutes,
                "overtime_count_this_week": overtime_count,
                "top_apps": top_apps,
                "category_breakdown": category_breakdown,
                "category_pct": category_pct,
                "daily_limit": daily_limit,
                "used_vs_limit_percent": min(100, int(today_minutes * 100 / daily_limit)),
                "last_quiz_at": None,
                "quiz_summary": None,
            }

    summary = asyncio.run(_fetch_summary())
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "summary": summary,
        "version": _app_version(),
        "active": "dashboard",
    })


@router.get("/members", response_class=HTMLResponse)
async def members_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Member).where(Member.family_id == member.family_id)
            return list((await s.execute(stmt)).scalars())

    members = asyncio.run(_fetch())
    return templates.TemplateResponse("members.html", {
        "request": request,
        "members": members,
        "version": _app_version(),
    })


@router.post("/members")
async def members_add(
    request: Request,
    name: str = Form(...),
    grade: int = Form(4),
    windows_username: str = Form(""),
):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _add():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            new_m = Member(
                family_id=member.family_id,
                name=name,
                role=MemberRole.CHILD,
                grade=grade,
                windows_username=windows_username or None,
            )
            s.add(new_m)
            await s.commit()

    asyncio.run(_add())
    return RedirectResponse("/web/members", status_code=302)


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Device).where(Device.family_id == member.family_id)
            devices = list((await s.execute(stmt)).scalars())
            # member name lookup
            out = []
            for d in devices:
                name = ""
                if d.member_id:
                    m = await s.get(Member, d.member_id)
                    if m: name = m.name
                out.append({
                    "id": d.id, "name": d.name, "computer_model": d.computer_model,
                    "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                    "online": d.online, "member_name": name,
                })
            return out

    devices = asyncio.run(_fetch())
    return templates.TemplateResponse("devices.html", {
        "request": request, "devices": devices, "version": _app_version(),
    })


@router.post("/devices/{device_id}/delete")
async def devices_delete(device_id: int, request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _del():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            d = await s.get(Device, device_id)
            if d and d.family_id == member.family_id:
                d.revoked = True
                await s.commit()

    asyncio.run(_del())
    return RedirectResponse("/web/devices", status_code=302)


@router.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Rule).where(Rule.member_id.in_(
                select(Member.id).where(Member.family_id == member.family_id)
            ))
            rules = list((await s.execute(stmt)).scalars())
            out = []
            for r in rules:
                m = await s.get(Member, r.member_id)
                out.append({
                    "id": r.id, "name": r.name, "match_key": r.match_key,
                    "daily_limit_minutes": r.daily_limit_minutes,
                    "questions_per_session": r.questions_per_session,
                    "enabled": r.enabled,
                    "member_name": m.name if m else "—",
                })
            return out

    rules = asyncio.run(_fetch())
    return templates.TemplateResponse("rules.html", {
        "request": request, "rules": rules, "version": _app_version(),
    })


@router.get("/quiz-config", response_class=HTMLResponse)
async def quiz_config_page(request: Request, member_id: int | None = None):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Member).where(Member.family_id == member.family_id, Member.role == MemberRole.CHILD)
            children = list((await s.execute(stmt)).scalars())
            if not member_id or member_id not in [c.id for c in children]:
                return children, None, None
            target = next(c for c in children if c.id == member_id)
            stmt = select(Rule).where(Rule.member_id == target.id, Rule.enabled.is_(True))
            rule = (await s.execute(stmt)).scalars().first()
            cfg = None
            if rule:
                stmt = select(QuizConfig).where(QuizConfig.rule_id == rule.id)
                cfg = (await s.execute(stmt)).scalar_one_or_none()
                if not cfg:
                    cfg = QuizConfig(rule_id=rule.id)
                    s.add(cfg)
                    await s.commit()
                    await s.refresh(cfg)
            return children, target, cfg

    children, target, cfg = asyncio.run(_fetch())
    return templates.TemplateResponse("quiz_config.html", {
        "request": request, "members": children, "member": target, "cfg": cfg,
        "version": _app_version(),
    })


@router.post("/quiz-config")
async def quiz_config_save(
    request: Request,
    member_id: int = Form(...),
    total_questions: int = Form(3),
    difficulty: int = Form(3),
    subjects: str = Form("math,chinese"),
    distribution_mode: str = Form("auto"),
):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _save():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Rule).where(Rule.member_id == member_id, Rule.enabled.is_(True))
            rule = (await s.execute(stmt)).scalars().first()
            if not rule: return
            stmt = select(QuizConfig).where(QuizConfig.rule_id == rule.id)
            cfg = (await s.execute(stmt)).scalar_one_or_none()
            if not cfg:
                cfg = QuizConfig(rule_id=rule.id)
                s.add(cfg)
            cfg.total_questions = total_questions
            cfg.difficulty = difficulty
            cfg.subjects = [x.strip() for x in subjects.split(",") if x.strip()]
            cfg.distribution_mode = distribution_mode
            await s.commit()

    asyncio.run(_save())
    return RedirectResponse(f"/web/quiz-config?member_id={member_id}", status_code=302)


@router.get("/mastery", response_class=HTMLResponse)
async def mastery_page(request: Request, member_id: int | None = None):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(Member).where(Member.family_id == member.family_id, Member.role == MemberRole.CHILD)
            children = list((await s.execute(stmt)).scalars())
            target = None
            if member_id:
                target = next((c for c in children if c.id == member_id), None)
            if not target and children:
                target = children[0]
            if not target:
                return children, None, {}, []
            mastery = await get_all_mastery(s, target.id)
            stmt = select(Suggestion).where(
                Suggestion.member_id == target.id,
                Suggestion.status.in_([SuggestionStatus.PENDING, SuggestionStatus.ACCEPTED]),
            ).order_by(Suggestion.generated_at.desc()).limit(5)
            suggestions = list((await s.execute(stmt)).scalars())
            return children, target, mastery, [
                {"title": sg.title, "content": sg.content, "confidence": sg.confidence}
                for sg in suggestions
            ]

    children, target, mastery, suggestions = asyncio.run(_fetch())
    return templates.TemplateResponse("mastery.html", {
        "request": request, "members": children, "member": target,
        "mastery": mastery, "suggestions": suggestions, "version": _app_version(),
    })


@router.get("/content-rules", response_class=HTMLResponse)
async def content_rules_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(ContentRule).where(ContentRule.family_id == member.family_id)
            return list((await s.execute(stmt)).scalars())

    rules = asyncio.run(_fetch())
    return templates.TemplateResponse("content_rules.html", {
        "request": request, "rules": rules, "version": _app_version(),
    })


@router.post("/content-rules")
async def content_rules_add(
    request: Request,
    match_type: str = Form(...),
    pattern: str = Form(...),
    category: str = Form(...),
    action: str = Form("monitor"),
):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine
    from app.models.content_rule import MatchType, ContentCategory, ContentAction

    async def _add():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            r = ContentRule(
                family_id=member.family_id,
                match_type=MatchType(match_type),
                pattern=pattern,
                category=ContentCategory(category),
                action=ContentAction(action),
                enabled=True,
            )
            s.add(r)
            await s.commit()

    asyncio.run(_add())
    return RedirectResponse("/web/content-rules", status_code=302)


@router.get("/toxic-alerts", response_class=HTMLResponse)
async def toxic_alerts_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(ToxicAlert).join(Member, ToxicAlert.member_id == Member.id).where(
                Member.family_id == member.family_id
            ).order_by(ToxicAlert.created_at.desc()).limit(50)
            alerts = list((await s.execute(stmt)).scalars())
            out = []
            for a in alerts:
                m = await s.get(Member, a.member_id)
                out.append({
                    "id": a.id, "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                    "app_name": a.app_name, "window_title": a.window_title,
                    "category": a.category, "confidence": a.confidence,
                    "reason": a.reason, "notified": a.notified,
                    "parent_acknowledged": a.parent_acknowledged,
                    "member_name": m.name if m else "—",
                })
            return out

    alerts = asyncio.run(_fetch())
    return templates.TemplateResponse("toxic_alerts.html", {
        "request": request, "alerts": alerts, "version": _app_version(),
    })


@router.post("/toxic-alerts/{alert_id}/ack")
async def toxic_alert_ack(alert_id: int, request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _ack():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            a = await s.get(ToxicAlert, alert_id)
            if a:
                a.parent_acknowledged = True
                await s.commit()

    asyncio.run(_ack())
    return RedirectResponse("/web/toxic-alerts", status_code=302)


@router.get("/weekly-reports", response_class=HTMLResponse)
async def weekly_reports_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(WeeklyReport).where(WeeklyReport.family_id == member.family_id).order_by(
                WeeklyReport.week_start.desc()).limit(20)
            reports = list((await s.execute(stmt)).scalars())
            out = []
            for r in reports:
                m = await s.get(Member, r.member_id)
                out.append({
                    "id": r.id,
                    "week_start": r.week_start.isoformat(),
                    "week_end": r.week_end.isoformat(),
                    "summary": r.summary or {},
                    "push_status": r.push_status.value if hasattr(r.push_status, "value") else str(r.push_status),
                    "member_name": m.name if m else "—",
                })
            return out

    reports = asyncio.run(_fetch())
    return templates.TemplateResponse("weekly_reports.html", {
        "request": request, "reports": reports, "version": _app_version(),
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _fetch():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(NotificationConfig).where(NotificationConfig.family_id == member.family_id)
            return (await s.execute(stmt)).scalar_one_or_none()

    cfg = asyncio.run(_fetch()) or NotificationConfig(family_id=member.family_id)
    return templates.TemplateResponse("settings.html", {
        "request": request, "cfg": cfg, "version": _app_version(),
    })


@router.post("/settings")
async def settings_save(
    request: Request,
    email: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    webhook_url: str = Form(""),
    enable_weekly_email: str = Form(""),
    enable_toxic_alert: str = Form(""),
    toxic_threshold: float = Form(0.7),
):
    member = _current_member(request, None)
    if not member:
        return RedirectResponse("/web/login", status_code=302)

    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db.session import engine

    async def _save():
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            stmt = select(NotificationConfig).where(NotificationConfig.family_id == member.family_id)
            cfg = (await s.execute(stmt)).scalar_one_or_none()
            if not cfg:
                cfg = NotificationConfig(family_id=member.family_id)
                s.add(cfg)
            cfg.email = email or None
            cfg.smtp_host = smtp_host or None
            cfg.smtp_port = smtp_port
            cfg.smtp_user = smtp_user or None
            if smtp_password:
                cfg.smtp_password_enc = smtp_password  # TODO: encrypt at rest
            cfg.webhook_url = webhook_url or None
            cfg.enable_weekly_email = bool(enable_weekly_email)
            cfg.enable_toxic_alert = bool(enable_toxic_alert)
            cfg.toxic_alert_threshold = toxic_threshold
            await s.commit()

    asyncio.run(_save())
    return RedirectResponse("/web/settings", status_code=302)
''')

print("\nWeb routes done.")