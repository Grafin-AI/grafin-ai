from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Entity, Transaction, TransactionEvent


class UserRiskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def risk_list(self, now: datetime, risk: str | None, limit: int) -> list[dict]:
        flagged = func.count().filter(TransactionEvent.status.in_(("flagged", "blocked")))
        stmt = (
            select(
                Entity.id.label("entity_id"),
                Entity.name.label("name"),
                Entity.province.label("province"),
                Account.risk_score.label("risk_score"),
                Account.risk_category.label("risk_category"),
                func.count(TransactionEvent.seq).label("total_txns"),
                flagged.label("flagged_txns"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("total_amount"),
            )
            .select_from(Entity)
            .join(Account, Account.entity_id == Entity.id)
            .join(Transaction, Transaction.from_account == Account.id, isouter=True)
            .join(
                TransactionEvent,
                (TransactionEvent.transaction_id == Transaction.id)
                & (TransactionEvent.surfaced_at <= now),
                isouter=True,
            )
            .group_by(Entity.id, Entity.name, Entity.province, Account.risk_score, Account.risk_category)
        )
        if risk:
            stmt = stmt.where(Account.risk_category == risk)
        stmt = stmt.order_by(Account.risk_score.desc().nulls_last()).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "entity_id": r.entity_id, "name": r.name, "province": r.province,
                "risk_level": r.risk_category, "risk_score": float(r.risk_score or 0),
                "total_transactions": int(r.total_txns), "flagged_transactions": int(r.flagged_txns),
                "total_amount": float(r.total_amount),
            }
            for r in rows
        ]

    async def profile(self, now: datetime, entity_id: str) -> dict | None:
        rows = await self.risk_list(now, risk=None, limit=1000)
        for r in rows:
            if r["entity_id"] == entity_id:
                return r
        return None
