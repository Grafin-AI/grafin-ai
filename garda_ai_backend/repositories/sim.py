from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import SimState


class SimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_state(self) -> SimState | None:
        return await self._session.get(SimState, 1)

    async def get_sim_now(self) -> datetime | None:
        state = await self.get_state()
        return state.sim_now if state else None

    async def update_state(
        self,
        running: bool | None = None,
        speed: float | None = None,
        sim_now: datetime | None = None,
    ) -> SimState:
        state = await self._session.get(SimState, 1)
        if state is None:
            raise ValueError("sim_state not seeded")
        if running is not None:
            state.running = running
        if speed is not None:
            state.speed = Decimal(str(speed))
        if sim_now is not None:
            state.sim_now = sim_now
        await self._session.flush()
        return state
