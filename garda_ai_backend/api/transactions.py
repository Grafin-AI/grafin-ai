from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query, status

from garda_ai_backend.api.deps import (
    CurrentUser,
    CurrentUserDep,
    HttpClientDep,
    NowDep,
    SessionDep,
    SettingsDep,
)
from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.api.users_view import can_unmask
from garda_ai_backend.api.view_schemas import (
    LiveItem,
    LiveResponse,
    TransactionDetail,
    TransactionExplanation,
)
from garda_ai_backend.repositories.explanations import ExplanationsRepository
from garda_ai_backend.repositories.transactions import TransactionsRepository
from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.services.explain import generate_explanation, load_explanation

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


async def _not_found_or(
    session: SessionDep, transaction_id: int, detail: str, code: int
) -> NoReturn:
    """Raise ``detail``/``code`` when the transaction exists, else 404 transaction not found."""
    if await ExplanationsRepository(session).transaction_exists(transaction_id):
        raise HTTPException(status_code=code, detail=detail)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")


async def _username(session: SessionDep, user: CurrentUser) -> str:
    found = await UserRepository(session).get_by_id(user.id)
    return found.email if found is not None else f"user-{user.id}"


@router.get("/{transaction_id}/explanation", response_model=TransactionExplanation)
async def get_explanation(
    transaction_id: int, session: SessionDep, _: CurrentUserDep
) -> TransactionExplanation:
    """The stored (LLM) explanation. Nothing is generated here: 404
    ``explanation_not_generated`` tells the UI to offer the generate button."""
    result = await load_explanation(session, transaction_id)
    if result is None:
        await _not_found_or(
            session, transaction_id, "explanation_not_generated", status.HTTP_404_NOT_FOUND
        )
    return TransactionExplanation(**result)


@router.post("/{transaction_id}/explanation", response_model=TransactionExplanation)
async def post_explanation(
    transaction_id: int,
    session: SessionDep,
    settings: SettingsDep,
    http_client: HttpClientDep,
    user: CurrentUserDep,
) -> TransactionExplanation:
    """Generate (or return the stored) explanation. LLM results are persisted; a rules
    fallback comes back with ``persisted: false`` and is not stored."""
    result = await generate_explanation(
        session, http_client, settings, transaction_id, await _username(session, user)
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return TransactionExplanation(**result)
