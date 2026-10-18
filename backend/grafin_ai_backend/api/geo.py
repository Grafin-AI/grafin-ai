from fastapi import APIRouter

from grafin_ai_backend.api.cache import cached_json
from grafin_ai_backend.api.deps import CurrentUserDep, NowDep, RedisDep, SessionDep
from grafin_ai_backend.api.view_schemas import GeoResponse, ProvinceFraud
from grafin_ai_backend.repositories.geo import GeoRepository


def _risk_level(count: int) -> str:
    if count >= 100:
        return "high"
    if count >= 20:
        return "medium"
    return "low"


router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.get("/provinces", response_model=GeoResponse)
async def provinces(
    session: SessionDep, redis: RedisDep, now: NowDep, _: CurrentUserDep
) -> GeoResponse:
    repo = GeoRepository(session)
    data = await cached_json(
        redis, f"geo:{now.isoformat()}", ttl=10,
        compute=lambda: repo.province_fraud_counts(now),
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
