import pytest
from fastapi import HTTPException

from grafin_ai_backend.api.ratelimit import RateLimiter


async def test_allows_under_limit(redis_client):
    rl = RateLimiter(redis_client, limit=3, window_seconds=60)
    for _ in range(3):
        await rl.check("client-a")  # no raise


async def test_blocks_over_limit(redis_client):
    rl = RateLimiter(redis_client, limit=2, window_seconds=60)
    await rl.check("client-b")
    await rl.check("client-b")
    with pytest.raises(HTTPException) as exc:
        await rl.check("client-b")
    assert exc.value.status_code == 429


async def test_separate_keys_independent(redis_client):
    rl = RateLimiter(redis_client, limit=1, window_seconds=60)
    await rl.check("client-c")
    await rl.check("client-d")  # different key, allowed
