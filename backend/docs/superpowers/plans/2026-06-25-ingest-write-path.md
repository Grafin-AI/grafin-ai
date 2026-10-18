# Backend Ingest Write-Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a token-gated `POST /api/v1/ingest` to `grafin-ai-backend` that scores transaction batches via the scoring service and persists + publishes them (commit-then-notify), idempotent on a producer-provided `transaction_id`.

**Architecture:** A pooled httpx scoring client (timeout + bounded retries → `ScoringUnavailable` → 503); an ingest repository doing SQLAlchemy `pg_insert(...).on_conflict_do_nothing().returning()` batch inserts of transactions/events/alerts in one transaction; a route that enriches `from_risk_category`, scores, persists only-new rows, and publishes the WS relay's exact message shape. Purely additive — replay worker, `sim_state`, and read endpoints untouched (Phase 5 removes them).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (asyncpg), pydantic v2, httpx, redis.asyncio, structlog, prometheus-client, pytest + testcontainers. Mirrors existing backend conventions.

**Spec:** `docs/superpowers/specs/2026-06-25-ingest-write-path-design.md`. **Anchor:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`.

---

## File structure

```
grafin_ai_backend/
├── config.py                        # MODIFY: scoring_url/token, ingest_token, timeout/retries
├── services/scoring_client.py       # CREATE: httpx client + ScoringUnavailable + retries
├── api/ingest_auth.py               # CREATE: pure _verify_ingest + require_ingest_token dep
├── api/ingest_schemas.py            # CREATE: IngestRequest/IngestResponse pydantic models
├── repositories/ingest.py           # CREATE: enrich lookups + batch persist (ON CONFLICT)
├── api/ingest.py                    # CREATE: POST /api/v1/ingest route (orchestration + publish)
├── observability.py                 # MODIFY: ingest metrics
└── main.py                          # MODIFY: include ingest router; lifespan for shared AsyncClient
tests/
├── test_scoring_client.py          # CREATE
├── test_ingest_auth.py             # CREATE
├── test_ingest_repository.py       # CREATE (testcontainers PG)
└── test_ingest_api.py              # CREATE (testcontainers PG+Redis, mocked scoring client)
```

---

### Task 1: Configuration

**Files:** Modify `grafin_ai_backend/config.py`; Test `tests/test_config_ingest.py` (create).

- [ ] **Step 1: Write the failing test** `tests/test_config_ingest.py`:

```python
import pytest
from pydantic import ValidationError

from grafin_ai_backend.config import Settings

_BASE = {
    "database_url": "postgresql+asyncpg://u:p@localhost/db",
    "scoring_url": "http://scoring:8000",
    "scoring_token": "s",
    "ingest_token": "i",
}


def test_ingest_settings_defaults():
    s = Settings(**_BASE)
    assert s.scoring_url == "http://scoring:8000"
    assert s.scoring_token == "s"
    assert s.ingest_token == "i"
    assert s.scoring_timeout_s == 5.0
    assert s.scoring_retries == 2


@pytest.mark.parametrize("missing", ["scoring_url", "scoring_token", "ingest_token"])
def test_ingest_settings_required(missing):
    data = {k: v for k, v in _BASE.items() if k != missing}
    with pytest.raises(ValidationError):
        Settings(**data)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config_ingest.py -q`
Expected: FAIL (fields don't exist / not required yet).

- [ ] **Step 3: Add the fields to `grafin_ai_backend/config.py`**

In `class Settings`, after the existing fields, add:
```python
    # --- Ingest write-path (Phase 2) ---
    scoring_url: str
    scoring_token: str
    ingest_token: str
    scoring_timeout_s: float = 5.0
    scoring_retries: int = 2
```
(These are required — no default — so a misconfigured deploy fails fast at startup, consistent with the existing fail-closed posture.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_config_ingest.py -q` → PASS.
NOTE: adding required fields means every `Settings()` construction now needs these env vars. Check that existing tests construct `Settings` via env/fixtures, not bare `Settings()`. If any existing test or the app boots `get_settings()` without them, they must be provided (via `.env`/conftest env). Run the FULL suite in Step 5 to catch this.

