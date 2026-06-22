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


async def test_live_window_orders_desc_and_paginates(client):
    r = await client.get("/api/v1/transactions/live?limit=2", headers=_auth())
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    seqs = [i["seq"] for i in items]
    assert seqs == sorted(seqs, reverse=True)
    assert {"seq", "bank", "amount", "fraud_score", "status"} <= set(items[0])


async def test_live_after_seq_backfill(client):
    r = await client.get("/api/v1/transactions/live?after_seq=2", headers=_auth())
    assert r.status_code == 200
    seqs = [i["seq"] for i in r.json()["items"]]
    assert all(s > 2 for s in seqs)


async def test_transaction_detail(client):
    r = await client.get("/api/v1/transactions/1", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["typology"] == "Fan-Out"
    assert body["status"] == "blocked"
    assert body["amount"] == 15000000.0


async def test_transaction_detail_404(client):
    r = await client.get("/api/v1/transactions/999", headers=_auth())
    assert r.status_code == 404
