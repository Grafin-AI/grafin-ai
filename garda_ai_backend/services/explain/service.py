"""Explanation orchestration: stored row -> evidence -> factors -> LLM or rules.

Only LLM explanations are persisted (table ``transaction_explanations``); a rules
fallback is returned with ``persisted: False`` and never stored, so the analyst can
retry once the provider is back. Read path only; nothing here is called from ingest.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.config import Settings
from garda_ai_backend.repositories.explanations import explanations_repository
from garda_ai_backend.schema import StoredExplanation
from garda_ai_backend.services.explain.evidence import compute_evidence
from garda_ai_backend.services.explain.knowledge import (
    confidence_from_score,
    deterministic_reason_code,
    filter_references,
    reference_refs,
    retrieve,
)
from garda_ai_backend.services.explain.llm import llm_narrative, resolve_model
from garda_ai_backend.services.explain.rules import (
    NARRATIVE_FIELDS,
    action_verb,
    risk_factors,
    rules_narrative,
)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def row_payload(row: StoredExplanation) -> dict[str, Any]:
    return {
        "transaction_id": row.transaction_id,
        "source": row.source,
        "model": row.model,
        **{k: getattr(row, k) for k in NARRATIVE_FIELDS},
        "reason_code": row.reason_code,
        "confidence": row.confidence,
        "references": row.references,
        "risk_factors": row.risk_factors,
        "evidence": row.evidence,
        "generated_at": iso_z(row.generated_at),
        "persisted": True,
        "str_draft": row.str_draft,
    }


async def load_explanation(
    session: AsyncSession, transaction_id: int, settings: Settings | None = None
) -> dict[str, Any] | None:
    row = await explanations_repository(session, settings).get(transaction_id)
    return row_payload(row) if row is not None else None


async def _narrate(
    client: httpx.AsyncClient | None, settings: Settings, ev: dict, factors: list,
    action: str, refs: list, transaction_id: int,
) -> dict[str, Any] | None:
    if client is not None:
        return await llm_narrative(client, settings, ev, factors, action, refs, transaction_id)
    async with httpx.AsyncClient() as own:
        return await llm_narrative(own, settings, ev, factors, action, refs, transaction_id)


async def generate_explanation(
    session: AsyncSession,
    client: httpx.AsyncClient | None,
    settings: Settings,
    transaction_id: int,
    generated_by: str,
) -> dict[str, Any] | None:
    """Stored explanation if any (no LLM call); else generate. None = unknown transaction."""
    repo = explanations_repository(session, settings)
    existing = await repo.get(transaction_id)
    if existing is not None:
        return row_payload(existing)

    evidence = await compute_evidence(session, transaction_id)
    if evidence is None:
        return None
    factors = risk_factors(evidence)
    codes = [f["code"] for f in factors]
    action = action_verb(evidence)
    refs = retrieve(codes, evidence.get("typology"))
    reason = deterministic_reason_code(evidence.get("typology"), codes)
    confidence = confidence_from_score(evidence["fraud_score"])

    narrative = None
    if settings.llm_provider != "none":
        narrative = await _narrate(
            client, settings, evidence, factors, action, refs, transaction_id
        )

    if narrative is None:
        return {
            "transaction_id": transaction_id,
            "source": "rules",
            "model": None,
            **rules_narrative(evidence, factors),
            "reason_code": reason,
            "confidence": confidence,
            "references": reference_refs(refs),
            "risk_factors": factors,
            "evidence": evidence,
            "generated_at": iso_z(datetime.now(UTC)),
            "persisted": False,
            "str_draft": None,
        }

    row = await repo.insert_if_absent({
        "transaction_id": transaction_id,
        "source": "llm",
        "model": resolve_model(settings),
        **{k: narrative[k] for k in NARRATIVE_FIELDS},
        "reason_code": narrative["reason_code"] or reason,
        "confidence": narrative["confidence"] or confidence,
        "references": filter_references(narrative["references"], refs) or reference_refs(refs),
        "risk_factors": factors,
        "evidence": evidence,
        "generated_by": generated_by,
        "generated_at": datetime.now(UTC),
    })
    return row_payload(row)