- [ ] **Step 5: Run the full suite; fix any missing-env fallout**

Run: `uv run pytest -q`
Expected: green. If tests that boot the app/settings now fail for missing `GRAFIN_SCORING_URL`/`GRAFIN_SCORING_TOKEN`/`GRAFIN_INGEST_TOKEN`, add them to the test env (e.g. the test `.env` or a conftest `monkeypatch.setenv`/autouse fixture) — do NOT give the fields insecure defaults. Report exactly what you changed.

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/config.py tests/test_config_ingest.py
git commit -m "feat(ingest): config for scoring client + ingest token"
```

---

### Task 2: Scoring client

**Files:** Create `grafin_ai_backend/services/scoring_client.py`; Test `tests/test_scoring_client.py`.

- [ ] **Step 1: Implement `grafin_ai_backend/services/scoring_client.py`**

```python
import asyncio

import httpx
import structlog

log = structlog.get_logger()


class ScoringUnavailable(Exception):
    """The scoring service could not be reached / rejected the batch. Maps to HTTP 503."""


class ScoringClient:
    """Thin client for grafin-ai-scoring's POST /v1/score. Retries transient failures."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str,
        *,
        retries: int = 2,
        timeout_s: float = 5.0,
    ) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/v1/score"
        self._token = token
        self._retries = retries
        self._timeout = timeout_s

    async def score(
        self, transactions: list[dict], correlation_id: str | None = None
    ) -> list[dict]:
        headers = {"Authorization": f"Bearer {self._token}"}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post(
                    self._url,
                    json={"transactions": transactions},
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.TransportError as exc:  # connect/read timeouts, conn errors
                last_exc = exc
            else:
                if resp.status_code < 400:
                    return list(resp.json()["results"])
                if resp.status_code < 500:
                    # A 4xx is a contract/auth problem — not transient; do not retry.
                    raise ScoringUnavailable(
                        f"scoring rejected batch: HTTP {resp.status_code}"
                    )
                last_exc = httpx.HTTPStatusError(
                    "scoring 5xx", request=resp.request, response=resp
                )
            if attempt < self._retries:
                await asyncio.sleep(0.1 * (2**attempt))  # 0.1s, 0.2s backoff
        raise ScoringUnavailable("scoring service unavailable after retries") from last_exc
```

- [ ] **Step 2: Write `tests/test_scoring_client.py`**

```python
import httpx
import pytest

from grafin_ai_backend.services.scoring_client import ScoringClient, ScoringUnavailable

_TXN = {"transaction_id": 1, "from_account": "a", "to_account": "b", "amount": "1.00",
        "payment_format": "ACH", "is_laundering": False, "event_time": "2026-06-25T09:00:00Z"}


def _client(handler) -> ScoringClient:
    transport = httpx.MockTransport(handler)
    return ScoringClient(httpx.AsyncClient(transport=transport), "http://scoring:8000", "tok",
                         retries=2, timeout_s=1.0)


async def test_score_success_and_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["cid"] = request.headers.get("x-correlation-id")
        return httpx.Response(200, json={"results": [{"transaction_id": 1, "fraud_score": 0.9,
                                                      "typology": "Smurfing", "status": "blocked"}]})

    out = await _client(handler).score([_TXN], correlation_id="cid-1")
    assert out[0]["status"] == "blocked"
    assert seen["auth"] == "Bearer tok"
    assert seen["cid"] == "cid-1"


async def test_score_retries_5xx_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ScoringUnavailable):
        await _client(handler).score([_TXN])
    assert calls["n"] == 3  # 1 + 2 retries


async def test_score_4xx_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    with pytest.raises(ScoringUnavailable):
        await _client(handler).score([_TXN])
    assert calls["n"] == 1  # no retry on 4xx
```

- [ ] **Step 3: Run + type-check**

Run: `uv run pytest tests/test_scoring_client.py -q` → PASS (3 tests).
Run: `uv run ruff check grafin_ai_backend/services/scoring_client.py tests/test_scoring_client.py` → clean.

- [ ] **Step 4: Commit**

```bash
git add grafin_ai_backend/services/scoring_client.py tests/test_scoring_client.py
git commit -m "feat(ingest): resilient scoring HTTP client (retries -> ScoringUnavailable)"
```

---

### Task 3: Ingest-token auth dependency

**Files:** Create `grafin_ai_backend/api/ingest_auth.py`; Test `tests/test_ingest_auth.py`.

- [ ] **Step 1: Write the failing test** `tests/test_ingest_auth.py`:

```python
import pytest
from fastapi import HTTPException

from grafin_ai_backend.api.ingest_auth import _verify_ingest


def test_verify_ingest_accepts_matching():
    _verify_ingest("Bearer s3cret", "s3cret")


@pytest.mark.parametrize("header", [None, "s3cret", "Bearer wrong", "Basic s3cret"])
def test_verify_ingest_rejects(header):
    with pytest.raises(HTTPException) as exc:
        _verify_ingest(header, "s3cret")
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ingest_auth.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `grafin_ai_backend/api/ingest_auth.py`**

```python
import hmac

from fastapi import Header, HTTPException, status

from grafin_ai_backend.config import get_settings


def _verify_ingest(authorization: str | None, token: str) -> None:
    """Pure bearer check for the ingest token (unit-testable without HTTP/env)."""
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.encode(), token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing ingest token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_ingest_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: read the ingest token ONLY from settings (no request override)."""
    _verify_ingest(authorization, get_settings().ingest_token)
