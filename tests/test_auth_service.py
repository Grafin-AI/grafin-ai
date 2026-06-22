from datetime import UTC, datetime

import pytest

from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.security.passwords import hash_password
from garda_ai_backend.security.refresh_store import RefreshTokenStore
from garda_ai_backend.security.tokens import decode_token
from garda_ai_backend.services.auth import AuthError, AuthService

SECRET = "test-secret"


async def _seed_user(session, email="a@example.com", password="pw", role="analyst"):
    repo = UserRepository(session)
    await repo.create(
        email=email, password_hash=hash_password(password), role=role,
        created_at=datetime.now(UTC),
    )
    await session.commit()


def _service(session, redis_client):
    return AuthService(
        users=UserRepository(session),
        refresh_store=RefreshTokenStore(redis_client),
        secret=SECRET,
        access_ttl_min=15,
        refresh_ttl_days=7,
    )


async def test_authenticate_issues_tokens(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    access = decode_token(pair.access_token, secret=SECRET)
    assert access["role"] == "analyst"
    refresh = decode_token(pair.refresh_token, secret=SECRET)
    assert await RefreshTokenStore(redis_client).is_valid(refresh["jti"], access["sub"])


async def test_authenticate_bad_password(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    with pytest.raises(AuthError):
        await svc.authenticate("a@example.com", "wrong")


async def test_refresh_rotates_and_revokes_old(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    old_jti = decode_token(pair.refresh_token, secret=SECRET)["jti"]
    new_pair = await svc.refresh(pair.refresh_token)
    assert await RefreshTokenStore(redis_client).is_valid(old_jti, "1") is False
    new_claims = decode_token(new_pair.refresh_token, secret=SECRET)
    assert await RefreshTokenStore(redis_client).is_valid(new_claims["jti"], "1")


async def test_logout_revokes(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    jti = decode_token(pair.refresh_token, secret=SECRET)["jti"]
    await svc.logout(pair.refresh_token)
    assert await RefreshTokenStore(redis_client).is_valid(jti, "1") is False


async def test_refresh_token_replay_rejected(session, redis_client):
    await _seed_user(session)
    svc = _service(session, redis_client)
    pair = await svc.authenticate("a@example.com", "pw")
    await svc.refresh(pair.refresh_token)
    # presenting the same (now-rotated) refresh token again must be rejected
    with pytest.raises(AuthError):
        await svc.refresh(pair.refresh_token)
