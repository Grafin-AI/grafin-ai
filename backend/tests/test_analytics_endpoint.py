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


async def test_institutions(client):
    r = await client.get("/api/v1/analytics/institutions", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["institutions"] == [{
        "bank": "Bank Rakyat Indonesia (BRI)", "transactions": 4, "flagged": 1,
        "blocked": 1, "flagged_rate": 0.5,
    }]
    # Groups are ranked by SENDING volume; Mandiri never sends here, so as a receiver it
    # falls into "Lainnya".
    assert body["flows"] == [{
        "from_bank": "Bank Rakyat Indonesia (BRI)", "to_bank": "Lainnya",
        "flagged_count": 2, "amount": 20_000_000.0,
    }]


async def test_institutions_folds_others_into_lainnya(client, session, monkeypatch):
    from datetime import UTC, datetime
    from decimal import Decimal

    from garda_ai_backend.repositories import analytics as repo_mod
    from garda_ai_backend.schema import Transaction, TransactionEvent

    session.add(Transaction(
        id=5, event_time=datetime(2025, 9, 1, 11, tzinfo=UTC), from_bank_id="20",
        from_account="ACC2", to_bank_id="10", to_account="ACC1",
        amount_paid=Decimal("700"), payment_currency="IDR", amount_received=Decimal("700"),
        receiving_currency="IDR", payment_format="ACH", is_laundering=False,
    ))
    await session.flush()
    session.add(TransactionEvent(
        seq=5, transaction_id=5, surfaced_at=datetime(2026, 8, 12, 11, tzinfo=UTC),
        event_time=datetime(2025, 9, 1, 11, tzinfo=UTC), fraud_score=Decimal("0.7"),
        typology=None, status="flagged",
    ))
    await session.commit()
    monkeypatch.setattr(repo_mod, "TOP_BANKS", 1)
    body = (await client.get("/api/v1/analytics/institutions", headers=_auth())).json()
    assert [i["bank"] for i in body["institutions"]] == ["Bank Rakyat Indonesia (BRI)", "Lainnya"]
    lainnya = body["institutions"][1]
    assert lainnya == {
        "bank": "Lainnya", "transactions": 1, "flagged": 1, "blocked": 0, "flagged_rate": 1.0,
    }
    flows = {(f["from_bank"], f["to_bank"]): f for f in body["flows"]}
    assert flows[("Bank Rakyat Indonesia (BRI)", "Lainnya")]["flagged_count"] == 2
    assert flows[("Lainnya", "Bank Rakyat Indonesia (BRI)")] == {
        "from_bank": "Lainnya", "to_bank": "Bank Rakyat Indonesia (BRI)",
        "flagged_count": 1, "amount": 700.0,
    }
