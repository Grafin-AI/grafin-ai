from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    app.dependency_overrides[deps.get_data_now] = lambda: seeded_dataset
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_overview(client):
    r = await client.get("/api/v1/metrics/overview", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["total_transactions"] == 4
    assert body["flagged"] == 1
    assert body["blocked"] == 1
    assert body["total_amount"] == 20400000.0
    assert 0.0 <= body["fraud_rate"] <= 1.0


async def test_overview_requires_auth(client):
    r = await client.get("/api/v1/metrics/overview")
    assert r.status_code in (401, 403)


async def test_volume_buckets(client):
    r = await client.get("/api/v1/metrics/volume?range=24h", headers=_auth())
    assert r.status_code == 200
    series = r.json()["series"]
    assert isinstance(series, list)
    assert all({"bucket", "count", "flagged"} <= set(p) for p in series)


async def test_heatmap_shape(client):
    r = await client.get("/api/v1/metrics/heatmap", headers=_auth())
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert len(cells) == 7
    assert all(len(row) == 24 for row in cells)
    # Load-bearing: dow/hour are extracted from event_time. 2025-09-01 is a Monday
    # (Postgres dow=1) and one event sits at 09:00. Bucketing on surfaced_at
    # (2026-08-12, a Wednesday) would put this cell elsewhere.
    assert cells[0][9] == 1


async def test_volume_range_weekly_buckets_by_day(client):
    r = await client.get("/api/v1/metrics/volume?range=weekly", headers=_auth())
    assert r.status_code == 200
    series = r.json()["series"]
    # seeded events all fall on 2025-09-01 -> one day bucket
    assert len(series) == 1
    assert series[0]["count"] == 4
    # Load-bearing: buckets key off event_time (dataset time), not surfaced_at
    # (which the fixture stamps at 2026-08-12).
    assert series[0]["bucket"].startswith("2025-09-01")


def test_floor_to_bucket_aligns_window_start():
    """The chart window anchors to the current bucket's start, not to `now`.

    Anchoring to a mid-bucket `now` leaves a sliver of a leading bucket — e.g. a
    window starting 23:59 yields an 'hour' bucket holding one minute of data,
    which plots as a near-zero point next to full ones and reads as missing data.
    """
    from garda_ai_backend.api.metrics import _floor_to_bucket

    mid = datetime(2025, 9, 8, 23, 59, 30, 500000, tzinfo=UTC)
    assert _floor_to_bucket(mid, "hour") == datetime(2025, 9, 8, 23, 0, tzinfo=UTC)
    assert _floor_to_bucket(mid, "day") == datetime(2025, 9, 8, 0, 0, tzinfo=UTC)
    assert _floor_to_bucket(mid, "month") == datetime(2025, 9, 1, 0, 0, tzinfo=UTC)

    on_boundary = datetime(2025, 9, 8, 23, 0, tzinfo=UTC)
    assert _floor_to_bucket(on_boundary, "hour") == on_boundary  # already aligned
