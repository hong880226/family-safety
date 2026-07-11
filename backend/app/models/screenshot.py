"""Screenshot: a JPEG/PNG snapshot uploaded by an agent.

Privacy note (architecture §5.3): screenshots are a deliberate opt-in feature
breaking the v1.0 'no screenshots' rule. Scope is intentionally minimal in
PR-C — the agent uploads, the parent browses. There is no auto-capture and no
TTL cleanup yet; both are tracked as follow-up work.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Screenshot(Base):
    __tablename__ = "device_screenshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)

    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Why was this screenshot captured? Drives audit UI grouping. PR-C wires
    # only the storage/upload path; the agent still chooses the value.
    trigger_type: Mapped[str] = mapped_column(String(16))

    # Optional metadata. Width/height can be filled by the agent later; we
    # accept nullable so an early agent can ship without parsing the bitmap.
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    bytes_size: Mapped[int] = mapped_column(Integer)

    # Path is RELATIVE to settings.screenshots_dir and is built from a fresh
    # uuid4 — never from caller-supplied data — so path-traversal is impossible.
    storage_path: Mapped[str] = mapped_column(String(512))

    sha256_hex: Mapped[str] = mapped_column(String(64), index=True)

    # Has a parent viewed the image at least once? Lets us badge unread rows
    # and eventually drive auto-purge heuristics. Not yet surfaced in UI.
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)

    device = relationship("Device", back_populates="screenshots")
