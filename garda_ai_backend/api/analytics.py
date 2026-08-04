from fastapi import APIRouter

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, NowDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import (
    DetectionMetrics,
    FraudAnalyticsResponse,
    TypologyCount,
)
from garda_ai_backend.repositories.analytics import AnalyticsRepository

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _metrics(c: dict) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


@router.get("/fraud", response_model=FraudAnalyticsResponse)
async def fraud(
    session: SessionDep, redis: RedisDep, now: NowDep, _: CurrentUserDep
) -> FraudAnalyticsResponse:
    repo = AnalyticsRepository(session)

    async def compute() -> dict:
        return {
            "distribution": await repo.typology_distribution(now),
            "detection": _metrics(await repo.confusion_counts(now)),
        }

    data = await cached_json(redis, f"fraud:{now.isoformat()}", ttl=5, compute=compute)
    return FraudAnalyticsResponse(
        distribution=[TypologyCount(**d) for d in data["distribution"]],
        detection=DetectionMetrics(**data["detection"]),
    )
