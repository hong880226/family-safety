"""P2 services: question generation, answer judging, distribution, mastery."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend/app/services")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND.parent.parent)} ({len(content)} bytes)")


write("question_generator.py", '''"""Question generation service with LLM + fallback."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.llm.client import LLMClient, LLMError
from app.llm.fallback_bank import get_fallback_questions
from app.llm.prompts import build_question_messages
from app.models.subject_mastery import SubjectMastery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


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
        pass

    try:
        return await _generate_with_llm(grade, subject, count, difficulty, is_weak)
    except LLMError as e:
        logger.warning(f"LLM question generation failed, falling back: {e}")
        return get_fallback_questions(subject, count, grade=grade, difficulty=difficulty)
''')


write("answer_judge.py", '''"""Answer judging service with LLM + simple fallback."""
from __future__ import annotations

import logging
from typing import Any

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_judge_messages

logger = logging.getLogger(__name__)


async def _judge_with_llm(
    grade: int,
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> dict[str, Any]:
    """Use LLM to judge answers + generate explanations."""
    client = LLMClient()
    messages = build_judge_messages(grade, questions, answers)
    text = await client.chat(messages, temperature=0.3, response_format_json=True)
    return LLMClient.parse_json_response(text)


def _judge_simple(
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> dict[str, Any]:
    """Simple deterministic judge: compare student answer to correct answer."""
    results = []
    for q in questions:
        qid = q["id"]
        student = answers.get(qid, answers.get(str(qid), ""))
        correct = q.get("answer", "")
        is_correct = student.strip().upper() == correct.strip().upper()
        results.append({
            "question_id": qid,
            "is_correct": is_correct,
            "correct_answer": correct,
            "student_answer": student,
            "feedback": ("答对啦! " if is_correct else f"哎呀, 正确答案是 {correct}. ")
                        + q.get("explanation", ""),
        })
    correct_count = sum(1 for r in results if r["is_correct"])
    return {
        "results": results,
        "overall_feedback": f"你答对了 {correct_count} / {len(results)} 题, 继续加油!",
    }


async def judge_answers(
    grade: int,
    questions: list[dict[str, Any]],
    answers: dict[int, str],
) -> dict[str, Any]:
    """Judge student answers; use LLM if available, else simple matcher."""
    try:
        result = await _judge_with_llm(grade, questions, answers)
        results = result.get("results", [])
        if len(results) != len(questions):
            raise LLMError("LLM returned wrong number of results")
        return result
    except LLMError as e:
        logger.warning(f"LLM judging failed, falling back to simple judge: {e}")
        return _judge_simple(questions, answers)


def compute_reward(
    correct: int,
    total: int,
    max_reward_minutes: int,
    reward_ratio: float,
) -> int:
    """Compute reward minutes based on accuracy.

    reward = correct / total * max_reward_minutes * reward_ratio * (1 / reward_ratio)
    Simpler: reward = (correct / total) * max_reward_minutes
    Clamped to [0, max_reward_minutes]
    """
    if total <= 0:
        return 0
    accuracy = correct / total
    reward = int(accuracy * max_reward_minutes)
    return max(0, min(reward, max_reward_minutes))
''')


write("distribution.py", '''"""Compute quiz distribution based on QuizConfig and SubjectMastery."""
from __future__ import annotations

from app.models.quiz_config import DistributionMode


def compute_distribution(
    mode: str,
    subjects: list[str],
    distribution: dict[str, int],
    total: int,
    weak_subjects: list[str] | None = None,
    mastery: dict[str, dict] | None = None,
) -> dict[str, int]:
    """Return a dict {subject: count} summing to `total`.

    Modes:
      - manual:        use distribution dict literally (clipped to total)
      - auto:          round-robin among subjects
      - weakness_first: prioritize weak_subjects, fill rest round-robin
    """
    if mode == DistributionMode.MANUAL.value:
        # Clamp to total
        s = sum(distribution.values())
        if s != total:
            scale = total / s if s > 0 else 1
            out = {k: max(0, round(v * scale)) for k, v in distribution.items()}
            # Adjust to exact total
            diff = total - sum(out.values())
            if out:
                first = next(iter(out))
                out[first] = max(0, out[first] + diff)
            return {k: v for k, v in out.items() if v > 0}
        return {k: v for k, v in distribution.items() if v > 0}

    if not subjects:
        return {}

    if mode == DistributionMode.WEAKNESS_FIRST.value:
        weak = [s for s in (weak_subjects or []) if s in subjects]
        non_weak = [s for s in subjects if s not in weak]
        out: dict[str, int] = {}
        # Reserve at least 1 per weak subject, capped
        per_weak = max(1, total // (2 * max(1, len(weak)))) if weak else 0
        # First pass: assign each weak subject `per_weak`
        used = 0
        for s in weak:
            give = min(per_weak, total - used)
            if give > 0:
                out[s] = give
                used += give
        # Remaining: round-robin among non_weak + remaining weak
        pool = non_weak + weak
        if not pool:
            pool = subjects
        idx = 0
        while used < total and pool:
            s = pool[idx % len(pool)]
            out[s] = out.get(s, 0) + 1
            used += 1
            idx += 1
        return out

    # auto: round-robin
    out = {}
    for i in range(total):
        s = subjects[i % len(subjects)]
        out[s] = out.get(s, 0) + 1
    return out
''')


write("mastery.py", '''"""SubjectMastery update service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_session import QuizSession, QuizStatus
from app.models.subject_mastery import SubjectMastery


async def update_mastery(
    db: AsyncSession, member_id: int, subject: str
) -> SubjectMastery | None:
    """Recompute mastery stats for (member, subject) from last 30 days of quiz data.

    Updates in place (or creates a new row).
    Returns the updated mastery, or None if insufficient data.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = select(QuizSession).where(
        QuizSession.member_id == member_id,
        QuizSession.status == QuizStatus.COMPLETED,
        QuizSession.completed_at >= since,
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    total = 0
    correct = 0
    last_quiz_at: datetime | None = None
    for s in sessions:
        for q in s.questions or []:
            qsubj = q.get("subject") if isinstance(q, dict) else None
            if qsubj != subject:
                continue
            total += 1
            per_q = q.get("result") or {}
            if per_q.get("is_correct"):
                correct += 1
            if s.completed_at and (last_quiz_at is None or s.completed_at > last_quiz_at):
                last_quiz_at = s.completed_at

    if total == 0:
        return None

    accuracy = correct / total
    is_weak = total >= 10 and accuracy < 0.6

    stmt = select(SubjectMastery).where(
        SubjectMastery.member_id == member_id,
        SubjectMastery.subject == subject,
    )
    result = await db.execute(stmt)
    mastery = result.scalar_one_or_none()
    if mastery is None:
        mastery = SubjectMastery(
            member_id=member_id,
            subject=subject,
        )
        db.add(mastery)

    mastery.total_answered = total
    mastery.total_correct = correct
    mastery.accuracy = accuracy
    mastery.last_quiz_at = last_quiz_at
    mastery.is_weak = is_weak
    mastery.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(mastery)
    return mastery


async def get_all_mastery(
    db: AsyncSession, member_id: int
) -> dict[str, dict]:
    """Return all SubjectMastery rows for a member as a dict."""
    stmt = select(SubjectMastery).where(SubjectMastery.member_id == member_id)
    result = await db.execute(stmt)
    out = {}
    for m in result.scalars():
        out[m.subject] = {
            "accuracy": m.accuracy,
            "total": m.total_answered,
            "correct": m.total_correct,
            "is_weak": m.is_weak,
        }
    return out
''')
