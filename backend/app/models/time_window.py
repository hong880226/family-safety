"""Per-rule weekly time window (allow / deny / cap).

Each Rule may declare an ordered set of time windows. A window applies on the
selected weekdays (``weekday_mask``, bit 0 = Monday … bit 6 = Sunday) between
``start_time`` and ``end_time``. ``end_time`` may be earlier than ``start_time``
to express an overnight window (e.g. 22:00–06:00).

``action`` values:
  * ``"allow"``  — usage during this window is permitted up to ``cap_minutes``.
  * ``"deny"``   — usage during this window is blocked outright.
  * ``"cap"``    — usage is permitted but capped at ``cap_minutes`` minutes.

The default rule ``default_action`` ("allow" or "deny") is consulted when no
window matches the current wall-clock time. See ``app.services.schedule``.
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

# All seven weekdays set — bit 0 = Mon ... bit 6 = Sun. Same as
# datetime.weekday() mapping for readability at call sites.
ALL_WEEKDAYS_MASK = 0x7F


class TimeWindow(Base):
    __tablename__ = "time_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), index=True
    )

    weekday_mask: Mapped[int] = mapped_column(Integer, default=ALL_WEEKDAYS_MASK)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    action: Mapped[str] = mapped_column(String(8), default="allow")
    cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rule = relationship("Rule", back_populates="time_windows")
