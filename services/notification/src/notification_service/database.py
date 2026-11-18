from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from notification_service.settings import get_notification_settings


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    settings = get_notification_settings()
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10)
        return async_sessionmaker(engine, expire_on_commit=False)
    except Exception:
        return None


async def get_session() -> AsyncIterator[AsyncSession | None]:
    factory = get_session_factory()
    if factory is None:
        yield None
        return
    try:
        async with factory() as session:
            yield session
    except Exception:
        yield None
