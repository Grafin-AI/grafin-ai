from fastapi import APIRouter, HTTPException, Query, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep, SimNowDep
from garda_ai_backend.api.view_schemas import LiveItem, LiveResponse, TransactionDetail
from garda_ai_backend.repositories.transactions import TransactionsRepository

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("/live", response_model=LiveResponse)
async def live(
    session: SessionDep,
    sim_now: SimNowDep,
    _: CurrentUserDep,
    after_seq: int | None = None,
    limit: int = Query(default=50, le=200),
) -> LiveResponse:
    rows = await TransactionsRepository(session).live_window(sim_now, after_seq, limit)
    return LiveResponse(items=[LiveItem(**r) for r in rows])


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def detail(transaction_id: int, session: SessionDep, _: CurrentUserDep) -> TransactionDetail:
    row = await TransactionsRepository(session).detail(transaction_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return TransactionDetail(**row)
