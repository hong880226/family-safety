"""ToxicAlert: LLM-judged potentially harmful content."""
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Float, Boolean, JSON, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ToxicAlert(Base):
    __tablename__ = "toxic_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    window_title: Mapped[str] = mapped_column(String(500))
    app_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    llm_judgment: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
