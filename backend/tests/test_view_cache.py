from garda_ai_backend.api.cache import cached_json


async def test_cached_json_computes_once(redis_client):
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"value": 42}

    first = await cached_json(redis_client, "k1", ttl=60, compute=compute)
    second = await cached_json(redis_client, "k1", ttl=60, compute=compute)
    assert first == {"value": 42}
    assert second == {"value": 42}
    assert calls["n"] == 1


async def test_cached_json_separate_keys(redis_client):
    async def compute_a():
        return {"v": "a"}

    async def compute_b():
        return {"v": "b"}

    assert await cached_json(redis_client, "ka", ttl=60, compute=compute_a) == {"v": "a"}
    assert await cached_json(redis_client, "kb", ttl=60, compute=compute_b) == {"v": "b"}