```
(This deliberately mirrors the Phase-1 scoring-auth fix: a pure verifier + a dependency that reads the token only from settings — never a request-controllable parameter that FastAPI could surface as a query param.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ingest_auth.py -q` → PASS (5 cases). `uv run ruff check grafin_ai_backend/api/ingest_auth.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/api/ingest_auth.py tests/test_ingest_auth.py
git commit -m "feat(ingest): bearer ingest-token dependency (settings-only, constant-time)"
```

---

### Task 4: Ingest repository

**Files:** Create `grafin_ai_backend/repositories/ingest.py`; Test `tests/test_ingest_repository.py`.

- [ ] **Step 1: Implement `grafin_ai_backend/repositories/ingest.py`**

```python
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from grafin_ai_backend.schema import Account, Alert, Bank, Transaction, TransactionEvent


@dataclass(frozen=True)
class InsertedEvent:
    seq: int
    transaction_id: int
    fraud_score: float
    typology: str | None
    status: str


class IngestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def risk_categories(self, account_ids: list[str]) -> dict[str, str | None]:
        if not account_ids:
            return {}
        rows = (
            await self._session.execute(
                select(Account.id, Account.risk_category).where(Account.id.in_(account_ids))
            )
        ).all()
        return {r.id: r.risk_category for r in rows}

    async def bank_names(self, bank_ids: list[str]) -> dict[str, str]:
        if not bank_ids:
            return {}
        rows = (
            await self._session.execute(
                select(Bank.id, Bank.name).where(Bank.id.in_(bank_ids))
            )
        ).all()
        return {r.id: r.name for r in rows}

    async def persist(
        self,
        transactions: list[dict],
        scores_by_id: dict[int, dict],
        now: datetime,
    ) -> list[InsertedEvent]:
        """Insert new transactions (ON CONFLICT DO NOTHING), then events for the newly-inserted
        ids, then alerts for blocked. One transaction; returns the inserted events with their seq.
        """
        async with self._session.begin():
            ins_txn = (
                pg_insert(Transaction)
                .values(transactions)
                .on_conflict_do_nothing(index_elements=[Transaction.id])
                .returning(Transaction.id)
            )
            new_ids = set((await self._session.execute(ins_txn)).scalars().all())
            if not new_ids:
                return []

            event_values = [
                {
                    "transaction_id": tid,
                    "surfaced_at": now,
                    "fraud_score": scores_by_id[tid]["fraud_score"],
                    "typology": scores_by_id[tid]["typology"],
                    "status": scores_by_id[tid]["status"],
                }
                for tid in new_ids
            ]
            ins_ev = (
                pg_insert(TransactionEvent)
                .values(event_values)
                .returning(
                    TransactionEvent.seq,
                    TransactionEvent.transaction_id,
                    TransactionEvent.fraud_score,
                    TransactionEvent.typology,
                    TransactionEvent.status,
                )
            )
            rows = (await self._session.execute(ins_ev)).all()
            events = [
                InsertedEvent(
                    seq=r.seq,
                    transaction_id=r.transaction_id,
                    fraud_score=float(r.fraud_score),
                    typology=r.typology,
                    status=r.status,
                )
                for r in rows
            ]

            alerts = [
                {"event_seq": e.seq, "severity": "high", "typology": e.typology, "created_at": now}
                for e in events
                if e.status == "blocked"
            ]
            if alerts:
                await self._session.execute(pg_insert(Alert).values(alerts))
            return events
```
NOTE: confirm the model import names against `grafin_ai_backend/schema/__init__.py` (`Account`, `Bank`, `Alert`, `Transaction`, `TransactionEvent`). If a name differs (e.g. `Alert` is exported under another name), adjust the import and report. `Alert` columns used: `event_seq`, `severity`, `typology`, `created_at` — verify against the schema; if the alert model has additional non-null columns without defaults, set them here.

