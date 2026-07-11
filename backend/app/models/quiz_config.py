"""QuizConfig: per-rule quiz settings (subjects, difficulty, distribution)."""
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DistributionMode(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"
    WEAKNESS_FIRST = "weakness_first"


class QuizConfig(Base):
    __tablename__ = "quiz_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("rules.id"), unique=True, index=True
    )

    total_questions: Mapped[int] = mapped_column(Integer, default=3)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, comment="1-5")
    subjects: Mapped[list] = mapped_column(JSON, default=lambda: ["math", "chinese"])
    distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    distribution_mode: Mapped[DistributionMode] = mapped_column(
        SAEnum(DistributionMode), default=DistributionMode.AUTO
    )
    auto_weak_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    weak_subjects: Mapped[list] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rule = relationship("Rule", back_populates="quiz_config")
