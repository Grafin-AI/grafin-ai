import asyncpg


def asyncpg_dsn(url: str) -> str:
    """asyncpg.connect wants a bare postgresql:// DSN, not SQLAlchemy's +asyncpg form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(asyncpg_dsn(url))