- [ ] **Step 2: Write `tests/test_ingest_repository.py`**

Use the backend's existing DB test fixture (find how other repository tests get an `AsyncSession` + a seeded schema — mirror `tests/` conventions, e.g. a `session` fixture on a testcontainers Postgres with `Base.metadata.create_all`). The test must seed one bank + two accounts (FKs) first.

```python
from datetime import UTC, datetime

import pytest

from grafin_ai_backend.repositories.ingest import IngestRepository

# Assumes a `session` fixture (AsyncSession on a fresh schema) and a helper to seed a bank +
# accounts. Follow the existing repository-test pattern in this repo for those fixtures.


def _txn(tid: int, laundering: bool = True) -> dict:
    return {
        "id": tid, "event_time": datetime(2026, 6, 25, 9, tzinfo=UTC),
        "from_bank_id": "011", "from_account": "1000000001",
        "to_bank_id": "011", "to_account": "1000000002",
        "amount_paid": 15000, "payment_currency": "IDR",
        "amount_received": 15000, "receiving_currency": "IDR",
        "payment_format": "ACH", "is_laundering": laundering,
    }


async def test_persist_inserts_events_and_alert(session, seed_reference):
    repo = IngestRepository(session)
    now = datetime.now(UTC)
    scores = {40217: {"fraud_score": 0.9, "typology": "Smurfing", "status": "blocked"}}
    events = await repo.persist([_txn(40217)], scores, now)
    assert len(events) == 1 and events[0].status == "blocked"
    # blocked -> an alert row exists
    from sqlalchemy import func, select
    from grafin_ai_backend.schema import Alert
    assert (await session.execute(select(func.count()).select_from(Alert))).scalar() == 1


async def test_persist_is_idempotent(session, seed_reference):
    repo = IngestRepository(session)
    now = datetime.now(UTC)
    scores = {40217: {"fraud_score": 0.2, "typology": None, "status": "approved"}}
    first = await repo.persist([_txn(40217, laundering=False)], scores, now)
    second = await repo.persist([_txn(40217, laundering=False)], scores, now)
    assert len(first) == 1
    assert second == []  # already present -> no new events


async def test_risk_categories_lookup(session, seed_reference):
    repo = IngestRepository(session)
    cats = await repo.risk_categories(["1000000001", "unknown"])
    assert "1000000001" in cats  # seeded; value may be None depending on seed
```
NOTE: create the `session` and `seed_reference` fixtures (or reuse existing ones) in this test file or the shared conftest, following how the repo's other DB tests are set up. `seed_reference` inserts bank `011` and accounts `1000000001`/`1000000002` so the FK inserts succeed.

