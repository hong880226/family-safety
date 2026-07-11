"""DeviceCommand: queued remote action delivered on the next heartbeat.

A parent-issued command (lock screen, shutdown, reboot, force_quiz, etc.) is
written here and surfaced to the agent in the heartbeat response. The agent
MUST acknowledge by marking ``consumed_at`` server-side via the heartbeat
consumer logic (see ``app.api.v1.agent.heartbeat``).

``family_id`` is denormalised off ``Device.family_id`` so family-scoped
admin queries (audit / count) don't have to join through Device. The
foreign key uses ``ON DELETE CASCADE`` so revoking a Device purges any
in-flight commands.

``expires_at`` is checked at delivery time. Commands past their expiry
are skipped (and may be purged by a follow-up job; PR-A only filters
them out of the result set).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )

    # Lock screen / shutdown / reboot / force_quiz / show_warning / ...
    type: Mapped[str] = mapped_column(String(32))
    # Optional, type-specific extras (delay seconds for shutdown, message text, ...).
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # The parent who issued the command. Nullable so a future automated job
    # (e.g. nightly reset) can write commands without a member attribution.
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("members.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    device = relationship("Device")
