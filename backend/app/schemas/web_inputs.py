"""Pydantic input models for dashboard forms.

Centralised so we get uniform validation, type coercion, and clear error
messages on bad input. ReDoS-style pattern limits live here too.
"""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, Field, field_validator

from app.models.content_rule import ContentAction, ContentCategory, MatchType

_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff\u3040-\u30ff\- ]{1,32}$")
_PATTERN_MAX = 200


class MemberForm(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=32)]
    grade: Annotated[int, Field(ge=1, le=12)] = 4
    windows_username: Annotated[str, Field(default="", max_length=100)]

    @field_validator("name")
    @classmethod
    def _name_shape(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("姓名只能是中英文/数字/下划线/空格/连字符，长度 ≤32")
        return v

    @classmethod
    def as_form(
        cls,
        name: str = Form(...),
        grade: int = Form(4),
        windows_username: str = Form(""),
    ) -> "MemberForm":
        return cls(name=name, grade=grade, windows_username=windows_username)


class QuizConfigForm(BaseModel):
    member_id: Annotated[int, Field(ge=1)]
    total_questions: Annotated[int, Field(ge=1, le=20)] = 3
    difficulty: Annotated[int, Field(ge=1, le=5)] = 3
    subjects: Annotated[str, Field(default="math,chinese", max_length=200)]
    distribution_mode: Annotated[str, Field(default="auto", max_length=32)]

    @field_validator("distribution_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in {"auto", "weak_first", "balanced"}:
            raise ValueError("distribution_mode 必须是 auto/weak_first/balanced")
        return v

    @classmethod
    def as_form(
        cls,
        member_id: int = Form(...),
        total_questions: int = Form(3),
        difficulty: int = Form(3),
        subjects: str = Form("math,chinese"),
        distribution_mode: str = Form("auto"),
    ) -> "QuizConfigForm":
        return cls(
            member_id=member_id,
            total_questions=total_questions,
            difficulty=difficulty,
            subjects=subjects,
            distribution_mode=distribution_mode,
        )


class ContentRuleForm(BaseModel):
    match_type: MatchType
    pattern: Annotated[str, Field(min_length=1, max_length=_PATTERN_MAX)]
    category: ContentCategory
    action: ContentAction = ContentAction.MONITOR

    @field_validator("pattern")
    @classmethod
    def _pattern_safe(cls, v: str) -> str:
        # Naive ReDoS guard: disallow nested quantifiers, quantified
        # alternation, and other shapes that lead to catastrophic
        # backtracking. This intentionally duplicates the heuristic in
        # app.services.content_classifier so a bad pattern is rejected at
        # the API boundary instead of failing-open later.
        if re.search(r"\([^)]*[+*]\)[+*]", v):
            raise ValueError("正则表达式过于复杂")
        if re.search(r"\([^()]*\|[^()]*\)[+*]", v):
            raise ValueError("正则表达式过于复杂")
        if ".*.*" in v:
            raise ValueError("正则表达式过于复杂")
        return v

    @classmethod
    def as_form(
        cls,
        match_type: str = Form(...),
        pattern: str = Form(...),
        category: str = Form(...),
        action: str = Form("monitor"),
    ) -> "ContentRuleForm":
        try:
            return cls(
                match_type=MatchType(match_type),
                pattern=pattern,
                category=ContentCategory(category),
                action=ContentAction(action),
            )
        except ValueError as e:
            raise ValueError(f"枚举值非法: {e}") from e


class SettingsForm(BaseModel):
    email: Annotated[str, Field(default="", max_length=255)]
    smtp_host: Annotated[str, Field(default="", max_length=255)]
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 587
    smtp_user: Annotated[str, Field(default="", max_length=255)]
    smtp_password: Annotated[str, Field(default="", max_length=512)]
    webhook_url: Annotated[str, Field(default="", max_length=500)]
    enable_weekly_email: bool = False
    enable_toxic_alert: bool = False
    toxic_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.7

    @classmethod
    def as_form(
        cls,
        email: str = Form(""),
        smtp_host: str = Form(""),
        smtp_port: int = Form(587),
        smtp_user: str = Form(""),
        smtp_password: str = Form(""),
        webhook_url: str = Form(""),
        enable_weekly_email: str = Form(""),
        enable_toxic_alert: str = Form(""),
        toxic_threshold: float = Form(0.7),
    ) -> "SettingsForm":
        return cls(
            email=email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            webhook_url=webhook_url,
            enable_weekly_email=bool(enable_weekly_email),
            enable_toxic_alert=bool(enable_toxic_alert),
            toxic_threshold=toxic_threshold,
        )