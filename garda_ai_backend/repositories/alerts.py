from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Alert


class AlertsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(self, active_only: bool) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc())
        if active_only:
            stmt = stmt.where(Alert.acknowledged_at.is_(None))
        return list((await self._session.execute(stmt)).scalars().all())

    async def acknowledge(self, alert_id: int, user_id: int) -> Alert | None:
        alert = await self._session.get(Alert, alert_id)
        if alert is None:
            return None
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
        await self._session.flush()
        return alert
