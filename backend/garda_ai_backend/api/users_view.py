from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.deps import CurrentUser, CurrentUserDep, NowDep, SessionDep
from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.api.view_schemas import RiskProfile, UserRiskResponse
from garda_ai_backend.repositories.users_view import UserRiskRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def can_unmask(user: CurrentUser, unmasked: bool) -> bool:
    """Names are shown raw only to an admin who explicitly asks (?unmasked=true)."""
    return unmasked and user.role == "admin"


def _shape(row: dict, user: CurrentUser, unmasked: bool) -> RiskProfile:
    name = row["name"] if can_unmask(user, unmasked) else mask_name(row["name"])
    return RiskProfile(**{**row, "name": name})


@router.get("/risk", response_model=UserRiskResponse)
async def risk(
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    risk: str | None = None,
    unmasked: bool = False,
    limit: int = 100,
) -> UserRiskResponse:
    rows = await UserRiskRepository(session).risk_list(now, risk, limit)
    return UserRiskResponse(profiles=[_shape(r, user, unmasked) for r in rows])


@router.get("/{entity_id}/profile", response_model=RiskProfile)
async def profile(
    entity_id: str,
    session: SessionDep,
    user: CurrentUserDep,
    now: NowDep,
    unmasked: bool = False,
) -> RiskProfile:
    row = await UserRiskRepository(session).profile(now, entity_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return _shape(row, user, unmasked)
