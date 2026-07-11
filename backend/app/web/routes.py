"""Server-rendered dashboard routes.

Session cookie auth (simple). For v0.1: cookie holds signed JWT.

Security notes:
- All routes go through `require_parent_or_redirect` so unauthenticated
  requests are redirected to /web/login.
- All ID-based mutations verify the target belongs to the parent's family.
- POST forms require a CSRF token (`X-CSRF-Token` header or `csrf_token`
  hidden input). See `app.web.csrf`.
"""
from __future__ import annotations

import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jinja2
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_member, require_parent_or_redirect
from app.db.session import get_db
from app.core.security import (
    create_access_token,
    decrypt_str,
    encrypt_str,
    hash_password,
    verify_password,
)
from app.models.content_rule import ContentRule, MatchType, ContentCategory, ContentAction
from app.models.device import Device
from app.models.member import Member, MemberRole
from app.models.notification_config import NotificationConfig
from app.models.quiz_config import QuizConfig
from app.models.rule import Rule
from app.models.suggestion import Suggestion, SuggestionStatus
from app.models.toxic_alert import ToxicAlert
from app.models.usage_record import UsageRecord
from app.models.weekly_report import WeeklyReport
from app.schemas.web_inputs import (
    ContentRuleForm,
    MemberForm,
    QuizConfigForm,
    SettingsForm,
)
from app.services.csrf import issue_csrf_token, validate_csrf_or_raise
from app.services.mastery import get_all_mastery
from app.core.config import get_settings
from app.web import redirect_with_toast

settings = get_settings()


def _set_flash_toast(response, kind: str, message: str) -> None:
    """Attach an X-Flash-Toast header so the client can pop a toast on the
    next page. Format: ``<kind>|<urlencoded-message>``."""
    try:
        response.headers["X-Flash-Toast"] = f"{kind}|{urllib.parse.quote(message)}"
    except Exception:
        pass


def redirect_with_toast(location: str, kind: str, message: str, status_code: int = 302):
    resp = RedirectResponse(location, status_code=status_code)
    _set_flash_toast(resp, kind, message)
    return resp

TEMPLATES_DIR = Path(__file__).parent / "templates"
_templates_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    enable_async=False,
)
_templates_env.cache = None  # type: ignore[assignment]

# Make `t("key")` available in templates.
from app.i18n import t as _i18n_t
_templates_env.globals["t"] = _i18n_t

templates = Jinja2Templates(env=_templates_env)

router = APIRouter(prefix="/web", tags=["web"])


def _app_version() -> str:
    try:
        from app import __version__
        return __version__
    except Exception:
        return "0.1.0"


# ---- Login (no auth) ----

@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    csrf = issue_csrf_token(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "version": _app_version(), "csrf_token": csrf},
    )


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    family_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)

    # v0.1: lookup parent by name. family_id, when supplied (e.g. after error
    # redirect) disambiguates when multiple families share the parent name "家长".
    stmt = select(Member).where(
        Member.role == MemberRole.PARENT,
        Member.name == username,
    )
    if family_id is not None:
        stmt = stmt.where(Member.family_id == family_id)
    r = await db.execute(stmt)
    member = r.scalar_one_or_none()
    if not member or not member.password_hash:
        # No silent "admin" fallback. Bad name OR missing hash both fail closed.
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "用户名或密码错误",
                "version": _app_version(),
                "csrf_token": issue_csrf_token(request),
            },
            status_code=401,
        )
    try:
        ok = verify_password(password, member.password_hash)
    except ValueError:
        ok = False
    if not ok:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "用户名或密码错误",
                "version": _app_version(),
                "csrf_token": issue_csrf_token(request),
            },
            status_code=401,
        )

    token = create_access_token({
        "sub": str(member.id),
        "family_id": member.family_id,
        "role": member.role.value,
    })
    resp = RedirectResponse("/web/dashboard", status_code=302)
    resp.set_cookie(
        "auth_token",
        token,
        httponly=True,
        secure=settings.environment != "dev",
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/web",
    )
    return resp


@router.get("/logout")
async def logout(request: Request):
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("auth_token", path="/web")
    return resp


