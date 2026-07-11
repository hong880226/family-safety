"""P2: content classification + toxic LLM judge."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend/app/services")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND.parent.parent)} ({len(content)} bytes)")


write("content_classifier.py", '''"""Content classification service (L1 process name + L2 window title)."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_rule import ContentRule, MatchType


# Built-in defaults (used when DB has no rules yet)
DEFAULT_RULES: list[dict[str, Any]] = [
    {"match_type": MatchType.PROCESS, "pattern": r"(?i)(steam|epicgames|minecraft|riot|wegame|valve)\\.exe$",
     "category": "game_native", "sub_label": None, "action": "monitor"},
    {"match_type": MatchType.PROCESS, "pattern": r"(?i)(chrome|msedge|firefox|brave)\\.exe$",
     "category": "browser", "sub_label": None, "action": "monitor"},
    {"match_type": MatchType.WINDOW_TITLE, "pattern": r"(4399|7k7k|3366|roblox|miniclip|小游戏)",
     "category": "game_web", "sub_label": "网页小游戏", "action": "warn"},
    {"match_type": MatchType.WINDOW_TITLE, "pattern": r"(抖音|douyin|tiktok|快手|kwai)",
     "category": "short_video", "sub_label": None, "action": "monitor"},
    {"match_type": MatchType.WINDOW_TITLE, "pattern": r"(bilibili|b站|哔哩哔哩)",
     "category": "video_long", "sub_label": "B站", "action": "monitor"},
    {"match_type": MatchType.WINDOW_TITLE, "pattern": r"(自残|自杀|血腥|暴力|色情|赌博)",
     "category": "toxic_content", "sub_label": "疑似毒视频", "action": "flag_for_llm"},
    {"match_type": MatchType.PROCESS, "pattern": r"(?i)(qq|wechat|wechatapp|telegram|discord)\\.exe$",
     "category": "social", "sub_label": None, "action": "monitor"},
    {"match_type": MatchType.WINDOW_TITLE, "pattern": r"(学习|课程|慕课|mooc|教程|课堂|英语|数学|语文)",
     "category": "study", "sub_label": None, "action": "monitor"},
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


def _match(rule: ContentRule | dict, process_name: str, window_title: str) -> bool:
    """Check if a rule matches the given process name or window title."""
    mt = rule.match_type if isinstance(rule, ContentRule) else rule["match_type"]
    pattern = rule.pattern if isinstance(rule, ContentRule) else rule["pattern"]
    try:
        if mt == MatchType.PROCESS or mt == "process":
            return bool(re.search(pattern, process_name))
        if mt == MatchType.WINDOW_TITLE or mt == "window_title":
            return bool(re.search(pattern, window_title, re.IGNORECASE))
        if mt == MatchType.URL or mt == "url":
            return bool(re.search(pattern, window_title))  # for v0.1, treat URL as title
        if mt == MatchType.DOMAIN or mt == "domain":
            return pattern.lower() in window_title.lower()
    except re.error:
        return False
    return False


async def classify_content(
    db: AsyncSession | None,
    family_id: int | None,
    process_name: str,
    window_title: str,
) -> ClassificationResult:
    """Classify a window/app into a category.

    Strategy:
      1. Try DB rules (ContentRule) first (parent-configurable)
      2. Fall back to hardcoded defaults
      3. Default 'unknown' if nothing matches
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

    all_rules = rules_db + DEFAULT_RULES  # DB rules win (higher priority)

    for rule in all_rules:
        if _match(rule, process_name, window_title):
            is_db = isinstance(rule, ContentRule)
            return ClassificationResult(
                category=rule.category.value if hasattr(rule.category, "value") else rule.category,
                sub_label=rule.sub_label,
                action=rule.action.value if hasattr(rule.action, "value") else rule.action,
                confidence=0.95 if is_db else 0.85,
                source="db" if is_db else "default",
            )

    return ClassificationResult(
        category="unknown",
        sub_label=None,
        action="monitor",
        confidence=0.0,
        source="none",
    )


def seed_default_rules() -> list[dict[str, Any]]:
    """Return the default rule set (for first-deployment seeding)."""
    return [
        {
            **r,
            "match_type": r["match_type"].value if hasattr(r["match_type"], "value") else r["match_type"],
            "category": r["category"].value if hasattr(r["category"], "value") else r["category"],
            "action": r["action"].value if hasattr(r["action"], "value") else r["action"],
            "enabled": True,
        }
        for r in DEFAULT_RULES
    ]
''')


write("toxic_judge.py", '''"""LLM-based toxic content judge.

Used when a content rule has action='flag_for_llm'.
"""
from __future__ import annotations

import logging
from typing import Any

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_toxic_judge_messages

logger = logging.getLogger(__name__)


async def judge_toxic(
    app_name: str,
    window_title: str,
    recent_history: list[str] | None = None,
) -> dict[str, Any]:
    """Ask LLM whether content is toxic. Returns dict with is_toxic, category, confidence, reason.

    Falls back to {is_toxic: False, confidence: 0.0} if LLM is unavailable.
    """
    history = recent_history or []
    try:
        client = LLMClient()
        messages = build_toxic_judge_messages(app_name, window_title, history)
        text = await client.chat(messages, temperature=0.2, response_format_json=True)
        data = LLMClient.parse_json_response(text)
        return {
            "is_toxic": bool(data.get("is_toxic", False)),
            "category": data.get("category", "other"),
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason", ""),
        }
    except LLMError as e:
        logger.warning(f"LLM toxic judge failed: {e}")
        return {"is_toxic": False, "category": "unknown", "confidence": 0.0, "reason": "judge_unavailable"}
''')
