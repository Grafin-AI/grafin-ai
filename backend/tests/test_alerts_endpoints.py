from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from grafin_ai_backend.api import deps
from grafin_ai_backend.redis_client import build_redis
from grafin_ai_backend.schema import User
from grafin_ai_backend.security.tokens import create_access_token


def _auth(role: str = "analyst") -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role=role, secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    # Seed a user with id=1 so FK on alerts.acknowledged_by is satisfied
    session.add(User(
        id=1, email="test@example.com", password_hash="x",
        role="analyst", created_at=datetime(2025, 1, 1, tzinfo=UTC),
    ))
    await session.commit()

    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from grafin_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_list_alerts(client):
    r = await client.get("/api/v1/alerts", headers=_auth())
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    assert len(alerts) == 2
    fan_out = next(a for a in alerts if a["typology"] == "Fan-Out")
    assert fan_out["acknowledged"] is False
    # Dataset time of the underlying transaction, formatted like the live feed.
    assert fan_out["event_time"] == "2025-09-01T09:00:00+00:00"
    # created_at is kept: it is real ingestion (wall-clock) time.
    assert fan_out["created_at"].startswith("2026-08-12")
    # The card opens the transaction detail, so the alert carries its transaction id.
    detail = await client.get(f"/api/v1/transactions/{fan_out['transaction_id']}", headers=_auth())
    assert detail.status_code == 200 and detail.json()["typology"] == "Fan-Out"


async def test_alerts_ordered_by_event_time_not_created_at(client):
    """Alerts from one ingest batch share created_at, so ordering on it breaks ties
    arbitrarily. The list now DISPLAYS per-row event_time, so an arbitrary tie order
    makes the shown timestamps jump around within a batch."""
    r = await client.get("/api/v1/alerts", headers=_auth())
    assert r.status_code == 200
    alerts = r.json()["alerts"]

    # Precondition: created_at cannot be what ordered these -- it is identical on both.
    assert len({a["created_at"] for a in alerts}) == 1

    assert [a["id"] for a in alerts] == [2, 1]
    assert [a["event_time"] for a in alerts] == [
        "2025-09-01T11:00:00+00:00",
        "2025-09-01T09:00:00+00:00",
    ]


async def test_ack_alert(client):
    r = await client.post("/api/v1/alerts/1/ack", headers=_auth())
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
    r2 = await client.get("/api/v1/alerts?status=active", headers=_auth())
    assert all(a["id"] != 1 for a in r2.json()["alerts"])


async def test_ack_missing_alert_404(client):
    r = await client.post("/api/v1/alerts/999/ack", headers=_auth())
    assert r.status_code == 404
