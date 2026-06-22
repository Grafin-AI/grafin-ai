from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from garda_ai_backend.config import get_settings


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=5)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = build_engine(get_settings().database_url)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _maker()() as session:
        yield session
