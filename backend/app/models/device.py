"""Device (a Windows PC) model."""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), default="windows")
    device_id: Mapped[str] = mapped_column(String(36), unique=True, default=_new_uuid, index=True)
    computer_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # bcrypt-hashed API key. Plaintext is shown to the agent exactly once on
    # register; DB only stores the hash + a non-secret prefix for log lines.
    api_key_hash: Mapped[str] = mapped_column(String(255), index=True)
    api_key_prefix: Mapped[str] = mapped_column(String(8))

    last_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    family = relationship("Family", back_populates="devices")