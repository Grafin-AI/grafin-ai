from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Entity, Transaction, TransactionEvent


class GeoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def province_fraud_counts(self, now: datetime) -> list[dict]:
        stmt = (
            select(Entity.province.label("province"), func.count().label("fraud_count"))
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .join(Account, Account.id == Transaction.from_account)
            .join(Entity, Entity.id == Account.entity_id)
            .where(TransactionEvent.surfaced_at <= now)
            .where(TransactionEvent.status.in_(("flagged", "blocked")))
            .where(Entity.province.is_not(None))
            .group_by(Entity.province)
            .order_by(func.count().desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"province": r.province, "fraud_count": int(r.fraud_count)} for r in rows]
