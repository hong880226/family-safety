"""Quiz endpoints: start / submit / detail."""
from __future__ import annotations

import json as _json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_device, require_device, get_db
from app.models.device import Device
from app.core.security import decrypt_str, encrypt_str
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
    device: Device = Depends(require_device),
    db: AsyncSession = Depends(get_db),
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

    # Build the answer key (server-only) and the public question list (no answer).
    answer_key = {str(q.get("id")): str(q.get("answer", "")) for q in all_questions}
    public_questions = [{k: v for k, v in q.items() if k != "answer"} for q in all_questions]

    token = _new_token()
    session = QuizSession(
        member_id=member.id,
        device_id=device.id,
        token=token,
        subject=req.subject or "mix",
        grade=member.grade,
        questions=public_questions,
        answer_key_enc=encrypt_str(_json.dumps(answer_key, ensure_ascii=False)),
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
    device: Device = Depends(require_device),
    db: AsyncSession = Depends(get_db),
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

    # Rehydrate the answer key from encrypted storage.
    if not session.answer_key_enc:
        logger.error("quiz session %s has no answer_key_enc", session.token)
        raise HTTPException(status_code=500, detail="Answer key missing for session")
    answer_key_raw = decrypt_str(session.answer_key_enc)
    if not answer_key_raw:
        logger.error("quiz session %s answer key decrypt failed", session.token)
        raise HTTPException(status_code=500, detail="Answer key unreadable")
    try:
        answer_key: dict[str, str] = _json.loads(answer_key_raw)
    except Exception:
        raise HTTPException(status_code=500, detail="Answer key corrupted")

    # Attach answer to each public question so judge_answers has the key.
    questions_full = []
    for q in (session.questions or []):
        q2 = dict(q)
        q2["answer"] = answer_key.get(str(q.get("id")), "")
        questions_full.append(q2)

    judgment = await judge_answers(session.grade, questions_full, norm_answers)

    correct = sum(1 for r in judgment.get("results", []) if r.get("is_correct"))
    total = len(judgment.get("results", []))
    reward = compute_reward(correct, total, max_reward, reward_ratio)

    # Persist results. Strip 'answer' before saving to questions column so the
    # DB row never contains plaintext answers even after submission.
    per_q_results = {r["question_id"]: r for r in judgment.get("results", [])}
    updated_questions = []
    for q in questions_full:
        q2 = dict(q)
        q2.pop("answer", None)
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

    # Update SubjectMastery (single transaction).
    seen_subjects = set(q.get("subject") for q in questions_full if q.get("subject"))
    for subj in seen_subjects:
        try:
            await update_mastery(db, session.member_id, subj)
        except Exception:
            logger.exception("mastery update failed member={} subject={}", session.member_id, subj)

    return QuizSubmitResponse(
        score=correct,
        total=total,
        correct_rate=(correct / total) if total else 0.0,
        reward_minutes=reward,
        explanations=[r.get("feedback", "") for r in judgment.get("results", [])],
        remaining_minutes=reward,  # simplified
    )


def json_dumps_compact(obj) -> str:
    return _json.dumps(obj, ensure_ascii=False)


@router.get("/session/{token}")
async def get_session(token: str, device: Device = Depends(require_device), db: AsyncSession = Depends(get_db)) -> dict:
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
