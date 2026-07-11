"""QuizSession model."""
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class QuizStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(50), default="mix")
    grade: Mapped[int] = mapped_column(Integer, default=4)
    # Public-facing question data: id, prompt, options, subject, difficulty.
    # NEVER includes the 'answer' field — that lives encrypted in answer_key_enc.
    questions: Mapped[list] = mapped_column(JSON, default=list)
    # Encrypted (Fernet) JSON dump of {question_id: answer}. Decryptable only
    # server-side; protects against DB-leak answer disclosure.
    answer_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    reward_minutes: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[QuizStatus] = mapped_column(SAEnum(QuizStatus), default=QuizStatus.PENDING)
    explanations: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)