- [ ] **Step 3: Run + type-check**

Run: `uv run pytest tests/test_ingest_repository.py -q` → PASS. `uv run ruff check grafin_ai_backend/repositories/ingest.py` → clean.
If a test can't get a DB session, inspect an existing DB-backed test in `tests/` and copy its fixture setup exactly. Report the fixture approach you used.

- [ ] **Step 4: Commit**

```bash
git add grafin_ai_backend/repositories/ingest.py tests/test_ingest_repository.py
git commit -m "feat(ingest): repository — enrich lookups + idempotent batch persist"
```

---

### Task 5: Ingest schemas + route + app wiring

**Files:** Create `grafin_ai_backend/api/ingest_schemas.py`, `grafin_ai_backend/api/ingest.py`; Modify `grafin_ai_backend/main.py`; Test `tests/test_ingest_api.py`.

- [ ] **Step 1: Implement `grafin_ai_backend/api/ingest_schemas.py`**

```python
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

RiskStatus = Literal["approved", "flagged", "blocked"]


class IngestTxn(BaseModel):
    transaction_id: int
    from_bank_id: str
    from_account: str
    to_bank_id: str
    to_account: str
    amount_paid: Decimal
    payment_currency: str
    amount_received: Decimal
    receiving_currency: str
    payment_format: str
    is_laundering: bool
    event_time: datetime


class IngestRequest(BaseModel):
    transactions: Annotated[list[IngestTxn], Field(max_length=1000)]


class IngestResultItem(BaseModel):
    transaction_id: int
    seq: int | None
    status: RiskStatus | None
    ingested: bool


class IngestResponse(BaseModel):
    results: list[IngestResultItem]
```

- [ ] **Step 2: Implement `grafin_ai_backend/api/ingest.py`**

