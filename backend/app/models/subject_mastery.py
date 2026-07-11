"""Per-member per-subject mastery statistics."""
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SubjectMastery(Base):
    __tablename__ = "subject_mastery"
    __table_args__ = (UniqueConstraint("member_id", "subject", name="uq_member_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    subject: Mapped[str] = mapped_column(String(50), index=True)

    total_answered: Mapped[int] = mapped_column(Integer, default=0)
    total_correct: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=1.0)
    last_quiz_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_weak: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
