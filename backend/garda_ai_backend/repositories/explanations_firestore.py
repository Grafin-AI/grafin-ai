"""Firestore-backed explanation store (GARDA_EXPLANATION_STORE=firestore).

Same interface as ``ExplanationsRepository``; transactions themselves stay in
Postgres, so ``transaction_exists`` still queries the SQL session. Collection
``transaction_explanations`` (doc id = str(transaction_id)) holds the same fields as
the Postgres row plus ``created_at``; successfully generated LTKM drafts are also
mirrored (best effort) to collection ``str_drafts``.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.config import Settings
from garda_ai_backend.repositories.explanations import ExplanationsRepository
from garda_ai_backend.schema import StoredExplanation

log = structlog.get_logger()

EXPLANATIONS_COLLECTION = "transaction_explanations"
STR_DRAFTS_COLLECTION = "str_drafts"

# Columns of StoredExplanation; the Firestore doc stores exactly these (+ created_at).
_FIELDS = tuple(c.name for c in StoredExplanation.__table__.columns)

_client: Any = None


def get_firestore_client(settings: Settings) -> Any:
    """One lazily created AsyncClient per process (Application Default Credentials)."""
    global _client
    if _client is None:
        from google.cloud import firestore  # imported lazily: only needed in this mode

        _client = firestore.AsyncClient(
            project=settings.firestore_project, database=settings.firestore_database
        )
    return _client


def _to_row(data: dict[str, Any]) -> StoredExplanation:
    # A transient (never added to a session) ORM object, so callers keep using the
    # same attribute access as with the Postgres repository.
    return StoredExplanation(**{k: data.get(k) for k in _FIELDS})


class FirestoreExplanationsRepository:
    def __init__(self, session: AsyncSession, client: Any, model_name: str = "") -> None:
        self._session = session
        self._client = client
        self._model_name = model_name

    def _doc(self, transaction_id: int) -> Any:
        return self._client.collection(EXPLANATIONS_COLLECTION).document(str(transaction_id))

    async def get(self, transaction_id: int) -> StoredExplanation | None:
        snap = await self._doc(transaction_id).get()
        if not snap.exists:
            return None
        return _to_row(snap.to_dict() or {})

    async def transaction_exists(self, transaction_id: int) -> bool:
        return await ExplanationsRepository(self._session).transaction_exists(transaction_id)

    async def insert_if_absent(self, values: dict[str, Any]) -> StoredExplanation:
        """``create()`` fails with AlreadyExists when a doc is there: keep the existing
        one (ON CONFLICT DO NOTHING semantics), then read back the stored doc."""
        from google.api_core.exceptions import AlreadyExists

        data = {k: values.get(k) for k in _FIELDS}
        data["created_at"] = datetime.now(UTC)
        try:
            await self._doc(values["transaction_id"]).create(data)
        except AlreadyExists:
            pass
        row = await self.get(values["transaction_id"])
        assert row is not None
        return row

    async def set_str_draft_if_absent(
        self, transaction_id: int, draft: dict[str, Any], at: datetime
    ) -> StoredExplanation:
        """First draft wins on the explanation doc (read-then-update; good enough for a
        per-analyst click), then mirror it to ``str_drafts`` without failing the call."""
        current = await self.get(transaction_id)
        assert current is not None
        if current.str_draft is None:
            await self._doc(transaction_id).update({"str_draft": draft, "str_generated_at": at})
        row = await self.get(transaction_id)
        assert row is not None and row.str_draft is not None
        await self._mirror_str_draft(transaction_id, row.str_draft, row.str_generated_at or at)
        return row

    async def _mirror_str_draft(
        self, transaction_id: int, draft: dict[str, Any], at: datetime
    ) -> None:
        try:
            await self._client.collection(STR_DRAFTS_COLLECTION).document(
                str(transaction_id)
            ).set({
                "transaction_id": transaction_id,
                "draft": draft,
                "generated_at": at,
                "model": self._model_name,
            })
        except Exception:  # noqa: BLE001 - the mirror is best effort by design
            log.warning(
                "str_draft_firestore_write_failed", transaction_id=transaction_id, exc_info=True
            )
