from fastapi import APIRouter

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep, SimNowDep
from garda_ai_backend.api.view_schemas import GeoResponse, ProvinceFraud
from garda_ai_backend.repositories.geo import GeoRepository


def _risk_level(count: int) -> str:
    if count >= 100:
        return "high"
    if count >= 20:
        return "medium"
    return "low"


router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.get("/provinces", response_model=GeoResponse)
async def provinces(
    session: SessionDep, redis: RedisDep, sim_now: SimNowDep, _: CurrentUserDep
) -> GeoResponse:
    repo = GeoRepository(session)
    data = await cached_json(
        redis, f"geo:{sim_now.isoformat()}", ttl=10,
        compute=lambda: repo.province_fraud_counts(sim_now),
    )
    return GeoResponse(
        provinces=[
            ProvinceFraud(
                name=d["province"], fraud_count=d["fraud_count"],
                # change_pct deferred: needs a prior replay window to diff against (Plan 3)
                change_pct=0.0, risk_level=_risk_level(d["fraud_count"]),
            )
            for d in data
        ]
    )
