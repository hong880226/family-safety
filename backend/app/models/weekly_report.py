"""WeeklyReport: weekly digest for parents."""
import enum
from datetime import datetime, date

from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Enum as SAEnum, Date, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PushStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class PushChannel(str, enum.Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    DASHBOARD = "dashboard"


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)

    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)

    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    push_status: Mapped[PushStatus] = mapped_column(
        SAEnum(PushStatus), default=PushStatus.PENDING
    )
    push_channel: Mapped[PushChannel] = mapped_column(
        SAEnum(PushChannel), default=PushChannel.DASHBOARD
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
