from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import func, select

from garda_ai_backend.repositories.ingest import IngestRepository
from garda_ai_backend.schema import Account, Alert, Bank, Entity

NOW = datetime(2026, 6, 25, 9, 30, tzinfo=UTC)


def _txn(tid: int, laundering: bool = True) -> dict:
    return {
        "id": tid,
        "event_time": datetime(2026, 6, 25, 9, tzinfo=UTC),
        "from_bank_id": "011",
        "from_account": "1000000001",
        "to_bank_id": "011",
        "to_account": "1000000002",
        "amount_paid": 15000,
        "payment_currency": "IDR",
        "amount_received": 15000,
        "receiving_currency": "IDR",
        "payment_format": "ACH",
        "is_laundering": laundering,
    }


def _scores(tid: int, status: str, typology: str | None, score: float) -> dict:
    return {tid: {"fraud_score": score, "typology": typology, "status": status}}


@pytest_asyncio.fixture
async def seeded_reference(session):
    """Seed bank '011' + two accounts so transaction FKs resolve."""
    session.add_all([
        Bank(id="011", name="Bank Central Asia (BCA)"),
        Entity(id="ENT1", name="Rina Wijaya", province="DKI Jakarta"),
    ])
    await session.flush()
    session.add_all([
        Account(
            id="1000000001", bank_id="011", entity_id="ENT1",
            risk_score=Decimal("85"), risk_category="High",
        ),
        Account(
            id="1000000002", bank_id="011", entity_id="ENT1",
            risk_score=Decimal("12"), risk_category="Low",
        ),
    ])
    await session.commit()
    return session


async def test_persist_inserts_transaction_and_event(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    events = await repo.persist(
        [_txn(101)],
        _scores(101, status="flagged", typology="Smurfing", score=0.72),
        NOW,
    )

    assert len(events) == 1
    ev = events[0]
    assert ev.transaction_id == 101
    assert ev.status == "flagged"
    assert ev.typology == "Smurfing"
    assert ev.fraud_score == 0.72
    assert isinstance(ev.seq, int)

    # A flagged (non-blocked) event does NOT create an alert.
    alert_count = (
        await session.execute(select(func.count()).select_from(Alert))
    ).scalar_one()
    assert alert_count == 0


async def test_persist_blocked_creates_alert(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    events = await repo.persist(
        [_txn(202)],
        _scores(202, status="blocked", typology="Fan-Out", score=0.97),
        NOW,
    )

    assert len(events) == 1
    assert events[0].status == "blocked"

    alerts = (await session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.event_seq == events[0].seq
    assert alert.severity == "high"
    assert alert.typology == "Fan-Out"
    assert alert.created_at == NOW


async def test_persist_is_idempotent(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    first = await repo.persist(
        [_txn(303)],
        _scores(303, status="blocked", typology="Fan-Out", score=0.9),
        NOW,
    )
    assert len(first) == 1

    # Re-ingesting the same producer transaction id is a no-op.
    second = await repo.persist(
        [_txn(303)],
        _scores(303, status="blocked", typology="Fan-Out", score=0.9),
        NOW,
    )
    assert second == []

    # Exactly one event and one alert exist despite the re-ingest.
    event_count = (
        await session.execute(
            select(func.count()).select_from(Alert)
        )
    ).scalar_one()
    assert event_count == 1


async def test_persist_batch_mixed_statuses(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    scores = {
        401: {"fraud_score": 0.05, "typology": None, "status": "approved"},
        402: {"fraud_score": 0.98, "typology": "Fan-Out", "status": "blocked"},
    }
    events = await repo.persist([_txn(401), _txn(402)], scores, NOW)

    assert len(events) == 2
    statuses = {e.transaction_id: e.status for e in events}
    assert statuses == {401: "approved", 402: "blocked"}

    # Only the blocked transaction yields an alert.
    alert_count = (
        await session.execute(select(func.count()).select_from(Alert))
    ).scalar_one()
    assert alert_count == 1


async def test_risk_categories_lookup(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    mapping = await repo.risk_categories(["1000000001", "1000000002", "9999999999"])

    assert mapping == {"1000000001": "High", "1000000002": "Low"}
    assert await repo.risk_categories([]) == {}


async def test_bank_names_lookup(seeded_reference):
    session = seeded_reference
    repo = IngestRepository(session)

    mapping = await repo.bank_names(["011", "999"])

    assert mapping == {"011": "Bank Central Asia (BCA)"}
    assert await repo.bank_names([]) == {}
