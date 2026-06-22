from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from garda_ai_backend.api.deps import CurrentUser, CurrentUserDep, SessionDep, require_role
from garda_ai_backend.api.view_schemas import SimControlRequest, SimStateResponse
from garda_ai_backend.repositories.sim import SimRepository

router = APIRouter(prefix="/api/v1/sim", tags=["sim"])

AdminDep = Annotated[CurrentUser, Depends(require_role("admin"))]


@router.get("/state", response_model=SimStateResponse)
async def get_state(session: SessionDep, _: CurrentUserDep) -> SimStateResponse:
    state = await SimRepository(session).get_state()
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    return SimStateResponse(sim_now=state.sim_now, speed=float(state.speed), running=state.running)


@router.post("/control", response_model=SimStateResponse)
async def control(
    body: SimControlRequest,
    session: SessionDep,
    _: AdminDep,
) -> SimStateResponse:
    repo = SimRepository(session)
    state = await repo.update_state(running=body.running, speed=body.speed, sim_now=body.sim_now)
    await session.commit()
    return SimStateResponse(sim_now=state.sim_now, speed=float(state.speed), running=state.running)
