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


async def test_fraud_analytics(client):
    r = await client.get("/api/v1/analytics/fraud", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    typ = {d["typology"]: d for d in body["distribution"]}
    assert "Fan-Out" in typ and "Smurfing" in typ
    assert typ["Fan-Out"]["count"] == 1
    m = body["detection"]
    assert {"precision", "recall", "f1"} <= set(m)
    assert 0.0 <= m["precision"] <= 1.0
