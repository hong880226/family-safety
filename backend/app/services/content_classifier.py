"""Content classification service (L1 process name + L2 window title).

ReDoS defence is purely heuristic (no regex execution timeout in stdlib `re`):
we reject patterns that look dangerous before even compiling them. That's
strict but safe — at worst, a custom rule fails to match, which is no worse
than the rule never existing. Default rules are all hand-written and safe.
"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_rule import ContentRule


# Patterns exceeding this length are rejected to avoid pathological regex.
_MAX_PATTERN_LEN = 200
# Hard cap on input length fed to regex; an adversary could try to blow up
# the matcher by sending a huge window_title. Default window titles are <300.
_MAX_INPUT_LEN = 4096


# ---- Regex safety ----

# Conservative shape detector. Each fragment catches a class of patterns
# that historically caused catastrophic backtracking. We err on the side of
# rejecting too much (false positives are no-match; false negatives are
# CPU-denial-of-service).
_BAD_PATTERN_FRAGMENTS = (
    # Nested quantifiers like (a+)+, (a*)*
    r"\([^()]*[+*]\)[+*]",
    # Adjacent quantifiers: a+a+ / a*a*
    r"[+*]\s*[+*]",
    # .* followed by .* / .+ in any order
    r"\.\s*[+*][^a-zA-Z0-9]*\.\s*[+*]",
    # Alternation with overlapping branches is tricky; keep simple
    r"\(\.\*\|\.\+\)",
    # Quantified alternation (a|b)+ / (a|bc)*  — overlaps between
    # branches make this catastrophic. False positives like (red|green)+
    # are tolerated: they just fail to match.
    r"\([^()]*\|[^()]*\)[+*]",
)


def _is_unsafe_pattern(pattern: str) -> bool:
    if not pattern or len(pattern) > _MAX_PATTERN_LEN:
        return True
    for frag in _BAD_PATTERN_FRAGMENTS:
        if re.search(frag, pattern):
            return True
    return False


def _safe_search(pattern: str, text: str, flags: int = 0) -> bool:
    """Pre-flight check + bounded input size + single re.search call."""
    if not pattern or not text:
        return False
    if _is_unsafe_pattern(pattern):
        logger.warning("rejecting unsafe regex pattern={}", pattern[:80])
        return False
    if len(text) > _MAX_INPUT_LEN:
        text = text[:_MAX_INPUT_LEN]
    try:
        return bool(re.search(pattern, text, flags))
    except re.error:
        return False


def _match(rule: ContentRule | dict, process_name: str, window_title: str) -> bool:
    if isinstance(rule, ContentRule):
        mt = _get_str(rule.match_type)
        pattern = rule.pattern
    else:
        mt = rule["match_type"]
        pattern = rule["pattern"]
    flags = re.IGNORECASE if mt in ("window_title", "url") else 0
    if mt == "process":
        return _safe_search(pattern, process_name, flags)
    if mt == "window_title":
        return _safe_search(pattern, window_title, flags)
    if mt == "url":
        return _safe_search(pattern, window_title, flags)
    if mt == "domain":
        # Plain substring; cheap and safe.
        if not pattern:
            return False
        return pattern.lower() in (window_title or "").lower()
    return False


DEFAULT_RULES: list[dict[str, Any]] = [
    {"match_type": "window_title", "pattern": r"(自残|自杀|血腥|暴力|色情|赌博)",
     "category": "toxic_content", "sub_label": "疑似毒视频", "action": "flag_for_llm"},
    {"match_type": "process", "pattern": r"(?i)(steam|epicgames|minecraft|riot|wegame|valve)\.exe$",
     "category": "game_native", "sub_label": None, "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(4399|7k7k|3366|roblox|miniclip|小游戏)",
     "category": "game_web", "sub_label": "网页小游戏", "action": "warn"},
    {"match_type": "window_title", "pattern": r"(抖音|douyin|tiktok|快手|kwai)",
     "category": "short_video", "sub_label": None, "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(bilibili|b站|哔哩哔哩)",
     "category": "video_long", "sub_label": "B站", "action": "monitor"},
    {"match_type": "window_title", "pattern": r"(学习|课程|慕课|mooc|教程|课堂|英语|数学|语文)",
     "category": "study", "sub_label": None, "action": "monitor"},
    {"match_type": "process", "pattern": r"(?i)(qq|wechat|wechatapp|telegram|discord)\.exe$",
     "category": "social", "sub_label": None, "action": "monitor"},
    # Browser LAST among process rules, so it acts as fallback for unmatched browser windows
    {"match_type": "process", "pattern": r"(?i)(chrome|msedge|firefox|brave)\.exe$",
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
            logger.exception("content rule load failed family={}", family_id)
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
