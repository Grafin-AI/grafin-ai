import os
from pathlib import Path

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from grafin_ai_ingest.db import asyncpg_dsn

_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture
async def db(pg_url):
    # Fresh schema per test, built from the committed DDL snapshot (no backend import).
    conn = await asyncpg.connect(asyncpg_dsn(pg_url))
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await conn.execute(_SCHEMA_SQL)
    yield conn
    await conn.close()


@pytest.fixture
def data_dir():
    return os.path.join(os.path.dirname(__file__), "data")
