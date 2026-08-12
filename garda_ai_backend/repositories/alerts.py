from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Alert, TransactionEvent


class AlertsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(self, active_only: bool) -> list[tuple[Alert, datetime]]:
        """Alerts newest-first on the DATASET timeline, paired with their event_time.

        Ordering is by the joined event_time, NOT by created_at: every alert raised in
        one ingest batch shares that batch's wall-clock created_at, so ordering on it
        leaves ties broken arbitrarily. Since the list displays per-row event_time, an
        arbitrary tie order makes the shown timestamps jump around within a batch.
        event_seq desc is a deterministic tiebreaker for events sharing an event_time.
        """
        stmt = (
            select(Alert, TransactionEvent.event_time)
            .join(TransactionEvent, TransactionEvent.seq == Alert.event_seq)
            .order_by(TransactionEvent.event_time.desc(), Alert.event_seq.desc())
        )
        if active_only:
            stmt = stmt.where(Alert.acknowledged_at.is_(None))
        rows = (await self._session.execute(stmt)).all()
        return [(alert, event_time) for alert, event_time in rows]

    async def acknowledge(self, alert_id: int, user_id: int) -> tuple[Alert, datetime] | None:
        alert = await self._session.get(Alert, alert_id)
        if alert is None:
            return None
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)  # wall clock: a real operator action
        await self._session.flush()
        event_time = await self._session.scalar(
            select(TransactionEvent.event_time).where(TransactionEvent.seq == alert.event_seq)
        )
        return alert, event_time