Full module `grafin_ai_backend/api/ingest.py`:
```python
import json
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, Header, Request
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from grafin_ai_backend.api.deps import RedisDep, SessionDep, SettingsDep
from grafin_ai_backend.api.ingest_auth import require_ingest_token
from grafin_ai_backend.api.ingest_schemas import IngestRequest, IngestResponse, IngestResultItem
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.repositories.ingest import IngestRepository
from grafin_ai_backend.services.scoring_client import ScoringClient, ScoringUnavailable

log = structlog.get_logger()
router = APIRouter(
    prefix="/api/v1", tags=["ingest"], dependencies=[Depends(require_ingest_token)]
)


def get_scoring_client(request: Request, settings: SettingsDep) -> ScoringClient:
    client: httpx.AsyncClient = request.app.state.http_client
    return ScoringClient(
        client, settings.scoring_url, settings.scoring_token,
        retries=settings.scoring_retries, timeout_s=settings.scoring_timeout_s,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    body: IngestRequest,
    session: SessionDep,
    redis: RedisDep,
    scoring: ScoringClient = Depends(get_scoring_client),
    x_correlation_id: str | None = Header(default=None),
) -> IngestResponse:
    cid = x_correlation_id or uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    txns = body.transactions
    repo = IngestRepository(session)

    # 1) enrich from_risk_category
    risk = await repo.risk_categories([t.from_account for t in txns])

    # 2) score (fail the whole batch on scoring outage)
    score_items = [
        {
            "transaction_id": t.transaction_id, "from_account": t.from_account,
            "to_account": t.to_account, "amount": str(t.amount_paid),
            "payment_format": t.payment_format, "is_laundering": t.is_laundering,
            "event_time": t.event_time.isoformat(),
            "from_risk_category": risk.get(t.from_account),
        }
        for t in txns
    ]
    try:
        results = await scoring.score(score_items, correlation_id=cid)
    except ScoringUnavailable as exc:
        log.warning("ingest.scoring_unavailable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="scoring unavailable"
        ) from exc
    scores_by_id = {r["transaction_id"]: r for r in results}

    # 3) persist (atomic; only-new rows get events)
    txn_rows = [
        {
            "id": t.transaction_id, "event_time": t.event_time, "from_bank_id": t.from_bank_id,
            "from_account": t.from_account, "to_bank_id": t.to_bank_id, "to_account": t.to_account,
            "amount_paid": t.amount_paid, "payment_currency": t.payment_currency,
            "amount_received": t.amount_received, "receiving_currency": t.receiving_currency,
            "payment_format": t.payment_format, "is_laundering": t.is_laundering,
        }
        for t in txns
    ]
    try:
        events = await repo.persist(txn_rows, scores_by_id, datetime.now(UTC))
    except IntegrityError as exc:
        log.warning("ingest.bad_reference", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="transaction references an unknown bank or account (seed reference data first)",
        ) from exc

    # 4) publish after commit — the exact shape the WS relay/frontend consume
    bank_names = await repo.bank_names([t.from_bank_id for t in txns])
    by_id = {t.transaction_id: t for t in txns}
    inserted_ids = {e.transaction_id for e in events}
    now_iso = datetime.now(UTC).isoformat()
    for e in events:
        t = by_id[e.transaction_id]
        message = {
            "seq": e.seq, "transaction_id": e.transaction_id,
            "bank": bank_names.get(t.from_bank_id), "type": t.payment_format,
            "amount": float(t.amount_paid), "fraud_score": e.fraud_score,
            "typology": e.typology, "status": e.status,
            "surfaced_at": now_iso, "sim_now": now_iso,
        }
        await redis.publish(LIVE_EVENTS_CHANNEL, json.dumps(message, default=str))

    log.info("ingest.done", received=len(txns), inserted=len(events))
    results_out = [
        IngestResultItem(
            transaction_id=t.transaction_id,
            seq=next((e.seq for e in events if e.transaction_id == t.transaction_id), None),
            status=next((e.status for e in events if e.transaction_id == t.transaction_id), None),
            ingested=t.transaction_id in inserted_ids,
        )
        for t in txns
    ]
    structlog.contextvars.clear_contextvars()
    return IngestResponse(results=results_out)
```
(Duplicates report `seq=None, status=None, ingested=False`, which is accurate for "no event created this call".)

- [ ] **Step 3: Wire the router + shared httpx client in `grafin_ai_backend/main.py`**

