"""LLM-based toxic content judge.

Used when a content rule has action='flag_for_llm'.
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_toxic_judge_messages


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
