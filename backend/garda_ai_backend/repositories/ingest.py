from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Alert, Bank, Transaction, TransactionEvent


@dataclass(frozen=True)
class InsertedEvent:
    seq: int
    transaction_id: int
    fraud_score: float
    typology: str | None
    status: str


class IngestRepository:
    """Persistence for the ingest write-path.

    Reference data (banks/accounts) is looked up for enrichment, and a batch of
    scored transactions is persisted idempotently: producer-provided transaction
    ids are the PK, so ``ON CONFLICT (id) DO NOTHING`` makes re-ingest a no-op and
    events/alerts are only created for newly-inserted transactions.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def risk_categories(self, account_ids: list[str]) -> dict[str, str | None]:
        """Map account id -> risk_category for the given ids (missing ids omitted)."""
        if not account_ids:
            return {}
        rows = (
            await self._session.execute(
                select(Account.id, Account.risk_category).where(Account.id.in_(account_ids))
            )
        ).all()
        return {r.id: r.risk_category for r in rows}

    async def bank_names(self, bank_ids: list[str]) -> dict[str, str]:
        """Map bank id -> name for the given ids (missing ids omitted)."""
        if not bank_ids:
            return {}
        rows = (
            await self._session.execute(
                select(Bank.id, Bank.name).where(Bank.id.in_(bank_ids))
            )
        ).all()
        return {r.id: r.name for r in rows}

    async def persist(
        self,
        transactions: list[dict],
        scores_by_id: dict[int, dict],
        now: datetime,
    ) -> list[InsertedEvent]:
        """Insert new transactions (ON CONFLICT DO NOTHING), then events for the newly-inserted
        ids, then alerts for blocked. One transaction; returns the inserted events with their seq.
        """
        async with self._session.begin():
            ins_txn = (
                pg_insert(Transaction)
                .values(transactions)
                .on_conflict_do_nothing(index_elements=[Transaction.id])
                .returning(Transaction.id)
            )
            new_ids = set((await self._session.execute(ins_txn)).scalars().all())
            if not new_ids:
                return []

            event_time_by_id = {t["id"]: t["event_time"] for t in transactions}
            event_values = [
                {
                    "transaction_id": tid,
                    "surfaced_at": now,
                    "event_time": event_time_by_id[tid],
                    "fraud_score": scores_by_id[tid]["fraud_score"],
                    "typology": scores_by_id[tid]["typology"],
                    "status": scores_by_id[tid]["status"],
                }
                # sorted(): new_ids is a set, so iterating it raw assigns seq in hash
                # order. seq stays a total order either way, but the live feed renders
                # in seq order, so out-of-order insertion makes its Time column jump
                # backwards mid-list.
                for tid in sorted(new_ids)
            ]
            ins_ev = (
                pg_insert(TransactionEvent)
                .values(event_values)
                .returning(
                    TransactionEvent.seq,
                    TransactionEvent.transaction_id,
                    TransactionEvent.fraud_score,
                    TransactionEvent.typology,
                    TransactionEvent.status,
                )
            )
            rows = (await self._session.execute(ins_ev)).all()
            events = [
                InsertedEvent(
                    seq=r.seq,
                    transaction_id=r.transaction_id,
                    fraud_score=float(r.fraud_score),
                    typology=r.typology,
                    status=r.status,
                )
                for r in rows
            ]

            alerts = [
                {"event_seq": e.seq, "severity": "high", "typology": e.typology, "created_at": now}
                for e in events
                if e.status == "blocked"
            ]
            if alerts:
                await self._session.execute(pg_insert(Alert).values(alerts))
            return events
