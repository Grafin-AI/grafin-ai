from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from garda_ai_backend.schema import Account, Bank, Entity, Transaction, TransactionEvent


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
        """Transaction detail with both parties. Never returns ``is_laundering``: the
        ground-truth label must not reach the UI. Entity names come back raw; the API
        layer masks them per caller."""
        from_bank, to_bank = aliased(Bank), aliased(Bank)
        from_acc, to_acc = aliased(Account), aliased(Account)
        from_ent, to_ent = aliased(Entity), aliased(Entity)
        stmt = (
            select(
                Transaction.id, Transaction.amount_paid, Transaction.payment_currency,
                Transaction.payment_format, Transaction.event_time,
                Transaction.from_bank_id, Transaction.to_bank_id,
                Transaction.from_account, Transaction.to_account,
                from_bank.name.label("from_bank_name"), to_bank.name.label("to_bank_name"),
                from_ent.id.label("from_entity_id"), from_ent.name.label("from_entity_name"),
                to_ent.id.label("to_entity_id"), to_ent.name.label("to_entity_name"),
                TransactionEvent.fraud_score, TransactionEvent.typology, TransactionEvent.status,
            )
            .select_from(Transaction)
            .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
            .outerjoin(from_bank, from_bank.id == Transaction.from_bank_id)
            .outerjoin(to_bank, to_bank.id == Transaction.to_bank_id)
            .outerjoin(from_acc, from_acc.id == Transaction.from_account)
            .outerjoin(to_acc, to_acc.id == Transaction.to_account)
            .outerjoin(from_ent, from_ent.id == from_acc.entity_id)
            .outerjoin(to_ent, to_ent.id == to_acc.entity_id)
            .where(Transaction.id == transaction_id)
        )
        r = (await self._session.execute(stmt)).first()
        if r is None:
            return None
        return {
            "id": r.id,
            # `bank` kept for backward compatibility: the sending bank's name.
            "bank": r.from_bank_name or r.from_bank_id,
            "amount": float(r.amount_paid),
            "currency": r.payment_currency, "type": r.payment_format,
            "fraud_score": float(r.fraud_score), "typology": r.typology,
            "status": r.status,
            "event_time": r.event_time.isoformat(),
            "from_bank": r.from_bank_id, "from_bank_name": r.from_bank_name,
            "from_account": r.from_account,
            "from_entity_id": r.from_entity_id, "from_entity_name": r.from_entity_name,
            "to_bank": r.to_bank_id, "to_bank_name": r.to_bank_name,
            "to_account": r.to_account,
            "to_entity_id": r.to_entity_id, "to_entity_name": r.to_entity_name,
        }
