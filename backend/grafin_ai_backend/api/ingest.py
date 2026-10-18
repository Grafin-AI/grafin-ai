import json
import time
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from grafin_ai_backend.api.deps import RedisDep, SessionDep, SettingsDep
from grafin_ai_backend.api.ingest_auth import require_ingest_token
from grafin_ai_backend.api.ingest_schemas import IngestRequest, IngestResponse, IngestResultItem
from grafin_ai_backend.observability import INGEST_SCORING_LATENCY, INGEST_TRANSACTIONS
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.repositories.ingest import IngestRepository
from grafin_ai_backend.services.scoring_client import ScoringClient, ScoringUnavailable

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
    now = datetime.now(UTC)
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    try:
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
        # Measure the outbound scoring round-trip. perf_counter + finally records the
        # latency even on the ScoringUnavailable (503) path, so the histogram captures
        # slow/failing calls too, not just successes.
        _scoring_started = time.perf_counter()
        try:
            results = await scoring.score(score_items, correlation_id=cid)
        except ScoringUnavailable as exc:
            log.warning("ingest.scoring_unavailable", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="scoring unavailable"
            ) from exc
        finally:
            INGEST_SCORING_LATENCY.observe(time.perf_counter() - _scoring_started)

        scores_by_id = {r["transaction_id"]: r for r in results}
        _VALID_STATUS = {"approved", "flagged", "blocked"}
        bad = [
            t.transaction_id for t in txns
            if t.transaction_id not in scores_by_id
            or scores_by_id[t.transaction_id].get("status") not in _VALID_STATUS
            or not isinstance(scores_by_id[t.transaction_id].get("fraud_score"), (int, float))
        ]
        if bad:
            log.warning("ingest.invalid_scoring_response", count=len(bad))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="scoring returned incomplete or invalid results",
            )

        txn_rows = [
            {
                "id": t.transaction_id, "event_time": t.event_time, "from_bank_id": t.from_bank_id,
                "from_account": t.from_account, "to_bank_id": t.to_bank_id,
                "to_account": t.to_account,
                "amount_paid": t.amount_paid, "payment_currency": t.payment_currency,
                "amount_received": t.amount_received, "receiving_currency": t.receiving_currency,
                "payment_format": t.payment_format, "is_laundering": t.is_laundering,
            }
            for t in txns
        ]
        try:
            events = await repo.persist(txn_rows, scores_by_id, now)
        except IntegrityError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            log.warning("ingest.persist_integrity_error", sqlstate=sqlstate)
            if sqlstate == "23503":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="transaction references an unknown bank or account "
                           "(seed reference data first)",
                ) from exc
            raise

        # Bounded-cardinality throughput counters (never per-transaction labels).
        INGEST_TRANSACTIONS.labels("inserted").inc(len(events))
        INGEST_TRANSACTIONS.labels("duplicate").inc(len(txns) - len(events))

        bank_names = await repo.bank_names([t.from_bank_id for t in txns])
        by_id = {t.transaction_id: t for t in txns}
        event_by_id = {e.transaction_id: e for e in events}
        now_iso = now.isoformat()
        # Commit-then-notify: if redis.publish fails after the DB commit, those events
        # are persisted-but-not-published and won't be re-published on an idempotent
        # retry (acceptable for Phase 2; a transactional outbox is out of scope).
        for e in events:
            t = by_id[e.transaction_id]
            message = {
                "seq": e.seq, "transaction_id": e.transaction_id,
                "bank": bank_names.get(t.from_bank_id), "type": t.payment_format,
                "amount": float(t.amount_paid), "fraud_score": e.fraud_score,
                "typology": e.typology, "status": e.status,
                "surfaced_at": now_iso,
                "event_time": t.event_time.isoformat(),
            }
            await redis.publish(LIVE_EVENTS_CHANNEL, json.dumps(message, default=str))

        log.info("ingest.done", received=len(txns), inserted=len(events))
        results_out = [
            IngestResultItem(
                transaction_id=t.transaction_id,
                seq=(ev.seq if (ev := event_by_id.get(t.transaction_id)) else None),
                status=(
                    event_by_id[t.transaction_id].status
                    if t.transaction_id in event_by_id else None
                ),
                ingested=t.transaction_id in event_by_id,
            )
            for t in txns
        ]
        return IngestResponse(results=results_out)
    finally:
        structlog.contextvars.clear_contextvars()
