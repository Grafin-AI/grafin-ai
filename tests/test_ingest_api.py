"""Endpoint tests for POST /api/v1/ingest.

Boots the real FastAPI app in-process (ASGITransport) against the testcontainers
Postgres + Redis fixtures from conftest, mirroring tests/test_alerts_endpoints.py:
- ``deps.get_session`` is overridden with the test session so the route and the
  assertions share one transaction/connection.
- ``deps.get_redis`` is monkeypatched to a Redis bound to the test container so
  publishes land on a channel a test subscriber can read.
- ``get_scoring_client`` is overridden with an in-memory fake, so the route never
  touches ``app.state.http_client`` and the (un-run) lifespan is irrelevant. See
  the note on ``client`` below.

The ingest bearer token comes from ``GARDA_INGEST_TOKEN`` set in conftest.
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from garda_ai_backend.api import deps
from garda_ai_backend.api.ingest import get_scoring_client
from garda_ai_backend.observability import REGISTRY
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.schema import Account, Bank, Entity, Transaction, TransactionEvent
from garda_ai_backend.services.scoring_client import ScoringUnavailable

_INGEST_TOKEN = os.environ["GARDA_INGEST_TOKEN"]  # set in conftest (test-ingest-token)


def _ingest_headers() -> dict:
    return {"Authorization": f"Bearer {_INGEST_TOKEN}"}


_TXN = {
    "transaction_id": 40217, "from_bank_id": "011", "from_account": "1000000001",
    "to_bank_id": "011", "to_account": "1000000002", "amount_paid": "15000.00",
    "payment_currency": "IDR", "amount_received": "15000.00", "receiving_currency": "IDR",
    "payment_format": "ACH", "is_laundering": True, "event_time": "2026-06-25T09:00:00Z",
}
_TXN_B = {**_TXN, "transaction_id": 40218}


class _FakeScoring:
    def __init__(self, status="blocked"):
        self._status = status

    async def score(self, transactions, correlation_id=None):
        return [
            {
                "transaction_id": t["transaction_id"], "fraud_score": 0.9,
                "typology": "Smurfing", "status": self._status,
            }
            for t in transactions
        ]


class _CapturingScoring(_FakeScoring):
    """Records the exact ``transactions`` payload the route sent to scoring."""

    def __init__(self, status="blocked"):
        super().__init__(status)
        self.captured = None

    async def score(self, transactions, correlation_id=None):
        self.captured = transactions
        return await super().score(transactions, correlation_id)


class _BogusScoring:
    """Returns an off-vocabulary status so the route must reject it with 502."""

    async def score(self, transactions, correlation_id=None):
        return [
            {
                "transaction_id": t["transaction_id"], "fraud_score": 0.9,
                "typology": "Smurfing", "status": "bogus",
            }
            for t in transactions
        ]


class _DownScoring:
    async def score(self, transactions, correlation_id=None):
        raise ScoringUnavailable("down")


@pytest_asyncio.fixture
async def seeded_reference(session):
    """Seed bank '011' + entity + accounts so transaction FKs resolve."""
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


@pytest_asyncio.fixture
async def client(session, redis_url, monkeypatch):
    """App-bound HTTP client sharing the test session + a container-bound Redis.

    Note on the lifespan/app.state nuance: ASGITransport with AsyncClient does NOT
    run the app lifespan, so ``app.state.http_client`` is never created here. That is
    fine because every test overrides ``get_scoring_client`` (the only reader of
    ``app.state.http_client``) with an in-memory fake, so the real provider — and thus
    app.state — is never touched.
    """
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)

    from garda_ai_backend.main import app

    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c._app = app  # expose for per-test scoring override
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_ingest_requires_token(client):
    r = await client.post("/api/v1/ingest", json={"transactions": [_TXN]})
    assert r.status_code == 401


async def test_ingest_scores_persists_and_returns_result(client, session, seeded_reference):
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    item = results[0]
    assert item["transaction_id"] == 40217
    assert item["ingested"] is True
    assert item["status"] == "blocked"
    assert item["seq"] is not None

    # The transaction_events row was persisted.
    event = (
        await session.execute(
            select(TransactionEvent).where(TransactionEvent.transaction_id == 40217)
        )
    ).scalar_one()
    assert event.status == "blocked"


async def test_ingest_is_idempotent(client, session, seeded_reference):
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        first = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
        second = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert first.status_code == 200
    assert first.json()["results"][0]["ingested"] is True
    assert second.status_code == 200
    assert second.json()["results"][0]["ingested"] is False

    # Exactly one transaction persisted despite the re-ingest.
    txn_count = (
        await session.execute(select(func.count()).select_from(Transaction))
    ).scalar_one()
    assert txn_count == 1


async def test_ingest_scoring_unavailable_persists_nothing(client, session, seeded_reference):
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _DownScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert r.status_code == 503
    # Nothing was persisted: the write-path never ran past scoring.
    txn_count = (
        await session.execute(select(func.count()).select_from(Transaction))
    ).scalar_one()
    assert txn_count == 0
    event_count = (
        await session.execute(select(func.count()).select_from(TransactionEvent))
    ).scalar_one()
    assert event_count == 0


async def test_ingest_unknown_reference_returns_400(client, session):
    # No reference seeded → the transaction FK to bank/account fails.
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert r.status_code == 400


async def test_ingest_publishes_live_event(client, session, seeded_reference, redis_url):
    subscriber = build_redis(redis_url)
    pubsub = subscriber.pubsub()
    await pubsub.subscribe("garda:events:live")
    # Drain the subscribe-confirmation frame.
    await pubsub.get_message(timeout=1.0)

    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 200

    message = None
    for _ in range(20):
        raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if raw is not None:
            message = json.loads(raw["data"])
            break
        await asyncio.sleep(0.05)

    await pubsub.aclose()
    await subscriber.aclose()

    assert message is not None
    assert message["transaction_id"] == 40217
    assert message["bank"] == "Bank Central Asia (BCA)"
    assert message["type"] == "ACH"
    assert message["amount"] == 15000.0
    assert message["fraud_score"] == 0.9
    assert message["typology"] == "Smurfing"
    assert message["status"] == "blocked"
    assert message["seq"] is not None
    assert "surfaced_at" in message
    assert "sim_now" not in message


async def test_ingest_publish_matches_persisted_event_time(client, session, seeded_reference):
    # Sanity: event_time echoed from the producer is preserved on the row.
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 200

    txn = (
        await session.execute(select(Transaction).where(Transaction.id == 40217))
    ).scalar_one()
    assert txn.event_time == datetime(2026, 6, 25, 9, 0, tzinfo=UTC)


async def test_event_row_carries_transaction_event_time(client, session, seeded_reference):
    """The denormalized transaction_events.event_time mirrors the producer's event_time,
    while surfaced_at stays ingestion (wall-clock) time — so detection lag stays measurable."""
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 200

    ev = (
        await session.execute(
            select(TransactionEvent).where(TransactionEvent.transaction_id == 40217)
        )
    ).scalar_one()
    assert ev.event_time == datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    assert ev.surfaced_at != ev.event_time  # ingestion time is "now", not the CSV time


async def test_ingest_enrichment_reaches_scoring(client, session, seeded_reference):
    # from_account 1000000001 is seeded risk_category="High"; the route must enrich
    # the scoring payload with it. Removing the enrichment line fails this test.
    app = client._app
    fake = _CapturingScoring()
    app.dependency_overrides[get_scoring_client] = lambda: fake
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert r.status_code == 200
    assert fake.captured is not None
    assert fake.captured[0]["from_risk_category"] == "High"


async def test_ingest_oversize_batch_returns_422(client):
    # 1001 items exceeds the per-request cap; validation rejects before scoring/DB.
    # The scoring override only keeps dependency-solving off app.state; it is never
    # called because body validation fails first.
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        txns = [{**_TXN, "transaction_id": i} for i in range(1001)]
        r = await client.post(
            "/api/v1/ingest", json={"transactions": txns}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 422


async def test_ingest_mixed_new_and_duplicate(client, session, seeded_reference):
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        first = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
        assert first.status_code == 200
        second = await client.post(
            "/api/v1/ingest",
            json={"transactions": [_TXN, _TXN_B]},
            headers=_ingest_headers(),
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert second.status_code == 200
    results = {r["transaction_id"]: r for r in second.json()["results"]}
    assert results[40217]["ingested"] is False
    assert results[40218]["ingested"] is True

    # Exactly one NEW event (for B) was created by the second call: two events total.
    event_ids = (
        await session.execute(select(TransactionEvent.transaction_id))
    ).scalars().all()
    assert sorted(event_ids) == [40217, 40218]


async def test_ingest_records_transaction_metrics(client, session, seeded_reference):
    # RED-style ingest metrics: a successful ingest bumps the bounded `inserted`
    # counter and the metric is scrapeable from the app's Prometheus endpoint.
    def _inserted() -> float:
        return REGISTRY.get_sample_value(
            "garda_ingest_transactions_total", {"result": "inserted"}
        ) or 0.0

    before = _inserted()
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 200
    assert _inserted() - before == 1.0

    # The counter is exposed on the /metrics scrape endpoint the app already serves.
    scrape = await client.get("/metrics")
    assert scrape.status_code == 200
    assert "garda_ingest_transactions_total" in scrape.text


async def test_ingest_invalid_scoring_response_returns_502(client, session, seeded_reference):
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _BogusScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)

    assert r.status_code == 502
    # Nothing persisted: the route rejects the bad batch before repo.persist().
    txn_count = (
        await session.execute(select(func.count()).select_from(Transaction))
    ).scalar_one()
    assert txn_count == 0
    event_count = (
        await session.execute(select(func.count()).select_from(TransactionEvent))
    ).scalar_one()
    assert event_count == 0
