import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from garda_ai_backend.schema import Base

# Disable Ryuk reaper sidecar — not needed for local test runs and
# causes port-mapping errors when the Ryuk container cannot bind.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
os.environ.setdefault(
    "GARDA_DATABASE_URL", "postgresql+asyncpg://garda:garda@localhost:5432/garda"
)


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture
async def session(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
