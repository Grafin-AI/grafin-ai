from redis.asyncio import Redis


class RefreshTokenStore:
    """Stores valid refresh-token jtis in Redis so they can be revoked."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _key(jti: str) -> str:
        return f"refresh:{jti}"

    async def save(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        await self._redis.set(self._key(jti), user_id, ex=ttl_seconds)

    async def is_valid(self, jti: str, user_id: str) -> bool:
        stored = await self._redis.get(self._key(jti))
        return stored is not None and stored == user_id

    async def revoke(self, jti: str) -> None:
        await self._redis.delete(self._key(jti))
