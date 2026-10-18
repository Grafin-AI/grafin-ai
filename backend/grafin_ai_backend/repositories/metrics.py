from datetime import datetime

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.schema import Transaction, TransactionEvent


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
            .where(TransactionEvent.event_time <= now)
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
        bucket = func.date_trunc(trunc, TransactionEvent.event_time).label("bucket")
        flagged = func.sum(
            case((TransactionEvent.status.in_(("flagged", "blocked")), 1), else_=0)
        )
        stmt = (
            select(bucket, func.count().label("count"), func.coalesce(flagged, 0).label("flagged"))
            .where(TransactionEvent.event_time <= now)
            .where(TransactionEvent.event_time >= lower)
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"bucket": r.bucket.isoformat(), "count": int(r.count), "flagged": int(r.flagged)}
            for r in rows
        ]

    async def heatmap(self, now: datetime) -> list[list[int]]:
        dow = cast(func.extract("dow", TransactionEvent.event_time), Integer).label("dow")
        hour = cast(func.extract("hour", TransactionEvent.event_time), Integer).label("hour")
        stmt = (
            select(dow, hour, func.count().label("count"))
            .where(TransactionEvent.event_time <= now)
            .group_by(dow, hour)
        )
        rows = (await self._session.execute(stmt)).all()
        grid = [[0] * 24 for _ in range(7)]
        for r in rows:
            # Postgres extract(dow) is 0=Sunday..6=Saturday, but the dashboard renders
            # rows Mon-first. Rotate so index 0 is Monday, or every row is drawn one
            # day late (Wednesday data appearing under "Thu").
            grid[(int(r.dow) + 6) % 7][int(r.hour)] = int(r.count)
        return grid
