from redis.asyncio import Redis

from grafin_ai_backend.config import get_settings


def build_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = build_redis(get_settings().redis_url)
    return _redis
