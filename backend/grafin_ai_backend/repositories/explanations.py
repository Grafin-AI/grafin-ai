from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.config import Settings
from grafin_ai_backend.schema import StoredExplanation, Transaction

if TYPE_CHECKING:
    from grafin_ai_backend.repositories.explanations_firestore import (
        FirestoreExplanationsRepository,
    )


class ExplanationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: int) -> StoredExplanation | None:
        stmt = select(StoredExplanation).where(
            StoredExplanation.transaction_id == transaction_id
        ).execution_options(populate_existing=True)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def transaction_exists(self, transaction_id: int) -> bool:
        found = await self._session.scalar(
            select(Transaction.id).where(Transaction.id == transaction_id)
        )
        return found is not None

    async def insert_if_absent(self, values: dict[str, Any]) -> StoredExplanation:
        """INSERT ... ON CONFLICT DO NOTHING, commit, then read back: when two requests
        race, both return the row that won."""
        stmt = insert(StoredExplanation).values(**values).on_conflict_do_nothing(
            index_elements=[StoredExplanation.transaction_id]
        )
        await self._session.execute(stmt)
        await self._session.commit()
        row = await self.get(values["transaction_id"])
        assert row is not None
        return row

    async def set_str_draft_if_absent(
        self, transaction_id: int, draft: dict[str, Any], at: datetime
    ) -> StoredExplanation:
        """First draft wins (UPDATE ... WHERE str_draft IS NULL), then read back."""
        stmt = (
            update(StoredExplanation)
            .where(
                StoredExplanation.transaction_id == transaction_id,
                StoredExplanation.str_draft.is_(None),
            )
            .values(str_draft=draft, str_generated_at=at)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        row = await self.get(transaction_id)
        assert row is not None
        return row


def explanations_repository(
    session: AsyncSession, settings: Settings | None = None
) -> "ExplanationsRepository | FirestoreExplanationsRepository":
    """Pick the explanation store by ``GRAFIN_EXPLANATION_STORE`` (default postgres)."""
    if settings is not None and settings.explanation_store == "firestore":
        from grafin_ai_backend.repositories.explanations_firestore import (
            FirestoreExplanationsRepository,
            get_firestore_client,
        )
        from grafin_ai_backend.services.explain.llm import resolve_model

        return FirestoreExplanationsRepository(
            session, get_firestore_client(settings), resolve_model(settings)
        )
    return ExplanationsRepository(session)
