from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Transaction, TransactionEvent


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def typology_distribution(self, now: datetime) -> list[dict]:
        stmt = (
            select(
                TransactionEvent.typology.label("typology"),
                func.count().label("count"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("amount"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= now)
            .where(TransactionEvent.typology.is_not(None))
            .group_by(TransactionEvent.typology)
            .order_by(func.count().desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"typology": r.typology, "count": int(r.count), "total_amount": float(r.amount)}
            for r in rows
        ]

    async def confusion_counts(self, now: datetime) -> dict:
        predicted = TransactionEvent.status.in_(("flagged", "blocked"))
        actual = Transaction.is_laundering.is_(True)
        tp = func.sum(case((predicted & actual, 1), else_=0))
        fp = func.sum(case((predicted & ~actual, 1), else_=0))
        fn = func.sum(case((~predicted & actual, 1), else_=0))
        stmt = (
            select(func.coalesce(tp, 0), func.coalesce(fp, 0), func.coalesce(fn, 0))
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= now)
        )
        tp_v, fp_v, fn_v = (await self._session.execute(stmt)).one()
        return {"tp": int(tp_v), "fp": int(fp_v), "fn": int(fn_v)}