# ---- Authenticated dashboard pages ----

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    csrf = issue_csrf_token(request)
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=today.weekday())

    stmt = select(UsageRecord).where(
        UsageRecord.member_id == member.id,
        UsageRecord.start_at >= week_start,
    )
    records = list((await db.execute(stmt)).scalars())
    today_minutes = sum(r.duration_seconds for r in records if r.start_at >= today_start) // 60
    week_minutes = sum(r.duration_seconds for r in records) // 60
    overtime_count = sum(1 for r in records if r.is_overtime)

    app_seconds: dict[str, int] = {}
    cat_seconds: dict[str, int] = {}
    for r in records:
        app_seconds[r.app_name] = app_seconds.get(r.app_name, 0) + r.duration_seconds
        cat_seconds[r.category] = cat_seconds.get(r.category, 0) + r.duration_seconds

    top_apps = sorted(
        [{"name": a, "minutes": s // 60, "percent": 0} for a, s in app_seconds.items()],
        key=lambda x: -x["minutes"],
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
    rule = (await db.execute(stmt)).scalars().first()
    if rule:
        daily_limit = rule.daily_limit_minutes

    summary = {
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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request, "summary": summary,
            "version": _app_version(), "active": "dashboard",
            "csrf_token": csrf,
        },
    )


@router.get("/members", response_class=HTMLResponse)
async def members_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Member).where(Member.family_id == member.family_id)
    members = list((await db.execute(stmt)).scalars())
    return templates.TemplateResponse(
        request,
        "members.html",
        {
            "request": request, "members": members,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/members")
async def members_add(
    request: Request,
    form: MemberForm = Depends(),
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    new_m = Member(
        family_id=member.family_id,
        name=form.name,
        role=MemberRole.CHILD,
        grade=form.grade,
        windows_username=form.windows_username or None,
    )
    db.add(new_m)
    await db.commit()
    return redirect_with_toast("/web/members", "success", f"已添加成员 {form.name}")


@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
async def members_edit_get(
    member_id: int,
    request: Request,
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Member).where(
        Member.id == member_id,
        Member.family_id == parent.family_id,
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="member not found")
    return templates.TemplateResponse(
        request,
        "member_edit.html",
        {
            "request": request, "m": target, "version": _app_version(),
            "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/members/{member_id}/edit")
async def members_edit_post(
    member_id: int,
    request: Request,
    form: MemberForm = Depends(),
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    stmt = select(Member).where(
        Member.id == member_id,
        Member.family_id == parent.family_id,
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="member not found")
    target.name = form.name
    target.grade = form.grade
    target.windows_username = form.windows_username or None
    await db.commit()
    return redirect_with_toast("/web/members", "success", f"已更新 {form.name}")


@router.post("/members/{member_id}/delete")
async def members_delete(
    member_id: int,
    request: Request,
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    stmt = select(Member).where(
        Member.id == member_id,
        Member.family_id == parent.family_id,
        Member.role == MemberRole.CHILD,
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if target:
        name = target.name
        await db.delete(target)
        await db.commit()
        return redirect_with_toast("/web/members", "success", f"已删除成员 {name}")
    return redirect_with_toast("/web/members", "warn", "未找到该成员")


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Device).where(Device.family_id == member.family_id)
    devices = list((await db.execute(stmt)).scalars())
    out = []
    for d in devices:
        name = ""
        if d.member_id:
            m = await db.get(Member, d.member_id)
            if m:
                name = m.name
        out.append({
            "id": d.id, "name": d.name, "computer_model": d.computer_model,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "online": d.online, "member_name": name,
        })
    return templates.TemplateResponse(
        request,
        "devices.html",
        {
            "request": request, "devices": out,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/devices/{device_id}/delete")
async def devices_delete(
    device_id: int,
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    d = await db.get(Device, device_id)
    if d and d.family_id == member.family_id:
        name = d.name
        d.revoked = True
        await db.commit()
        return redirect_with_toast("/web/devices", "success", f"已撤销设备 {name}")
    return redirect_with_toast("/web/devices", "warn", "设备不存在或无权访问")


@router.get("/rules", response_class=HTMLResponse)
async def rules_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Rule).where(Rule.member_id.in_(
        select(Member.id).where(Member.family_id == member.family_id)
    ))
    rules = list((await db.execute(stmt)).scalars())
    out = []
    for r in rules:
        m = await db.get(Member, r.member_id)
        out.append({
            "id": r.id, "name": r.name, "match_key": r.match_key,
            "daily_limit_minutes": r.daily_limit_minutes,
            "questions_per_session": r.questions_per_session,
            "enabled": r.enabled,
            "member_name": m.name if m else "—",
        })
    return templates.TemplateResponse(
        request,
        "rules.html",
        {
            "request": request, "rules": out,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.get("/quiz-config", response_class=HTMLResponse)
async def quiz_config_page(
    request: Request,
    member_id: int | None = None,
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Member).where(
        Member.family_id == parent.family_id, Member.role == MemberRole.CHILD,
    )
    children = list((await db.execute(stmt)).scalars())
    target = None
    cfg = None
    if member_id and any(c.id == member_id for c in children):
        target = next(c for c in children if c.id == member_id)
        stmt = select(Rule).where(Rule.member_id == target.id, Rule.enabled.is_(True))
        rule = (await db.execute(stmt)).scalars().first()
        if rule:
            stmt = select(QuizConfig).where(QuizConfig.rule_id == rule.id)
            cfg = (await db.execute(stmt)).scalar_one_or_none()
            if not cfg:
                cfg = QuizConfig(rule_id=rule.id)
                db.add(cfg)
                await db.commit()
                await db.refresh(cfg)
    return templates.TemplateResponse(
        request,
        "quiz_config.html",
        {
            "request": request, "members": children, "member": target,
            "cfg": cfg, "version": _app_version(),
            "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/quiz-config")
async def quiz_config_save(
    request: Request,
    form: QuizConfigForm = Depends(),
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    # Cross-family check: verify target member is in parent's family before
    # touching its rules.
    stmt = select(Member).where(
        Member.id == form.member_id,
        Member.family_id == parent.family_id,
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="child not found")

    stmt = select(Rule).where(Rule.member_id == form.member_id, Rule.enabled.is_(True))
    rule = (await db.execute(stmt)).scalars().first()
    if rule:
        stmt = select(QuizConfig).where(QuizConfig.rule_id == rule.id)
        cfg = (await db.execute(stmt)).scalar_one_or_none()
        if not cfg:
            cfg = QuizConfig(rule_id=rule.id)
            db.add(cfg)
        cfg.total_questions = form.total_questions
        cfg.difficulty = form.difficulty
        cfg.subjects = [x.strip() for x in form.subjects.split(",") if x.strip()]
        cfg.distribution_mode = form.distribution_mode
        await db.commit()
        return redirect_with_toast(
            f"/web/quiz-config?member_id={form.member_id}",
            "success",
            "答题配置已保存",
        )
    return redirect_with_toast(
        f"/web/quiz-config?member_id={form.member_id}",
        "warn",
        "该成员还没有启用的规则,未保存",
    )


@router.get("/mastery", response_class=HTMLResponse)
async def mastery_page(
    request: Request,
    member_id: int | None = None,
    parent: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Member).where(
        Member.family_id == parent.family_id, Member.role == MemberRole.CHILD,
    )
    children = list((await db.execute(stmt)).scalars())
    target = None
    if member_id:
        target = next((c for c in children if c.id == member_id), None)
    if not target and children:
        target = children[0]
    mastery: dict = {}
    suggestions = []
    if target:
        mastery = await get_all_mastery(db, target.id)
        stmt = select(Suggestion).where(
            Suggestion.member_id == target.id,
            Suggestion.status.in_([SuggestionStatus.PENDING, SuggestionStatus.ACCEPTED]),
        ).order_by(Suggestion.generated_at.desc()).limit(5)
        suggestions_objs = list((await db.execute(stmt)).scalars())
        suggestions = [
            {"title": sg.title, "content": sg.content, "confidence": sg.confidence}
            for sg in suggestions_objs
        ]
    return templates.TemplateResponse(
        request,
        "mastery.html",
        {
            "request": request, "members": children, "member": target,
            "mastery": mastery, "suggestions": suggestions,
            "version": _app_version(),
            "csrf_token": issue_csrf_token(request),
        },
    )


@router.get("/content-rules", response_class=HTMLResponse)
async def content_rules_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ContentRule).where(ContentRule.family_id == member.family_id)
    rules = list((await db.execute(stmt)).scalars())
    return templates.TemplateResponse(
        request,
        "content_rules.html",
        {
            "request": request, "rules": rules,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/content-rules")
async def content_rules_add(
    request: Request,
    form: ContentRuleForm = Depends(),
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    r = ContentRule(
        family_id=member.family_id,
        match_type=form.match_type,
        pattern=form.pattern,
        category=form.category,
        action=form.action,
        enabled=True,
    )
    db.add(r)
    await db.commit()
    return redirect_with_toast("/web/content-rules", "success", f"已添加规则 {form.pattern[:24]}")


@router.get("/toxic-alerts", response_class=HTMLResponse)
async def toxic_alerts_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ToxicAlert)
        .join(Member, ToxicAlert.member_id == Member.id)
        .where(Member.family_id == member.family_id)
        .order_by(ToxicAlert.created_at.desc())
        .limit(50)
    )
    alerts = list((await db.execute(stmt)).scalars())
    out = []
    for a in alerts:
        m = await db.get(Member, a.member_id)
        out.append({
            "id": a.id,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            "app_name": a.app_name, "window_title": a.window_title,
            "category": a.category, "confidence": a.confidence,
            "reason": a.reason, "notified": a.notified,
            "parent_acknowledged": a.parent_acknowledged,
            "member_name": m.name if m else "—",
        })
    return templates.TemplateResponse(
        request,
        "toxic_alerts.html",
        {
            "request": request, "alerts": out,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/toxic-alerts/{alert_id}/ack")
async def toxic_alert_ack(
    alert_id: int,
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    stmt = (
        select(ToxicAlert)
        .join(Member, ToxicAlert.member_id == Member.id)
        .where(ToxicAlert.id == alert_id, Member.family_id == member.family_id)
    )
    a = (await db.execute(stmt)).scalar_one_or_none()
    if a:
        a.parent_acknowledged = True
        await db.commit()
        return redirect_with_toast("/web/toxic-alerts", "success", "告警已确认")
    return redirect_with_toast("/web/toxic-alerts", "warn", "告警不存在")


@router.get("/weekly-reports", response_class=HTMLResponse)
async def weekly_reports_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(WeeklyReport)
        .where(WeeklyReport.family_id == member.family_id)
        .order_by(WeeklyReport.week_start.desc())
        .limit(20)
    )
    reports = list((await db.execute(stmt)).scalars())
    out = []
    for r in reports:
        m = await db.get(Member, r.member_id)
        out.append({
            "id": r.id,
            "week_start": r.week_start.isoformat(),
            "week_end": r.week_end.isoformat(),
            "summary": r.summary or {},
            "push_status": r.push_status.value if hasattr(r.push_status, "value") else str(r.push_status),
            "member_name": m.name if m else "—",
        })
    return templates.TemplateResponse(
        request,
        "weekly_reports.html",
        {
            "request": request, "reports": out,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NotificationConfig).where(NotificationConfig.family_id == member.family_id)
    cfg = (await db.execute(stmt)).scalar_one_or_none()
    if not cfg:
        cfg = NotificationConfig(family_id=member.family_id)
    has_smtp_pw = bool(cfg and cfg.smtp_password_enc)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request, "cfg": cfg, "has_smtp_pw": has_smtp_pw,
            "version": _app_version(), "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    form: SettingsForm = Depends(),
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    stmt = select(NotificationConfig).where(NotificationConfig.family_id == member.family_id)
    cfg = (await db.execute(stmt)).scalar_one_or_none()
    if not cfg:
        cfg = NotificationConfig(family_id=member.family_id)
        db.add(cfg)
    cfg.email = form.email or None
    cfg.smtp_host = form.smtp_host or None
    cfg.smtp_port = form.smtp_port
    cfg.smtp_user = form.smtp_user or None
    if form.smtp_password:
        cfg.smtp_password_enc = encrypt_str(form.smtp_password)
    cfg.webhook_url = form.webhook_url or None
    cfg.enable_weekly_email = form.enable_weekly_email
    cfg.enable_toxic_alert = form.enable_toxic_alert
    cfg.toxic_alert_threshold = form.toxic_threshold
    await db.commit()
    return redirect_with_toast("/web/settings", "success", "推送设置已保存")


# ---- Parent profile: change password ----

@router.get("/change-password", response_class=HTMLResponse)
async def change_password_get(
    request: Request,
    member: Member = Depends(require_parent_or_redirect),
):
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {
            "request": request, "version": _app_version(),
            "csrf_token": issue_csrf_token(request),
        },
    )


@router.post("/change-password")
async def change_password_post(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    member: Member = Depends(require_parent_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    await validate_csrf_or_raise(request)
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "change_password.html",
            {
                "request": request, "version": _app_version(),
                "csrf_token": issue_csrf_token(request),
                "error": "两次输入的新密码不一致",
            },
            status_code=400,
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "change_password.html",
            {
                "request": request, "version": _app_version(),
                "csrf_token": issue_csrf_token(request),
                "error": "新密码至少 8 个字符",
            },
            status_code=400,
        )
    if member.password_hash:
        try:
            if not verify_password(old_password, member.password_hash):
                raise ValueError
        except ValueError:
            return templates.TemplateResponse(
                request,
                "change_password.html",
                {
                    "request": request, "version": _app_version(),
                    "csrf_token": issue_csrf_token(request),
                    "error": "当前密码错误",
                },
                status_code=401,
            )
    member.password_hash = hash_password(new_password)
    await db.commit()
    return redirect_with_toast("/web/dashboard", "success", "密码已更新")