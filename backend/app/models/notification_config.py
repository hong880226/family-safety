"""NotificationConfig: how to notify parents (email, webhook)."""
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), unique=True, index=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)

    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    enable_weekly_email: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_toxic_alert: Mapped[bool] = mapped_column(Boolean, default=True)
    toxic_alert_threshold: Mapped[float] = mapped_column(Float, default=0.7)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    family = relationship("Family", back_populates="notification_config")
