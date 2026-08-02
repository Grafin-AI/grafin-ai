from functools import lru_cache
from typing import cast

from fastapi import APIRouter, Depends

from garda_ai_scoring.api.auth import require_token
from garda_ai_scoring.api.schemas import (
    ScoreRequest,
    ScoreResponse,
    ScoreResultItem,
    Status,
)
from garda_ai_scoring.config import get_settings
from garda_ai_scoring.observability import TRANSACTIONS_SCORED
from garda_ai_scoring.scoring.factory import get_scorer
from garda_ai_scoring.scoring.types import ScoringContext, ScoringProvider, TxnInput

router = APIRouter(prefix="/v1", tags=["scoring"])


@lru_cache(maxsize=1)
def _provider() -> ScoringProvider:
    s = get_settings()
    return get_scorer(s.scorer, seed=s.seed, fn_rate=s.fn_rate, fp_rate=s.fp_rate)


@router.post("/score", response_model=ScoreResponse, dependencies=[Depends(require_token)])
async def score(body: ScoreRequest) -> ScoreResponse:
    provider = _provider()
    results: list[ScoreResultItem] = []
    for item in body.transactions:
        txn = TxnInput(
            transaction_id=item.transaction_id,
            from_account=item.from_account,
            to_account=item.to_account,
            amount=item.amount,
            payment_format=item.payment_format,
            is_laundering=item.is_laundering,
            event_time=item.event_time,
        )
        ctx = ScoringContext(from_risk_category=item.from_risk_category)
        r = await provider.score(txn, ctx)
        TRANSACTIONS_SCORED.labels(r.status).inc()
        results.append(
            ScoreResultItem(
                transaction_id=item.transaction_id,
                fraud_score=r.fraud_score,
                typology=r.typology,
                status=cast(Status, r.status),
            )
        )
    return ScoreResponse(results=results)
