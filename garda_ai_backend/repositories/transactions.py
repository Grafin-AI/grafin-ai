from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Bank, Transaction, TransactionEvent


class TransactionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_window(
        self, now: datetime, after_seq: int | None, limit: int
    ) -> list[dict]:
        stmt = (
            select(
                TransactionEvent.seq,
                TransactionEvent.transaction_id,
                TransactionEvent.fraud_score,
                TransactionEvent.typology,
                TransactionEvent.status,
                TransactionEvent.surfaced_at,
                TransactionEvent.event_time,
                Transaction.amount_paid,
                Transaction.payment_format,
                Bank.name.label("bank"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .join(Bank, Bank.id == Transaction.from_bank_id)
            .where(TransactionEvent.event_time <= now)
        )
        if after_seq is not None:
            stmt = stmt.where(TransactionEvent.seq > after_seq).order_by(TransactionEvent.seq.asc())
        else:
            stmt = stmt.order_by(TransactionEvent.seq.desc())
        stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "seq": r.seq, "transaction_id": r.transaction_id, "bank": r.bank,
                "type": r.payment_format, "amount": float(r.amount_paid),
                "fraud_score": float(r.fraud_score), "typology": r.typology,
                "status": r.status, "surfaced_at": r.surfaced_at.isoformat(),
                "event_time": r.event_time.isoformat(),
            }
            for r in rows
        ]

    async def detail(self, transaction_id: int) -> dict | None:
        stmt = (
            select(
                Transaction.id, Transaction.amount_paid, Transaction.payment_currency,
                Transaction.payment_format, Transaction.is_laundering, Transaction.event_time,
                Bank.name.label("bank"),
                TransactionEvent.fraud_score, TransactionEvent.typology, TransactionEvent.status,
            )
            .select_from(Transaction)
            .join(Bank, Bank.id == Transaction.from_bank_id)
            .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
            .where(Transaction.id == transaction_id)
        )
        r = (await self._session.execute(stmt)).first()
        if r is None:
            return None
        return {
            "id": r.id, "bank": r.bank, "amount": float(r.amount_paid),
            "currency": r.payment_currency, "type": r.payment_format,
            "fraud_score": float(r.fraud_score), "typology": r.typology,
            "status": r.status, "is_laundering": r.is_laundering,
            "event_time": r.event_time.isoformat(),
        }
