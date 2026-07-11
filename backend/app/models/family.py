"""Family model."""
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Per-family secret used to authorise new device joins.
    # Stored hashed; plaintext is shown only once at creation/rotation.
    setup_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members = relationship("Member", back_populates="family", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="family", cascade="all, delete-orphan")
    notification_config = relationship(
        "NotificationConfig", back_populates="family", uselist=False, cascade="all, delete-orphan"
    )