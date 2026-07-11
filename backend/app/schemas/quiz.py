"""Quiz session schemas."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class QuizStartRequest(BaseModel):
    subject: Literal["math", "chinese", "english", "science", "mix"] | None = None


class QuizQuestionOut(BaseModel):
    id: int
    subject: str
    grade: int
    difficulty: int
    question: str
    options: list[str]


class QuizStartResponse(BaseModel):
    token: str
    questions: list[QuizQuestionOut]
    config_used: dict
    expires_in: int = 600


class QuizSubmitRequest(BaseModel):
    token: str
    answers: dict[int, str] = Field(
        description="Map question_id -> chosen option letter (A/B/C/D)"
    )


class QuizSubmitResponse(BaseModel):
    score: int
    total: int
    correct_rate: float
    reward_minutes: int
    explanations: list[str]
    remaining_minutes: int | None = None
