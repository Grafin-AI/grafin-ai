from fastapi import APIRouter
from sqlalchemy import func, select, text

from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep, SettingsDep
from garda_ai_backend.api.view_schemas import SystemHealthResponse
from garda_ai_backend.schema import TransactionEvent

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health", response_model=SystemHealthResponse)
async def health(
    session: SessionDep, redis: RedisDep, settings: SettingsDep, _: CurrentUserDep
) -> SystemHealthResponse:
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    surfaced = (
        await session.execute(select(func.count()).select_from(TransactionEvent))
    ).scalar_one()

    return SystemHealthResponse(
        db_ok=db_ok,
        redis_ok=redis_ok,
        events_surfaced=int(surfaced),
        # Simulated unless a real trained model is configured behind the scoring service.
        model_accuracy_simulated=not settings.model_name,
        model_name=settings.model_name or None,
    )
