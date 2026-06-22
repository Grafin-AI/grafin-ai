from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.schema import User
from garda_ai_backend.security.tokens import create_access_token


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
    from garda_ai_backend.main import app
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
    assert len(alerts) == 1
    assert alerts[0]["typology"] == "Fan-Out"
    assert alerts[0]["acknowledged"] is False


async def test_ack_alert(client):
    r = await client.post("/api/v1/alerts/1/ack", headers=_auth())
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
    r2 = await client.get("/api/v1/alerts?status=active", headers=_auth())
    assert all(a["id"] != 1 for a in r2.json()["alerts"])


async def test_ack_missing_alert_404(client):
    r = await client.post("/api/v1/alerts/999/ack", headers=_auth())
    assert r.status_code == 404
