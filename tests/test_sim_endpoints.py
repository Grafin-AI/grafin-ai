import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth(role: str) -> dict:
    token = create_access_token(subject="1", role=role, secret="test-secret", ttl_min=15)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
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


async def test_get_sim_state(client):
    r = await client.get("/api/v1/sim/state", headers=_auth("analyst"))
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert body["speed"] == 60.0
    assert body["sim_now"].startswith("2025-09-01")


async def test_sim_control_requires_admin(client):
    r = await client.post("/api/v1/sim/control", json={"running": False}, headers=_auth("analyst"))
    assert r.status_code == 403


async def test_sim_control_admin_updates(client):
    r = await client.post(
        "/api/v1/sim/control", json={"running": False, "speed": 120.0}, headers=_auth("admin")
    )
    assert r.status_code == 200
    assert r.json()["running"] is False
    assert r.json()["speed"] == 120.0
