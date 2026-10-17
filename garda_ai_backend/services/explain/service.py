"""Explanation orchestration: Redis cache -> evidence -> factors -> LLM or rules.

Read path only; nothing here is called from ingest.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.config import Settings
from garda_ai_backend.services.explain.evidence import compute_evidence
from garda_ai_backend.services.explain.llm import llm_narrative, resolve_model
from garda_ai_backend.services.explain.rules import action_verb, risk_factors, rules_narrative

log = structlog.get_logger()

CACHE_TTL_S = 24 * 3600
# A rules fallback caused by an LLM failure is cached briefly so a transient
# provider outage does not pin the degraded answer for a whole day.
FALLBACK_TTL_S = 300


def cache_key(transaction_id: int) -> str:
    return f"expl:{transaction_id}"


async def _cache_get(redis: Redis, key: str) -> dict | None:
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — cache is best-effort
        log.warning("explain.cache_get_failed", error=type(exc).__name__)
        return None


async def _cache_set(redis: Redis, key: str, value: dict, ttl: int) -> None:
    try:
        await redis.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        log.warning("explain.cache_set_failed", error=type(exc).__name__)


async def _narrate(
    client: httpx.AsyncClient | None, settings: Settings, ev: dict, factors: list, action: str
) -> dict[str, str] | None:
    if client is not None:
        return await llm_narrative(client, settings, ev, factors, action)
    async with httpx.AsyncClient() as own:
        return await llm_narrative(own, settings, ev, factors, action)


async def explain_transaction(
    session: AsyncSession,
    redis: Redis,
    client: httpx.AsyncClient | None,
    settings: Settings,
    transaction_id: int,
) -> dict[str, Any] | None:
    """Full explanation payload, or None if the transaction is unknown."""
    key = cache_key(transaction_id)
    cached = await _cache_get(redis, key)
    if cached is not None:
        return cached

    evidence = await compute_evidence(session, transaction_id)
    if evidence is None:
        return None
    factors = risk_factors(evidence)
    action = action_verb(evidence)

    narrative: dict[str, str] | None = None
    llm_enabled = settings.llm_provider != "none"
    if llm_enabled:
        narrative = await _narrate(client, settings, evidence, factors, action)
    source, model = ("llm", resolve_model(settings)) if narrative else ("rules", None)
    if narrative is None:
        narrative = rules_narrative(evidence, factors)

    result = {
        "transaction_id": transaction_id,
        "source": source,
        "model": model,
        **narrative,
        "risk_factors": factors,
        "evidence": evidence,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    ttl = FALLBACK_TTL_S if (llm_enabled and source == "rules") else CACHE_TTL_S
    await _cache_set(redis, key, result, ttl)
    return result
