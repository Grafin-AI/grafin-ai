from fastapi import HTTPException, status
from redis.asyncio import Redis


class RateLimiter:
    """Fixed-window per-key limiter backed by Redis INCR + EXPIRE."""

    def __init__(self, redis: Redis, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def check(self, key: str) -> None:
        redis_key = f"ratelimit:{key}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, self._window)
        if count > self._limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )
