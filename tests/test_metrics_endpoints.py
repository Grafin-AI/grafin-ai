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
    app.dependency_overrides[deps.get_data_now] = lambda: seeded_dataset
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_overview(client):
    r = await client.get("/api/v1/metrics/overview", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["total_transactions"] == 4
    assert body["flagged"] == 1
    assert body["blocked"] == 1
    assert body["total_amount"] == 20400000.0
    assert 0.0 <= body["fraud_rate"] <= 1.0


async def test_overview_requires_auth(client):
    r = await client.get("/api/v1/metrics/overview")
    assert r.status_code in (401, 403)


async def test_volume_buckets(client):
    r = await client.get("/api/v1/metrics/volume?range=24h", headers=_auth())
    assert r.status_code == 200
    series = r.json()["series"]
    assert isinstance(series, list)
    assert all({"bucket", "count", "flagged"} <= set(p) for p in series)


async def test_heatmap_shape(client):
    r = await client.get("/api/v1/metrics/heatmap", headers=_auth())
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert len(cells) == 7
    assert all(len(row) == 24 for row in cells)


async def test_volume_range_weekly_buckets_by_day(client):
    r = await client.get("/api/v1/metrics/volume?range=weekly", headers=_auth())
    assert r.status_code == 200
    series = r.json()["series"]
    # seeded events all fall on 2025-09-01 -> one day bucket
    assert len(series) == 1
    assert series[0]["count"] == 4
