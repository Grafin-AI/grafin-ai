from grafin_ai_backend.redis_client import build_redis


async def test_build_redis_pings(redis_url):
    client = build_redis(redis_url)
    assert await client.ping() is True
    await client.aclose()
