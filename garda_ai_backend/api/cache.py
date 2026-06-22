import json
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis


async def cached_json(
    redis: Redis, key: str, ttl: int, compute: Callable[[], Awaitable[Any]]
) -> Any:
    """Return cached JSON for ``key`` or compute, store (ttl seconds), and return it."""
    cached = await redis.get(f"agg:{key}")
    if cached is not None:
        return json.loads(cached)
    value = await compute()
    await redis.set(f"agg:{key}", json.dumps(value, default=str), ex=ttl)
    return value
