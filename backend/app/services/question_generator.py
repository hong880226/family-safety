"""Question generation service with LLM + fallback."""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.llm.client import LLMClient, LLMError
from app.llm.fallback_bank import get_fallback_questions
from app.llm.prompts import build_question_messages
from app.models.subject_mastery import SubjectMastery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _generate_with_llm(
    grade: int,
    subject: str,
    count: int,
    difficulty: int,
    is_weak: bool,
) -> list[dict[str, Any]]:
    """Call LLM to generate `count` questions."""
    client = LLMClient()
    messages = build_question_messages(
        grade=grade,
        subject=subject,
        count=count,
        difficulty=difficulty,
        is_weak=is_weak,
    )
    text = await client.chat(messages, temperature=0.8, response_format_json=True)
    parsed = LLMClient.parse_json_response(text)
    questions = parsed.get("questions", [])
    # Normalize ids and fields
    out = []
    for i, q in enumerate(questions):
        out.append({
            "id": i,
            "subject": q.get("subject", subject),
            "grade": q.get("grade", grade),
            "difficulty": q.get("difficulty", difficulty),
            "question": q["question"],
            "options": q["options"],
            "answer": q.get("answer", "A"),
            "explanation": q.get("explanation", ""),
        })
    if len(out) != count:
        raise LLMError(f"LLM returned {len(out)} questions, expected {count}")
    return out


async def generate_questions(
    db: AsyncSession,
    member_id: int,
    grade: int,
    subject: str,
    count: int,
    difficulty: int = 3,
) -> list[dict[str, Any]]:
    """Generate quiz questions, with fallback to local bank on LLM failure.

    Checks SubjectMastery to add weakness hint to LLM prompt.
    """
    is_weak = False
    try:
        stmt = select(SubjectMastery).where(
            SubjectMastery.member_id == member_id,
            SubjectMastery.subject == subject,
        )
        result = await db.execute(stmt)
        mastery = result.scalar_one_or_none()
        if mastery and mastery.is_weak:
            is_weak = True
    except Exception:
        logger.exception("mastery lookup failed member={} subject={}", member_id, subject)

    try:
        return await _generate_with_llm(grade, subject, count, difficulty, is_weak)
    except LLMError as e:
        logger.warning(f"LLM question generation failed, falling back: {e}")
        return get_fallback_questions(subject, count, grade=grade, difficulty=difficulty)
