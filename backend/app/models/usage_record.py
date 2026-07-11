"""UsageRecord: a chunk of time spent on an app."""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True, index=True)
    member_grade: Mapped[int] = mapped_column(Integer, default=0)

    app_name: Mapped[str] = mapped_column(String(255), index=True)
    window_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    category: Mapped[str] = mapped_column(String(50), default="unknown", index=True)
    sub_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
