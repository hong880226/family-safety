"""Answer judging service with LLM + simple fallback."""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_judge_messages


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
