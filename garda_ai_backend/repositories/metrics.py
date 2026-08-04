from datetime import datetime

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Transaction, TransactionEvent


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self, now: datetime) -> dict:
        flagged = func.sum(case((TransactionEvent.status == "flagged", 1), else_=0))
        blocked = func.sum(case((TransactionEvent.status == "blocked", 1), else_=0))
        stmt = (
            select(
                func.count().label("total"),
                func.coalesce(flagged, 0).label("flagged"),
                func.coalesce(blocked, 0).label("blocked"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("amount"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= now)
        )
        row = (await self._session.execute(stmt)).one()
        total = row.total or 0
        risky = (row.flagged or 0) + (row.blocked or 0)
        return {
            "total_transactions": total,
            "flagged": int(row.flagged or 0),
            "blocked": int(row.blocked or 0),
            "total_amount": float(row.amount or 0),
            "fraud_rate": (risky / total) if total else 0.0,
        }

    async def volume(self, lower: datetime, now: datetime, trunc: str) -> list[dict]:
        bucket = func.date_trunc(trunc, TransactionEvent.surfaced_at).label("bucket")
        flagged = func.sum(
            case((TransactionEvent.status.in_(("flagged", "blocked")), 1), else_=0)
        )
        stmt = (
            select(bucket, func.count().label("count"), func.coalesce(flagged, 0).label("flagged"))
            .where(TransactionEvent.surfaced_at <= now)
            .where(TransactionEvent.surfaced_at >= lower)
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"bucket": r.bucket.isoformat(), "count": int(r.count), "flagged": int(r.flagged)}
            for r in rows
        ]

    async def heatmap(self, now: datetime) -> list[list[int]]:
        dow = cast(func.extract("dow", TransactionEvent.surfaced_at), Integer).label("dow")
        hour = cast(func.extract("hour", TransactionEvent.surfaced_at), Integer).label("hour")
        stmt = (
            select(dow, hour, func.count().label("count"))
            .where(TransactionEvent.surfaced_at <= now)
            .group_by(dow, hour)
        )
        rows = (await self._session.execute(stmt)).all()
        grid = [[0] * 24 for _ in range(7)]
        for r in rows:
            grid[int(r.dow)][int(r.hour)] = int(r.count)
        return grid
