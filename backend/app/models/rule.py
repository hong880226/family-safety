"""Rule model with match_key for (username, computer_model) matching."""
from datetime import datetime, time

from sqlalchemy import String, Integer, ForeignKey, DateTime, Time, Float, Boolean, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="default")

    match_key: Mapped[str] = mapped_column(
        String(255), default="*@*",
        comment="Format: <windows_username>@<computer_model>, supports * wildcard",
    )
    match_priority: Mapped[int] = mapped_column(Integer, default=0)

    daily_limit_minutes: Mapped[int] = mapped_column(Integer, default=120)
    weekday_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekend_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    bedtime_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    bedtime_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    monitored_apps: Mapped[list] = mapped_column(JSON, default=list)
    blocked_websites: Mapped[list] = mapped_column(JSON, default=list)

    questions_per_session: Mapped[int] = mapped_column(Integer, default=3)
    reward_ratio: Mapped[float] = mapped_column(Float, default=0.2)
    max_reward_minutes: Mapped[int] = mapped_column(Integer, default=20)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    member = relationship("Member", back_populates="rules")
    quiz_config = relationship(
        "QuizConfig", back_populates="rule", uselist=False, cascade="all, delete-orphan"
    )
