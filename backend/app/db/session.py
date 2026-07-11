"""Async SQLAlchemy session management."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialise database schema.

    - dev/test: create_all for fast iteration.
    - prod: require migrations via `alembic upgrade head`; refuse to fall back
      to create_all to avoid masking missed migrations.
    """
    from app.core.config import get_settings
    from app.models import (  # noqa: F401  ensure models are registered
        family,
        member,
        device,
        rule,
        quiz_config,
        usage_record,
        quiz_session,
        content_rule,
        toxic_alert,
        subject_mastery,
        suggestion,
        weekly_report,
        notification_config,
    )

    settings = get_settings()
    if settings.environment == "prod":
        # In prod, the entrypoint script must run `alembic upgrade head`.
        # We only check connectivity here.
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
