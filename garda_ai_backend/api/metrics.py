from datetime import timedelta

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
    lower = now - window
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
