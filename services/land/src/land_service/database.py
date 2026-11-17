from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from land_service.settings import get_land_settings


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_land_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session