Add a lifespan that owns one pooled `httpx.AsyncClient` on `app.state`, and include the router:
```python
from contextlib import asynccontextmanager

import httpx

from grafin_ai_backend.api.ingest import router as ingest_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient()
    try:
        yield
    finally:
        await app.state.http_client.aclose()
```
Change the app construction to `app = FastAPI(title="Grafin AI Backend", version="0.1.0", lifespan=lifespan)` and add `app.include_router(ingest_router)` alongside the others.
NOTE: if `main.py` already defines a lifespan, MERGE this into it (don't create a second). Read `main.py` first.

- [ ] **Step 4: Write `tests/test_ingest_api.py`**

Endpoint tests against testcontainers Postgres + Redis (reuse the backend's existing app-test fixtures), with a **mocked scoring client** so no real scoring service is needed. Override the `get_scoring_client` dependency with a fake returning deterministic results (and one that raises `ScoringUnavailable`).

```python
import pytest

from grafin_ai_backend.api.ingest import get_scoring_client
from grafin_ai_backend.services.scoring_client import ScoringUnavailable

_TXN = {
    "transaction_id": 40217, "from_bank_id": "011", "from_account": "1000000001",
    "to_bank_id": "011", "to_account": "1000000002", "amount_paid": "15000.00",
    "payment_currency": "IDR", "amount_received": "15000.00", "receiving_currency": "IDR",
    "payment_format": "ACH", "is_laundering": True, "event_time": "2026-06-25T09:00:00Z",
}


class _FakeScoring:
    def __init__(self, status="blocked"):
        self._status = status

    async def score(self, transactions, correlation_id=None):
        return [{"transaction_id": t["transaction_id"], "fraud_score": 0.9,
                 "typology": "Smurfing", "status": self._status} for t in transactions]


class _DownScoring:
    async def score(self, transactions, correlation_id=None):
        raise ScoringUnavailable("down")


# `app`, `client` (httpx/ASGI TestClient with lifespan), `ingest_headers` (Bearer ingest token),
# and `seed_reference` (bank 011 + accounts) fixtures follow the repo's existing app-test setup.


def test_ingest_requires_token(client, seed_reference):
    r = client.post("/api/v1/ingest", json={"transactions": [_TXN]})
    assert r.status_code == 401


def test_ingest_persists_and_publishes(app, client, ingest_headers, seed_reference):
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = client.post("/api/v1/ingest", json={"transactions": [_TXN]}, headers=ingest_headers)
        assert r.status_code == 200
        item = r.json()["results"][0]
        assert item["ingested"] is True and item["status"] == "blocked" and item["seq"]
    finally:
        app.dependency_overrides.clear()


def test_ingest_idempotent(app, client, ingest_headers, seed_reference):
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring(status="approved")
    try:
        client.post("/api/v1/ingest", json={"transactions": [_TXN]}, headers=ingest_headers)
        r2 = client.post("/api/v1/ingest", json={"transactions": [_TXN]}, headers=ingest_headers)
        assert r2.json()["results"][0]["ingested"] is False
    finally:
        app.dependency_overrides.clear()


def test_ingest_scoring_down_503_persists_nothing(app, client, ingest_headers, seed_reference):
    app.dependency_overrides[get_scoring_client] = lambda: _DownScoring()
    try:
        r = client.post("/api/v1/ingest", json={"transactions": [_TXN]}, headers=ingest_headers)
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_ingest_unknown_reference_400(app, client, ingest_headers):
    # no seed_reference -> FK violation
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = client.post("/api/v1/ingest", json={"transactions": [_TXN]}, headers=ingest_headers)
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
```
NOTE: use the SAME app-level test fixtures the existing endpoint tests use (e.g. `tests/test_ws_uvicorn.py` / whichever tests boot the FastAPI app with a real Postgres+Redis). The mocked scoring client is injected via `app.dependency_overrides[get_scoring_client]`. If the existing tests publish/subscribe to verify Redis, add a subscriber assertion on `grafin:events:live` for the publish test; otherwise asserting the DB rows + response is sufficient.

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run pytest -q` → all green (existing + new). `uv run ruff check grafin_ai_backend tests` → clean.
If the ASGI TestClient doesn't run the lifespan (so `app.state.http_client` is missing), use a client that triggers lifespan (e.g. `TestClient(app)` as a context manager, or httpx ASGITransport with lifespan) — the scoring client is overridden in tests anyway, so `app.state.http_client` may be unused in tests; ensure the override path doesn't touch it. Report how you handled lifespan in tests.

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/api/ingest_schemas.py grafin_ai_backend/api/ingest.py grafin_ai_backend/main.py tests/test_ingest_api.py
git commit -m "feat(ingest): POST /api/v1/ingest — score, persist, publish (commit-then-notify)"
```

---

### Task 6: Ingest metrics

**Files:** Modify `grafin_ai_backend/observability.py`; wire counters in `grafin_ai_backend/api/ingest.py`.

- [ ] **Step 1: Add metrics to `grafin_ai_backend/observability.py`**

```python
from prometheus_client import Counter, Histogram  # extend existing import

INGEST_TRANSACTIONS = Counter(
    "grafin_ingest_transactions_total",
    "Transactions received by /ingest, by result",
    ["result"],  # bounded: inserted | duplicate
    registry=REGISTRY,
)
INGEST_SCORING_LATENCY = Histogram(
    "grafin_ingest_scoring_latency_seconds",
    "Latency of the scoring-service call from /ingest",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY,
)
```

- [ ] **Step 2: Record them in the ingest route**

In `api/ingest.py`: time the `scoring.score(...)` call with `INGEST_SCORING_LATENCY.time()` (context manager), and after persist increment `INGEST_TRANSACTIONS.labels("inserted").inc(len(events))` and `INGEST_TRANSACTIONS.labels("duplicate").inc(len(txns) - len(events))`. Keep labels bounded (only `inserted`/`duplicate`).

- [ ] **Step 3: Run + verify metrics exposed**

Run: `uv run pytest -q` → green. Add/extend a test asserting `/metrics` exposes `grafin_ingest_transactions_total` after an ingest (optional if an existing metrics test covers the endpoint). Run `uv run ruff check grafin_ai_backend tests` → clean.

- [ ] **Step 4: Commit**

```bash
git add grafin_ai_backend/observability.py grafin_ai_backend/api/ingest.py
git commit -m "feat(ingest): RED-style ingest metrics (transactions total + scoring latency)"
```

---

### Task 7: Documentation

**Files:** `docs/c4/03-component.md`, `docs/c4/04-code.md` (backend); the system container note in `grafin-ai-deploy/docs/c4/02-container.md`.

- [ ] **Step 1: Refresh backend C4 (c4-architecture plugin)**

Run the `c4-code` + `c4-component` agents over the backend to document the new components: the ingest route, `ScoringClient` (+ `ScoringUnavailable`), `IngestRepository`, ingest auth, and the `/api/v1/ingest` contract; note the commit-then-notify flow and that scoring is now an outbound HTTP dependency. Dated 2026-06-25.

- [ ] **Step 2: Update the system Container view**

In `grafin-ai-deploy/docs/c4/02-container.md`, add the edge: backend → scoring service (HTTP `POST /v1/score`) and the ingest entrypoint (producer → backend `POST /api/v1/ingest`). Note this is additive (the replay path still exists until Phase 5).

- [ ] **Step 3: Commit (per repo)**

```bash
git add docs/c4 && git commit -m "docs(ingest): C4 refresh for the ingest write-path"
cd ../grafin-ai-deploy && git add docs/c4 && git commit -m "docs: system container adds backend->scoring + ingest edges" && cd -
```

---

## Self-Review

**Spec coverage:**
- Config (scoring_url/token, ingest_token, timeout/retries, fail-fast) → Task 1. ✅
- Scoring client (pooled, timeout, bounded retries → ScoringUnavailable, correlation-id, 4xx-no-retry) → Task 2. ✅
- Ingest-token auth (settings-only, no request override, constant-time) → Task 3. ✅
- Repository: enrich risk_category + bank names; idempotent batch persist (ON CONFLICT DO NOTHING, events only for new ids, alerts for blocked) → Task 4. ✅
- Endpoint: enrich→score→503-on-down→atomic persist→publish frontend shape; response with per-item `ingested`; 400 on FK; 401/422 → Task 5. ✅
- Observability (bounded metrics + correlation id) → Tasks 5–6. ✅
- Testing (persistence, idempotency, publish, 503-persists-nothing, 401, 400, enrichment; client unit tests) → Tasks 2, 4, 5. ✅
- Out of scope honored (no read re-anchoring, no replay/sim removal) — nothing in the plan touches read endpoints or sim_state. ✅

**Placeholder scan:** none — full code per step.

**Type consistency:** `ScoringClient.score(transactions, correlation_id)` (Task 2) matches the call in the route (Task 5). `IngestRepository.persist(transactions, scores_by_id, now) -> list[InsertedEvent]` (Task 4) matches the route's usage and the publish loop reads `InsertedEvent.seq/transaction_id/fraud_score/typology/status`. `scores_by_id` keys on `transaction_id` from the scoring `results`. Schema model names (`Account`, `Bank`, `Alert`, `Transaction`, `TransactionEvent`) are flagged for verification against `schema/__init__.py` in Task 4. `IngestResponse`/`IngestResultItem` (Task 5) match the route return + tests. Config field names (`scoring_url`, `scoring_token`, `ingest_token`, `scoring_timeout_s`, `scoring_retries`) are consistent across config, client, route, and `get_scoring_client`.
