"""LLM-generated suggestions for parents."""
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, JSON, Enum as SAEnum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SuggestionType(str, enum.Enum):
    LIMIT = "limit"
    SUBJECTS = "subjects"
    DIFFICULTY = "difficulty"
    ENCOURAGEMENT = "encouragement"
    SCHEDULE = "schedule"


class SuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class Suggestion(Base):
    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)

    type: Mapped[SuggestionType] = mapped_column(SAEnum(SuggestionType))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SuggestionStatus] = mapped_column(
        SAEnum(SuggestionStatus), default=SuggestionStatus.PENDING
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
