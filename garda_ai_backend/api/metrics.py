from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import (
    HeatmapResponse,
    MetricsOverviewResponse,
    VolumeResponse,
)
from garda_ai_backend.repositories.metrics import MetricsRepository
from garda_ai_backend.repositories.sim import SimRepository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


async def _require_sim_now(session):
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    return sim_now


@router.get("/overview", response_model=MetricsOverviewResponse)
async def overview(session: SessionDep, redis: RedisDep, _: CurrentUserDep) -> MetricsOverviewResponse:
    sim_now = await _require_sim_now(session)
    repo = MetricsRepository(session)
    data = await cached_json(redis, f"overview:{sim_now.isoformat()}", ttl=5, compute=lambda: repo.overview(sim_now))
    return MetricsOverviewResponse(**data)


@router.get("/volume", response_model=VolumeResponse)
async def volume(session: SessionDep, redis: RedisDep, _: CurrentUserDep, range: str = "24h") -> VolumeResponse:
    sim_now = await _require_sim_now(session)
    repo = MetricsRepository(session)
    series = await cached_json(redis, f"volume:{range}:{sim_now.isoformat()}", ttl=5, compute=lambda: repo.volume(sim_now))
    return VolumeResponse(series=series)


@router.get("/heatmap", response_model=HeatmapResponse)
async def heatmap(session: SessionDep, redis: RedisDep, _: CurrentUserDep) -> HeatmapResponse:
    sim_now = await _require_sim_now(session)
    repo = MetricsRepository(session)
    cells = await cached_json(redis, f"heatmap:{sim_now.isoformat()}", ttl=5, compute=lambda: repo.heatmap(sim_now))
    return HeatmapResponse(cells=cells)
