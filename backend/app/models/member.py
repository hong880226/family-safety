"""Member (parent or child) model."""
import enum
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MemberRole(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[MemberRole] = mapped_column(SAEnum(MemberRole), default=MemberRole.CHILD)
    grade: Mapped[int] = mapped_column(Integer, default=4, comment="1-12, used for quiz difficulty")
    windows_username: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Only for parents")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    family = relationship("Family", back_populates="members")
    rules = relationship("Rule", back_populates="member", cascade="all, delete-orphan")
