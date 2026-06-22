from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.security.passwords import hash_password


@pytest_asyncio.fixture
async def client(session, redis_url, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()  # isolate rate-limit + refresh state per test
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)

    repo = UserRepository(session)
    await repo.create(
        email="analyst@example.com", password_hash=hash_password("pw"),
        role="analyst", created_at=datetime.now(UTC),
    )
    await session.commit()

    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_login_me_refresh_logout_flow(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": "pw"}
    )
    assert r.status_code == 200
    tokens = r.json()
    access, refresh = tokens["access_token"], tokens["refresh_token"]

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json()["email"] == "analyst@example.com"
    assert r.json()["role"] == "analyst"

    r = await client.get("/api/v1/auth/me")  # no token
    assert r.status_code in (401, 403)

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})  # replay
    assert r.status_code == 401

    r = await client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    assert r.status_code == 204


async def test_login_bad_credentials(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "analyst@example.com", "password": "nope"}
    )
    assert r.status_code == 401


async def test_login_is_rate_limited(client):
    # limit is 10/min per client IP; 11th attempt is blocked with 429
    last = None
    for _ in range(11):
        last = await client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.com", "password": "nope"},
        )
    assert last.status_code == 429
