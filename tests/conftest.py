import os

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from garda_ai_backend.schema import Base

# Disable Ryuk reaper sidecar — not needed for local test runs and
# causes port-mapping errors when the Ryuk container cannot bind.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
os.environ.setdefault(
    "GARDA_DATABASE_URL", "postgresql+asyncpg://garda:garda@localhost:5432/garda"
)
os.environ.setdefault("GARDA_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GARDA_JWT_SECRET", "test-secret")
# Ingest write-path (Phase 2) — required at startup, mirrors the fail-closed
# posture of GARDA_JWT_SECRET. Provided here so the app/get_settings() can boot
# across the suite. test_config_ingest.py clears these to assert they're required.
os.environ.setdefault("GARDA_SCORING_URL", "http://scoring:8000")
os.environ.setdefault("GARDA_SCORING_TOKEN", "test-scoring-token")
os.environ.setdefault("GARDA_INGEST_TOKEN", "test-ingest-token")


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture
async def session(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.fixture(scope="session")
def redis_url():
    with RedisContainer("redis:7-alpine") as rc:
        host = rc.get_container_host_ip()
        port = rc.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url):
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.flushdb()
    yield client
    await client.aclose()


from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio as _pytest_asyncio

from garda_ai_backend.schema import (
    Account,
    Alert,
    Bank,
    Entity,
    Transaction,
    TransactionEvent,
)

SIM_NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)


@_pytest_asyncio.fixture
async def seeded_dataset(session):
    """Deterministic mini dataset for view-endpoint tests."""
    session.add_all([
        Bank(id="10", name="Bank Rakyat Indonesia (BRI)"),
        Bank(id="20", name="Bank Mandiri"),
        Entity(id="E1", name="Ahmad Setiawan", province="DKI Jakarta"),
        Entity(id="E2", name="Budi Santoso", province="Jawa Barat"),
    ])
    await session.flush()
    session.add_all([
        Account(id="ACC1", bank_id="10", entity_id="E1", risk_score=Decimal("80"), risk_category="High"),
        Account(id="ACC2", bank_id="20", entity_id="E2", risk_score=Decimal("10"), risk_category="Low"),
    ])
    await session.flush()

    def _txn(i, frm, to, amount, launder, hour):
        return Transaction(
            id=i, event_time=datetime(2025, 9, 1, hour, tzinfo=UTC),
            from_bank_id="10", from_account=frm, to_bank_id="20", to_account=to,
            amount_paid=Decimal(amount), payment_currency="IDR",
            amount_received=Decimal(amount), receiving_currency="IDR",
            payment_format="ACH", is_laundering=launder,
        )
    session.add_all([
        _txn(1, "ACC1", "ACC2", "15000000", True, 9),
        _txn(2, "ACC2", "ACC1", "250000", False, 10),
        _txn(3, "ACC1", "ACC2", "5000000", True, 11),
        _txn(4, "ACC2", "ACC1", "150000", False, 11),
    ])
    await session.flush()

    def _ev(seq, tid, score, typ, status, hour):
        # The two clocks MUST differ, otherwise no test can tell which column a
        # query windows/buckets on and the whole event_time switch is untestable.
        return TransactionEvent(
            seq=seq, transaction_id=tid,
            # ingestion is wall-clock "today"; business time is the dataset's
            surfaced_at=datetime(2026, 8, 12, hour, tzinfo=UTC),
            event_time=datetime(2025, 9, 1, hour, tzinfo=UTC),
            fraud_score=Decimal(score), typology=typ, status=status,
        )
    session.add_all([
        _ev(1, 1, "0.95", "Fan-Out", "blocked", 9),
        _ev(2, 2, "0.10", None, "approved", 10),
        _ev(3, 3, "0.78", "Smurfing", "flagged", 11),
        _ev(4, 4, "0.05", None, "approved", 11),
    ])
    await session.flush()
    # Both alerts share created_at: they came from ONE ingest batch, stamped with that
    # batch's wall-clock now(). Their underlying events have different event_times
    # (seq 1 -> 09:00, seq 3 -> 11:00), so ordering on created_at leaves the tie broken
    # arbitrarily while ordering on event_time is deterministic. Inserted oldest-event
    # first, so physical order is the WRONG display order.
    batch_ingested_at = datetime(2026, 8, 12, 12, tzinfo=UTC)
    session.add_all([
        Alert(
            id=1, event_seq=1, severity="high", typology="Fan-Out",
            created_at=batch_ingested_at,
        ),
        Alert(
            id=2, event_seq=3, severity="medium", typology="Smurfing",
            created_at=batch_ingested_at,
        ),
    ])
    await session.commit()
    return SIM_NOW
