from garda_ai_backend.security.refresh_store import RefreshTokenStore


async def test_save_validate_revoke(redis_client):
    store = RefreshTokenStore(redis_client)
    await store.save(jti="jti-1", user_id="7", ttl_seconds=60)

    assert await store.is_valid(jti="jti-1", user_id="7") is True
    assert await store.is_valid(jti="jti-1", user_id="9") is False  # wrong user
    assert await store.is_valid(jti="missing", user_id="7") is False

    await store.revoke(jti="jti-1")
    assert await store.is_valid(jti="jti-1", user_id="7") is False
