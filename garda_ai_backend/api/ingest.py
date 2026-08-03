import json
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from garda_ai_backend.api.deps import RedisDep, SessionDep, SettingsDep
from garda_ai_backend.api.ingest_auth import require_ingest_token
from garda_ai_backend.api.ingest_schemas import IngestRequest, IngestResponse, IngestResultItem
from garda_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from garda_ai_backend.repositories.ingest import IngestRepository
from garda_ai_backend.services.scoring_client import ScoringClient, ScoringUnavailable

log = structlog.get_logger()
router = APIRouter(
    prefix="/api/v1", tags=["ingest"], dependencies=[Depends(require_ingest_token)]
)


def get_scoring_client(request: Request, settings: SettingsDep) -> ScoringClient:
    client: httpx.AsyncClient = request.app.state.http_client
    return ScoringClient(
        client, settings.scoring_url, settings.scoring_token,
        retries=settings.scoring_retries, timeout_s=settings.scoring_timeout_s,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    body: IngestRequest,
    session: SessionDep,
    redis: RedisDep,
    scoring: ScoringClient = Depends(get_scoring_client),
    x_correlation_id: str | None = Header(default=None),
) -> IngestResponse:
    cid = x_correlation_id or uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    txns = body.transactions
    repo = IngestRepository(session)

    risk = await repo.risk_categories([t.from_account for t in txns])
    # The enrichment SELECT autobegins a read-only transaction. Release it before
    # the scoring network round-trip so we don't pin a DB connection across HTTP,
    # and so repo.persist() can open its own `session.begin()` on a clean session.
    await session.rollback()

    score_items = [
        {
            "transaction_id": t.transaction_id, "from_account": t.from_account,
            "to_account": t.to_account, "amount": str(t.amount_paid),
            "payment_format": t.payment_format, "is_laundering": t.is_laundering,
            "event_time": t.event_time.isoformat(),
            "from_risk_category": risk.get(t.from_account),
        }
        for t in txns
    ]
    try:
        results = await scoring.score(score_items, correlation_id=cid)
    except ScoringUnavailable as exc:
        log.warning("ingest.scoring_unavailable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="scoring unavailable"
        ) from exc
    scores_by_id = {r["transaction_id"]: r for r in results}

    txn_rows = [
        {
            "id": t.transaction_id, "event_time": t.event_time, "from_bank_id": t.from_bank_id,
            "from_account": t.from_account, "to_bank_id": t.to_bank_id, "to_account": t.to_account,
            "amount_paid": t.amount_paid, "payment_currency": t.payment_currency,
            "amount_received": t.amount_received, "receiving_currency": t.receiving_currency,
            "payment_format": t.payment_format, "is_laundering": t.is_laundering,
        }
        for t in txns
    ]
    try:
        events = await repo.persist(txn_rows, scores_by_id, datetime.now(UTC))
    except IntegrityError as exc:
        log.warning("ingest.bad_reference", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="transaction references an unknown bank or account (seed reference data first)",
        ) from exc

    bank_names = await repo.bank_names([t.from_bank_id for t in txns])
    by_id = {t.transaction_id: t for t in txns}
    inserted_ids = {e.transaction_id for e in events}
    now_iso = datetime.now(UTC).isoformat()
    for e in events:
        t = by_id[e.transaction_id]
        message = {
            "seq": e.seq, "transaction_id": e.transaction_id,
            "bank": bank_names.get(t.from_bank_id), "type": t.payment_format,
            "amount": float(t.amount_paid), "fraud_score": e.fraud_score,
            "typology": e.typology, "status": e.status,
            "surfaced_at": now_iso, "sim_now": now_iso,
        }
        await redis.publish(LIVE_EVENTS_CHANNEL, json.dumps(message, default=str))

    log.info("ingest.done", received=len(txns), inserted=len(events))
    results_out = [
        IngestResultItem(
            transaction_id=t.transaction_id,
            seq=next((e.seq for e in events if e.transaction_id == t.transaction_id), None),
            status=next((e.status for e in events if e.transaction_id == t.transaction_id), None),
            ingested=t.transaction_id in inserted_ids,
        )
        for t in txns
    ]
    structlog.contextvars.clear_contextvars()
    return IngestResponse(results=results_out)
