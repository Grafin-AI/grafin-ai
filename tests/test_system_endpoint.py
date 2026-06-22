import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


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


async def test_system_health(client):
    r = await client.get("/api/v1/system/health", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["db_ok"] is True
    assert body["redis_ok"] is True
    assert body["model_accuracy_simulated"] is True
    assert body["events_surfaced"] == 4
