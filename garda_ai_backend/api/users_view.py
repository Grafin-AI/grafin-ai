from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep, SimNowDep
from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.api.view_schemas import RiskProfile, UserRiskResponse
from garda_ai_backend.repositories.users_view import UserRiskRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _shape(row: dict, user, unmasked: bool) -> RiskProfile:
    allow_unmasked = unmasked and user.role == "admin"
    name = row["name"] if allow_unmasked else mask_name(row["name"])
    return RiskProfile(**{**row, "name": name})


@router.get("/risk", response_model=UserRiskResponse)
async def risk(
    session: SessionDep,
    user: CurrentUserDep,
    sim_now: SimNowDep,
    risk: str | None = None,
    unmasked: bool = False,
    limit: int = 100,
) -> UserRiskResponse:
    rows = await UserRiskRepository(session).risk_list(sim_now, risk, limit)
    return UserRiskResponse(profiles=[_shape(r, user, unmasked) for r in rows])


@router.get("/{entity_id}/profile", response_model=RiskProfile)
async def profile(
    entity_id: str,
    session: SessionDep,
    user: CurrentUserDep,
    sim_now: SimNowDep,
    unmasked: bool = False,
) -> RiskProfile:
    row = await UserRiskRepository(session).profile(sim_now, entity_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return _shape(row, user, unmasked)
