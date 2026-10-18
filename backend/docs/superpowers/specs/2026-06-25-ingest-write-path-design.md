# Backend Ingest Write-Path — Design (Phase 2)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Repo:** `grafin-ai-backend`
**Anchor spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`
**Depends on:** `grafin-ai-scoring` (Phase 1, its `POST /v1/score` contract).

Phase 2 of the platform re-architecture. Add an **ingest write-path** to the backend: receive
transaction batches, score them via the scoring service, persist `transactions` +
`transaction_events` (+ `alerts`), and publish to Redis for the WS relay. This ports the replay
worker's persistence/publish logic into a synchronous HTTP endpoint and moves scoring to a
network call.

**Purely additive.** The existing replay worker, `sim_state`, `/sim/*`, the WS relay, and all
read endpoints are UNCHANGED — they are removed/re-anchored in Phase 5. During Phase 2 the old
replay path still drives the live dashboard; the new `/ingest` is exercised via tests + the WS
relay, and becomes the dashboard's sole source at Phase 5.

## Configuration (add to `grafin_ai_backend/config.py`)

- `scoring_url: str` — base URL of the scoring service (e.g. `http://scoring:8000`). Required.
- `scoring_token: str` — bearer token presented to the scoring service. Required.
- `ingest_token: str` — bearer token the producer must present to `/ingest`. Required.
- `scoring_timeout_s: float = 5.0`, `scoring_retries: int = 2` — client resilience knobs.

Fail-fast: these are required (no default), so a misconfigured deploy crashes at startup rather
than silently exposing/breaking ingest. (Consistent with the existing `jwt_secret` fail-closed
validator; keep dev ergonomics by allowing them via `.env`.)

## Scoring client — `grafin_ai_backend/services/scoring_client.py`

An httpx `AsyncClient` wrapper:
- `async def score(items: list[ScoreItem]) -> list[ScoreResult]` → `POST {scoring_url}/v1/score`
  with `Authorization: Bearer {scoring_token}`, body `{"transactions": [...]}`.
- Timeout `scoring_timeout_s`; retry up to `scoring_retries` times with exponential backoff on
  connect/timeout/5xx (python-resilience). A 4xx (e.g. contract mismatch) is NOT retried.
- On exhaustion raises `ScoringUnavailable` (custom exception) — the endpoint maps it to **503**.
- Reuses a single `AsyncClient` (created at app startup / lifespan, closed on shutdown) —
  connection pooling, no per-request client.
- Propagates the request's correlation id as `X-Correlation-ID` so the ingest→score chain traces
  end-to-end (pairs with the scoring service's correlation-id middleware).

## Ingest endpoint — `POST /api/v1/ingest`

Auth: bearer `ingest_token` (a dependency mirroring the scoring service's `_verify`/`require_token`
split — pure verifier + FastAPI dependency reading the token only from settings; **never** a
request-controllable override — see the Phase-1 auth-bypass lesson). User JWTs do NOT grant ingest.

### Request
```json
{
  "transactions": [
    {
      "transaction_id": 40217,
      "from_bank_id": "011",
      "from_account": "1000000001",
      "to_bank_id": "014",
      "to_account": "1000000002",
      "amount_paid": "15000.00",
      "payment_currency": "IDR",
      "amount_received": "15000.00",
      "receiving_currency": "IDR",
      "payment_format": "ACH",
      "is_laundering": true,
      "event_time": "2026-06-25T09:00:00Z"
    }
  ]
}
```
- `transaction_id` is **producer-provided and stable** (idempotency + scoring key).
- `event_time` is stored as-is (the producer/sim decides real vs historical time).
- Bounded batch: `max_length=1000` (reject oversize → 422), matching the scoring service's cap.

### Response (200)
```json
{ "results": [ { "transaction_id": 40217, "seq": 9931, "status": "blocked", "ingested": true } ] }
```
- `ingested: false` (and `seq: null`) for transactions whose id already existed (idempotent
  replay — no duplicate row/event created).

### Handler flow (commit-then-notify)
1. **Enrich** — one batch query: `SELECT id, risk_category FROM accounts WHERE id = ANY($from_accounts)`;
   map `from_risk_category` per transaction (null if the account has none).
2. **Score** — call the scoring client with `{transaction_id, from_account, to_account,
   amount_paid→amount, payment_format, is_laundering, event_time, from_risk_category}`.
   **If the client raises `ScoringUnavailable` → return 503; nothing is persisted.**
3. **Persist (atomic)** — in one DB transaction:
   - `INSERT INTO transactions (id, event_time, from_bank_id, from_account, to_bank_id,
     to_account, amount_paid, payment_currency, amount_received, receiving_currency,
     payment_format, is_laundering) SELECT * FROM unnest(...) ON CONFLICT (id) DO NOTHING
     RETURNING id` → the set of **newly-inserted** ids.
   - For the newly-inserted ids only: `INSERT INTO transaction_events (transaction_id,
     surfaced_at, fraud_score, typology, status) SELECT * FROM unnest(...) RETURNING seq,
     transaction_id, fraud_score, typology, status` (`surfaced_at = now()`).
   - `INSERT INTO alerts (event_seq, severity, typology, created_at)` for events with
     `status = 'blocked'` (severity `high`, `created_at = now()`) — same rule as the replay worker.
4. **Publish (after commit)** — for each new event, publish to Redis `grafin:events:live` the
   **exact message shape the WS relay/frontend already consume**:
   `{seq, transaction_id, bank, type, amount, fraud_score, typology, status, surfaced_at, sim_now}`
   where `bank` = the from-bank name (join `banks`), `type` = `payment_format`, `amount` =
   `float(amount_paid)`, `surfaced_at` = `now().isoformat()`, `sim_now` = `surfaced_at` (kept for
   shape compatibility; becomes irrelevant once reads re-anchor in Phase 5).

### Idempotency
The whole endpoint is idempotent on `transaction_id`: a re-POSTed batch inserts no duplicate
transactions (ON CONFLICT), creates no duplicate events (events only for newly-inserted ids),
and publishes nothing for duplicates. Scoring may run again for duplicates (pure + cheap) but has
no persisted effect.

### Error semantics
- 200 — batch processed (per-item `ingested` true/false).
- 401 — missing/invalid ingest token.
- 422 — malformed body / oversize batch.
- 400 — a transaction references an unknown `from_bank_id`/`to_bank_id`/account (FK violation):
  return a clear "unknown reference" error (reference data must be seeded first, Phase 3). The
  batch is rejected atomically (nothing persisted).
- 503 — scoring service unavailable (after retries).

## Repository — `grafin_ai_backend/repositories/ingest.py`

Encapsulates the three batch statements above (asyncpg-style `unnest` inserts + `RETURNING`),
adapted from the proven `ReplayRepository.write_events_and_advance` pattern (minus the sim-clock
advance). The backend uses SQLAlchemy async elsewhere; this repository may use SQLAlchemy `text()`
with bound arrays or the existing async session — follow the backend's established data-access
pattern (do not introduce a second driver). Keep the insert of transactions + events + alerts in
one transaction (session.begin()).

## Observability

- Structured request log for `/ingest` (batch size, inserted count, duration) with correlation id.
- Metrics (bounded labels): reuse the backend's Prometheus registry; add
  `grafin_ingest_transactions_total{result}` (`inserted|duplicate`) and
  `grafin_ingest_scoring_latency_seconds` (histogram) — bounded, `prefix_name_unit`.
- Correlation id propagated to the scoring call (above).

## Testing

Against the backend's existing testcontainers (Postgres + Redis), with a **mocked scoring client**:
- Persistence: POST a batch → 200; `transactions` + `transaction_events` rows present; `alerts`
  row for a `blocked` result.
- Idempotency: re-POST the same batch → `ingested:false`, no duplicate events, no extra publish.
- Publish: a Redis subscriber on `grafin:events:live` receives one message per new event with the
  expected shape/fields.
- 503: scoring client raises `ScoringUnavailable` → 503, and **nothing persisted** (DB unchanged).
- 401: missing/wrong ingest token. 422: malformed / oversize batch. 400: unknown bank/account ref.
- Enrichment: `from_risk_category` is looked up and passed to the scoring client (assert the
  client received it).
Scoring-client unit tests (httpx mock / respx or monkeypatched transport): success maps response;
5xx/timeout retries then raises `ScoringUnavailable`; 4xx does not retry; bearer + correlation-id
headers are sent.

## Engineering standards (plugin conformance)

Follows `backend-development`, `python-development`, `observability-monitoring` (same bar as
Phase 1), plus:
- **Resilience** (python-resilience): scoring client timeout + bounded retries + backoff; a single
  pooled `AsyncClient`; a typed `ScoringUnavailable` boundary → 503.
- **Error handling** (python-error-handling): validation via pydantic (422); FK/reference errors
  mapped to 400 with a clear message; no swallowed exceptions; the persist step is atomic.
- **API design**: versioned `/api/v1/ingest`, correct status codes, consistent JSON error shape,
  OpenAPI docs; ingest auth reads the token ONLY from settings (no request-controllable override).
- **Security** (backend-security-coder): constant-time token compare; ingest separated from user
  auth; batch bound to cap resource use.

Build subagent-driven with `fastapi-pro`/`python-pro` implementers + `code-reviewer` and
`security-auditor` review gates (the write-path + new auth warrant a security pass).

## Out of scope (YAGNI / later phases)

- **Read-side re-anchoring** (`sim_now` → real-time / data high-water mark) — Phase 5. Phase 2
  does not change the read endpoints; ingested data is verified at the ingest→persist→publish→WS
  level, not via the aggregate views.
- Removing the replay worker / `sim_state` / `/sim/*` — Phase 5.
- The producer (`grafin-ai-sim`) — Phase 4; the reference seed (`grafin-ai-ingest`) — Phase 3.
- Account/bank **upsert on ingest** for unknown references (a real external feed) — future; Phase 2
  requires reference data pre-seeded and 400s on unknown refs.
- No message queue between producer and backend — direct HTTP batches (anchor decision).
