from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, NowDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import (
    HeatmapResponse,
    MetricsOverviewResponse,
    VolumeResponse,
)
from garda_ai_backend.repositories.metrics import MetricsRepository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

# range -> (window back from now, date_trunc bucket granularity)
_RANGE_WINDOWS: dict[str, tuple[timedelta, str]] = {
    "24h": (timedelta(days=1), "hour"),
    "weekly": (timedelta(days=7), "day"),
    "monthly": (timedelta(days=30), "day"),
    "yearly": (timedelta(days=365), "month"),
}


def _floor_to_bucket(dt: datetime, trunc: str) -> datetime:
    """Snap a timestamp down to the start of its bucket.

    The window is anchored to the CURRENT bucket's start rather than to `now`
    itself, so the oldest bucket in the series is a whole one. Anchoring to a
    mid-bucket `now` leaves a sliver of a leading bucket (e.g. one minute of an
    hour), which plots as a near-zero point beside full ones and reads as a gap
    in the data. A partial bucket at the END is expected — that one is "now".
    """
    if trunc == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if trunc == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if trunc == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt


@router.get("/overview", response_model=MetricsOverviewResponse)
async def overview(
    session: SessionDep, redis: RedisDep, now: NowDep, _: CurrentUserDep
) -> MetricsOverviewResponse:
    repo = MetricsRepository(session)
    data = await cached_json(
        redis, f"overview:{now.isoformat()}", ttl=5, compute=lambda: repo.overview(now)
    )
    return MetricsOverviewResponse(**data)


@router.get("/volume", response_model=VolumeResponse)
async def volume(
    session: SessionDep,
    redis: RedisDep,
    now: NowDep,
    _: CurrentUserDep,
    time_range: str = Query("24h", alias="range"),
) -> VolumeResponse:
    window, trunc = _RANGE_WINDOWS.get(time_range, _RANGE_WINDOWS["24h"])
    lower = _floor_to_bucket(now, trunc) - window
    repo = MetricsRepository(session)
    series = await cached_json(
        redis,
        f"volume:{time_range}:{now.isoformat()}",
        ttl=5,
        compute=lambda: repo.volume(lower, now, trunc),
    )
    return VolumeResponse(series=series)


@router.get("/heatmap", response_model=HeatmapResponse)
async def heatmap(
    session: SessionDep, redis: RedisDep, now: NowDep, _: CurrentUserDep
) -> HeatmapResponse:
    repo = MetricsRepository(session)
    cells = await cached_json(
        redis, f"heatmap:{now.isoformat()}", ttl=5, compute=lambda: repo.heatmap(now)
    )
    return HeatmapResponse(cells=cells)
