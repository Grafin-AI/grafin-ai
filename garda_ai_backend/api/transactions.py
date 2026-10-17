from fastapi import APIRouter, HTTPException, Query, status

from garda_ai_backend.api.deps import CurrentUserDep, NowDep, SessionDep
from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.api.users_view import can_unmask
from garda_ai_backend.api.view_schemas import LiveItem, LiveResponse, TransactionDetail
from garda_ai_backend.repositories.transactions import TransactionsRepository

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("/live", response_model=LiveResponse)
async def live(
    session: SessionDep,
    now: NowDep,
    _: CurrentUserDep,
    after_seq: int | None = None,
    limit: int = Query(default=50, le=200),
) -> LiveResponse:
    rows = await TransactionsRepository(session).live_window(now, after_seq, limit)
    return LiveResponse(items=[LiveItem(**r) for r in rows])


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def detail(
    transaction_id: int, session: SessionDep, user: CurrentUserDep, unmasked: bool = False
) -> TransactionDetail:
    row = await TransactionsRepository(session).detail(transaction_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    if not can_unmask(user, unmasked):
        # Same masking rule as the Users view.
        for key in ("from_entity_name", "to_entity_name"):
            if row[key] is not None:
                row[key] = mask_name(row[key])
    return TransactionDetail(**row)
