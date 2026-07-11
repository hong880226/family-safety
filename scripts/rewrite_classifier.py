"""Rewrite content classifier: 2-pass matching (window_title first, then process)."""
from pathlib import Path

target = Path("E:/codeRepo/familysafety/backend/app/services/content_classifier.py")

content = '''"""Content classification service (L1 process name + L2 window title)."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_rule import ContentRule


DEFAULT_RULES: list[dict[str, Any]] = [
    {"match_type": "window_title", "pattern": r"(自残|自杀|血腥|暴力|色情|赌博)",
     "category": "toxic_content", "sub_label": "疑似毒视频", "action": "flag_for_llm"},
    {"match_type": "process", "pattern": r"(?i)(steam|epicgames|minecraft|riot|wegame|valve)\\.exe$",
     "category": "game_native", "sub_label": None, "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(4399|7k7k|3366|roblox|miniclip|小游戏)",
     "category": "game_web", "sub_label": "网页小游戏", "action": "warn"},
    {"match_type": "window_title", "pattern": r"(抖音|douyin|tiktok|快手|kwai)",
     "category": "short_video", "sub_label": None, "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(bilibili|b站|哔哩哔哩)",
     "category": "video_long", "sub_label": "B站", "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(学习|课程|慕课|mooc|教程|课堂|英语|数学|语文)",
     "category": "study", "sub_label": None, "action": "monitor"},
    {"match_type": "process", "pattern": r"(?i)(qq|wechat|wechatapp|telegram|discord)\\.exe$",
     "category": "social", "sub_label": None, "action": "monitor"},
    # Browser LAST among process rules, so it acts as fallback for unmatched browser windows
    {"match_type": "process", "pattern": r"(?i)(chrome|msedge|firefox|brave)\\.exe$",
     "category": "browser", "sub_label": None, "action": "monitor"},
]


class ClassificationResult:
    def __init__(self, category: str, sub_label: str | None, action: str,
                 confidence: float, source: str):
        self.category = category
        self.sub_label = sub_label
        self.action = action
        self.confidence = confidence
        self.source = source

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "sub_label": self.sub_label,
            "action": self.action,
            "confidence": self.confidence,
            "source": self.source,
        }


def _get_str(enum_or_str) -> str:
    if hasattr(enum_or_str, "value"):
        v = enum_or_str.value
        return v if isinstance(v, str) else str(v)
    return str(enum_or_str)


def _match(rule: ContentRule | dict, process_name: str, window_title: str) -> bool:
    if isinstance(rule, ContentRule):
        mt = _get_str(rule.match_type)
        pattern = rule.pattern
    else:
        mt = rule["match_type"]
        pattern = rule["pattern"]
    try:
        if mt == "process":
            return bool(re.search(pattern, process_name))
        if mt == "window_title":
            return bool(re.search(pattern, window_title, re.IGNORECASE))
        if mt == "url":
            return bool(re.search(pattern, window_title))
        if mt == "domain":
            return pattern.lower() in window_title.lower()
    except re.error:
        return False
    return False


def _make_result(rule: ContentRule | dict) -> ClassificationResult:
    is_db = isinstance(rule, ContentRule)
    if is_db:
        cat = _get_str(rule.category)
        act = _get_str(rule.action)
        sub = rule.sub_label
    else:
        cat = rule["category"]
        act = rule["action"]
        sub = rule["sub_label"]
    return ClassificationResult(
        category=cat, sub_label=sub, action=act,
        confidence=0.95 if is_db else 0.85,
        source="db" if is_db else "default",
    )


async def classify_content(
    db: AsyncSession | None,
    family_id: int | None,
    process_name: str,
    window_title: str,
) -> ClassificationResult:
    """Classify a window/app into a category.

    Matching strategy (in order):
      1. DB rules: window_title match wins over process match
      2. DEFAULT_RULES: same priority logic
    """
    rules_db: list[ContentRule] = []
    if db is not None and family_id is not None:
        try:
            stmt = select(ContentRule).where(
                ContentRule.family_id == family_id,
                ContentRule.enabled.is_(True),
            )
            result = await db.execute(stmt)
            rules_db = list(result.scalars().all())
        except Exception:
            rules_db = []

    for rule_set in (rules_db, DEFAULT_RULES):
        # Pass 1: window_title (more specific context)
        for rule in rule_set:
            mt = (_get_str(rule.match_type) if isinstance(rule, ContentRule)
                  else rule["match_type"])
            if mt == "window_title" and _match(rule, process_name, window_title):
                return _make_result(rule)
        # Pass 2: process name
        for rule in rule_set:
            mt = (_get_str(rule.match_type) if isinstance(rule, ContentRule)
                  else rule["match_type"])
            if mt == "process" and _match(rule, process_name, window_title):
                return _make_result(rule)

    return ClassificationResult(
        category="unknown",
        sub_label=None,
        action="monitor",
        confidence=0.0,
        source="none",
    )


def seed_default_rules() -> list[dict[str, Any]]:
    return [{**r, "enabled": True} for r in DEFAULT_RULES]
'''

target.write_text(content, encoding="utf-8")
print(f"Wrote {target} ({len(content)} bytes)")