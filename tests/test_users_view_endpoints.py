import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth(role: str = "analyst") -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role=role, secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    app.dependency_overrides[deps.get_now] = lambda: seeded_dataset
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_user_risk_list_masks_name_for_analyst(client):
    r = await client.get("/api/v1/users/risk", headers=_auth("analyst"))
    assert r.status_code == 200
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "A**** S****"
    assert profiles["E1"]["risk_level"] == "High"


async def test_user_risk_list_unmasked_for_admin(client):
    r = await client.get("/api/v1/users/risk?unmasked=true", headers=_auth("admin"))
    assert r.status_code == 200
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "Ahmad Setiawan"


async def test_user_risk_unmasked_denied_for_analyst(client):
    r = await client.get("/api/v1/users/risk?unmasked=true", headers=_auth("analyst"))
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "A**** S****"


async def test_user_profile_detail(client):
    r = await client.get("/api/v1/users/E1/profile", headers=_auth("analyst"))
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == "E1"
    assert body["name"] == "A**** S****"
    assert body["total_transactions"] >= 1
    assert body["province"] == "DKI Jakarta"
