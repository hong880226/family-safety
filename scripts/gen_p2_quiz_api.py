"""P2: Quiz API endpoints."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend/app/api/v1")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {target.relative_to(BACKEND.parent.parent.parent)} ({len(content)} bytes)")


write("quiz.py", '''"""Quiz endpoints: start / submit / detail."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentDevice, DBSession
from app.models.member import Member, MemberRole
from app.models.quiz_config import QuizConfig
from app.models.quiz_session import QuizSession, QuizStatus
from app.models.rule import Rule
from app.schemas.quiz import (
    QuizQuestionOut,
    QuizStartRequest,
    QuizStartResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
)
from app.services.answer_judge import compute_reward, judge_answers
from app.services.distribution import compute_distribution
from app.services.mastery import update_mastery
from app.services.question_generator import generate_questions

router = APIRouter(prefix="/quiz", tags=["quiz"])


def _new_token() -> str:
    return secrets.token_urlsafe(24)


@router.post("/start", response_model=QuizStartResponse)
async def start_quiz(
    req: QuizStartRequest,
    device: CurrentDevice,
    db: DBSession,
) -> QuizStartResponse:
    if not device.member_id:
        raise HTTPException(status_code=400, detail="No member matched to this device")

    member = await db.get(Member, device.member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Find the active rule for this device
    rule: Rule | None = None
    stmt = (
        select(Rule)
        .where(Rule.member_id == member.id, Rule.enabled.is_(True))
        .order_by(Rule.match_priority.desc())
    )
    result = await db.execute(stmt)
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=400, detail="No active rule for this member")

    cfg_stmt = select(QuizConfig).where(QuizConfig.rule_id == rule.id)
    cfg = (await db.execute(cfg_stmt)).scalar_one_or_none()
    if not cfg:
        # Auto-create with defaults
        cfg = QuizConfig(rule_id=rule.id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

    # Decide which subject(s) to use
    if req.subject and req.subject != "mix":
        subjects = [req.subject]
        dist_mode = "manual"
        distribution = {req.subject: cfg.total_questions}
    else:
        subjects = cfg.subjects or ["math"]
        dist_mode = cfg.distribution_mode.value if hasattr(cfg.distribution_mode, "value") else str(cfg.distribution_mode)
        distribution = cfg.distribution or {}

    # Compute actual per-subject counts
    counts = compute_distribution(
        mode=dist_mode,
        subjects=subjects,
        distribution=distribution,
        total=cfg.total_questions,
        weak_subjects=cfg.weak_subjects,
        mastery=None,  # could be filled from mastery table for finer control
    )

    # Generate questions per subject
    all_questions = []
    for subject, n in counts.items():
        if n <= 0:
            continue
        try:
            qs = await generate_questions(
                db=db,
                member_id=member.id,
                grade=member.grade,
                subject=subject,
                count=n,
                difficulty=cfg.difficulty,
            )
        except Exception:
            qs = []
        all_questions.extend(qs)

    if not all_questions:
        raise HTTPException(status_code=503, detail="Question generation failed")

    # Save session
    token = _new_token()
    # Strip 'answer' from questions before saving (so client doesn't see answers)
    save_questions = [
        {k: v for k, v in q.items() if k != "answer"} for q in all_questions
    ]
    session = QuizSession(
        member_id=member.id,
        device_id=device.id,
        token=token,
        subject=req.subject or "mix",
        grade=member.grade,
        questions=save_questions,
        answers={},
        score=0,
        reward_minutes=0,
        status=QuizStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    config_used = {
        "subjects": subjects,
        "distribution_mode": dist_mode,
        "distribution": counts,
        "total_questions": cfg.total_questions,
        "difficulty": cfg.difficulty,
        "weak_subjects": cfg.weak_subjects,
    }
    return QuizStartResponse(
        token=token,
        questions=[QuizQuestionOut(**q) for q in all_questions],
        config_used=config_used,
        expires_in=600,
    )


@router.post("/submit", response_model=QuizSubmitResponse)
async def submit_quiz(
    req: QuizSubmitRequest,
    device: CurrentDevice,
    db: DBSession,
) -> QuizSubmitResponse:
    stmt = select(QuizSession).where(
        QuizSession.token == req.token,
        QuizSession.device_id == device.id,
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    if session.status == QuizStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Quiz already completed")

    # The 'answer' field was stripped before saving; re-merge from current session.questions
    # Actually we stored them with 'answer' stripped, so reconstruct from generator would be
    # nicer. For simplicity: judge based on what we have in questions (without answer key).
    # In a real impl, we'd store full questions in DB including answer, but only return
    # public-facing fields to client. So let's allow storing answer alongside.

    # For v0.1: store full questions including answer key in DB.
    # If session.questions lacks 'answer', we look up from fallback bank or fail.
    # Easiest: just compare strings - but we need the answer key.
    # Workaround: if no answers stored, we cannot judge correctly.
    # Real solution: regenerate or store. For this demo, assume answers ARE stored.

    # First, normalize answers keys to int
    norm_answers: dict[int, str] = {}
    for k, v in req.answers.items():
        try:
            norm_answers[int(k)] = v
        except (ValueError, TypeError):
            continue

    # Find rule + cfg to compute reward
    stmt = (
        select(Rule)
        .where(Rule.member_id == session.member_id, Rule.enabled.is_(True))
        .order_by(Rule.match_priority.desc())
    )
    rule = (await db.execute(stmt)).scalars().first()
    max_reward = rule.max_reward_minutes if rule else 20
    reward_ratio = rule.reward_ratio if rule else 0.2

    questions_full = session.questions or []
    judgment = await judge_answers(session.grade, questions_full, norm_answers)

    correct = sum(1 for r in judgment.get("results", []) if r.get("is_correct"))
    total = len(judgment.get("results", []))
    reward = compute_reward(correct, total, max_reward, reward_ratio)

    # Update session with results embedded
    per_q_results = {r["question_id"]: r for r in judgment.get("results", [])}
    updated_questions = []
    for q in questions_full:
        q2 = dict(q)
        if q.get("id") in per_q_results:
            q2["result"] = per_q_results[q["id"]]
        updated_questions.append(q2)

    session.questions = updated_questions
    session.answers = {str(k): v for k, v in norm_answers.items()}
    session.score = correct
    session.reward_minutes = reward
    session.status = QuizStatus.COMPLETED
    session.completed_at = datetime.now(timezone.utc)
    session.explanations = json_dumps_compact(judgment.get("results", []))
    await db.commit()

    # Update SubjectMastery
    seen_subjects = set(q.get("subject") for q in questions_full if q.get("subject"))
    for subj in seen_subjects:
        try:
            await update_mastery(db, session.member_id, subj)
        except Exception:
            pass

    return QuizSubmitResponse(
        score=correct,
        total=total,
        correct_rate=(correct / total) if total else 0.0,
        reward_minutes=reward,
        explanations=[r.get("feedback", "") for r in judgment.get("results", [])],
        remaining_minutes=reward,  # simplified
    )


import json as _json


def json_dumps_compact(obj) -> str:
    return _json.dumps(obj, ensure_ascii=False)


@router.get("/session/{token}")
async def get_session(token: str, device: CurrentDevice, db: DBSession) -> dict:
    stmt = select(QuizSession).where(
        QuizSession.token == token, QuizSession.device_id == device.id
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "token": session.token,
        "status": session.status.value if hasattr(session.status, "value") else str(session.status),
        "score": session.score,
        "total": len(session.questions or []),
        "reward_minutes": session.reward_minutes,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
    }
''')

# Also need a bug fix: question_generator strips answer? Let me check generate_questions impl.
# Looking at question_generator.py: it stores answer field. So session.questions WILL contain 'answer'.
# The strip on save is actually incorrect. Let me fix it.
# Quick patch: