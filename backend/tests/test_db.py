from sqlalchemy import text

from garda_ai_backend.db import build_engine


async def test_build_engine_connects(pg_url):
    engine = build_engine(pg_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await engine.dispose()
