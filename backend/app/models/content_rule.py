"""Content classification rules."""
import enum
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MatchType(str, enum.Enum):
    PROCESS = "process"
    WINDOW_TITLE = "window_title"
    URL = "url"
    DOMAIN = "domain"


class ContentCategory(str, enum.Enum):
    GAME_NATIVE = "game_native"
    GAME_WEB = "game_web"
    SHORT_VIDEO = "short_video"
    VIDEO_LONG = "video_long"
    SOCIAL = "social"
    STUDY = "study"
    SEARCH = "search"
    NEWS = "news"
    BROWSER = "browser"
    TOXIC_CONTENT = "toxic_content"
    UNKNOWN = "unknown"


class ContentAction(str, enum.Enum):
    MONITOR = "monitor"
    WARN = "warn"
    BLOCK = "block"
    FLAG_FOR_LLM = "flag_for_llm"


class ContentRule(Base):
    __tablename__ = "content_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)

    match_type: Mapped[MatchType] = mapped_column(SAEnum(MatchType))
    pattern: Mapped[str] = mapped_column(String(500))
    category: Mapped[ContentCategory] = mapped_column(SAEnum(ContentCategory))
    sub_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[ContentAction] = mapped_column(
        SAEnum(ContentAction), default=ContentAction.MONITOR
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
