import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth(role: str = "analyst") -> dict:
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
    app.dependency_overrides[deps.get_data_now] = lambda: seeded_dataset
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
    # Load-bearing, and pins BOTH halves of the design at once: the view is driven
    # by dataset time, while surfaced_at survives as real ingestion time so
    # detection lag (surfaced_at - event_time) stays measurable.
    assert items[0]["event_time"].startswith("2025-09")
    assert items[0]["surfaced_at"].startswith("2026-08")


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
    # Ground truth must never reach the UI.
    assert "is_laundering" not in body
    assert body["bank"] == "Bank Rakyat Indonesia (BRI)"
    assert body["from_bank"] == "10"
    assert body["from_bank_name"] == "Bank Rakyat Indonesia (BRI)"
    assert body["from_account"] == "ACC1"
    assert body["from_entity_id"] == "E1"
    assert body["from_entity_name"] == "A**** S****"
    assert body["to_bank"] == "20"
    assert body["to_bank_name"] == "Bank Mandiri"
    assert body["to_account"] == "ACC2"
    assert body["to_entity_id"] == "E2"
    assert body["to_entity_name"] == "B**** S****"


async def test_transaction_detail_unmasked_only_for_admin(client):
    r = await client.get("/api/v1/transactions/1?unmasked=true", headers=_auth("admin"))
    body = r.json()
    assert body["from_entity_name"] == "Ahmad Setiawan"
    assert body["to_entity_name"] == "Budi Santoso"
    # Admin without the opt-in, and analyst with it, both stay masked (Users view rule).
    r = await client.get("/api/v1/transactions/1", headers=_auth("admin"))
    assert r.json()["from_entity_name"] == "A**** S****"
    r = await client.get("/api/v1/transactions/1?unmasked=true", headers=_auth("analyst"))
    assert r.json()["from_entity_name"] == "A**** S****"


async def test_transaction_detail_requires_auth(client):
    r = await client.get("/api/v1/transactions/1")
    assert r.status_code in (401, 403)


async def test_transaction_detail_404(client):
    r = await client.get("/api/v1/transactions/999", headers=_auth())
    assert r.status_code == 404
