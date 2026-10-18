# garda-ai-scoring — Service Design (Phase 1)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Repo:** `garda-ai-scoring` (new, standalone)
**Anchor spec:** `garda-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`

Phase 1 of the platform re-architecture. Extract the scoring engine from `garda-ai-pipeline`
into a standalone, stateless HTTP service. **Purely additive** — the pipeline keeps its own
copy of the scorer running until it is retired (Phase 5), so nothing else changes yet.

## Purpose

Give scoring its own independently deployable, horizontally scalable service with a stable HTTP
contract, so the backend (Phase 2) can call it during ingest and a future `MLModelScorer` can
drop in behind the same API. The service is a **pure function of its request** — no database, no
Redis, no state.

## Scope

- New repo `garda-ai-scoring`: uv project, FastAPI, mirroring `garda-ai-backend`'s conventions
  (pydantic-settings, structlog, Prometheus `/metrics`, `/healthz` + `/readyz`, ruff, pytest,
  own-context Dockerfile).
- A faithful, behavior-identical port of the pipeline's scoring package.
- A batch `POST /score` endpoint, bearer-token protected.

**Out of scope:** the backend-side scoring client + risk-category enrichment (Phase 2); the
`MLModelScorer` implementation (still a `scorer=ml` "not yet" guard); the deploy pipeline / IaC
(Phase 6 — this repo ships a Dockerfile + a lint/test CI only).

## Faithful port (behavior-identical)

Copy from `garda-ai-pipeline/garda_ai_pipeline/scoring/` into `garda_ai_scoring/scoring/`,
changing only the package name in imports. Determinism MUST be preserved exactly (same seed,
same key construction, same thresholds) so a given transaction scores identically to today.

- `types.py` — `TxnInput`, `ScoringContext`, `ScoringResult`, `ScoringProvider` (async
  `score(txn, ctx) -> ScoringResult` protocol). Verbatim.
  - `TxnInput`: `transaction_id: int`, `from_account: str`, `to_account: str`,
    `amount: Decimal`, `payment_format: str`, `is_laundering: bool`, `event_time: datetime`.
  - `ScoringContext`: `from_risk_category: str | None` (`Low | Medium | High`).
  - `ScoringResult`: `fraud_score: float` (0..1), `typology: str | None`, `status: str`.
- `deterministic.py` — `unit_hash`, `status_for` (block ≥ 0.8, flag ≥ 0.5, else approved),
  `typology_for`, `TYPOLOGIES` (the 7: Fan-Out, Cycle, Gather-Scatter, Smurfing, Mule Account,
  Layering, Trade-Based). Verbatim.
- `label_replay.py` — `LabelReplayScorer` (seeded FP/FN noise, risk-category bump, rounds to 4
  dp). Verbatim.
- `factory.py` — `get_scorer(name)` → `label_replay` returns `LabelReplayScorer`; `ml` raises
  "not yet implemented (Phase 2)"; unknown raises. Verbatim.

## HTTP API

FastAPI app (`garda_ai_scoring/api/`). Pydantic v2 request/response models. The API layer
(transport) is kept separate from `garda_ai_scoring/scoring/` (pure domain) — the domain has no
FastAPI/HTTP imports (separation of concerns; the scorer is testable without the web layer).

**Versioned from day one** (api-design-principles): the score endpoint is mounted under `/v1`
so a future breaking change can ship as `/v2` without disturbing callers. Ops endpoints
(`/healthz`, `/readyz`, `/metrics`) are unversioned by convention.

### `POST /v1/score`  (bearer `GARDA_SCORING_TOKEN`)

Request:
```json
{
  "transactions": [
    {
      "transaction_id": 123,
      "from_account": "0009abc",
      "to_account": "0011def",
      "amount": "15000.00",
      "payment_format": "ACH",
      "is_laundering": true,
      "event_time": "2026-06-25T09:00:00Z",
      "from_risk_category": "High"
    }
  ]
}
```
- `from_risk_category` is optional (nullable) — the backend enriches it from `accounts` during
  ingest (Phase 2); when absent, the scorer applies no risk bump.
- The request carries only what the scorer needs (`amount` is parsed as `Decimal`). Additional
  transaction fields can be added to the contract later without breaking callers.

Response:
```json
{ "results": [ { "transaction_id": 123, "fraud_score": 0.8123, "typology": "Smurfing", "status": "blocked" } ] }
```
- `status` ∈ `approved | flagged | blocked`. `typology` nullable (null when approved).
- Results are returned in the same order as the request and carry `transaction_id` so the caller
  can correlate. Determinism means results don't depend on batch composition.

Handler: for each item build `TxnInput` + `ScoringContext(from_risk_category=...)`, `await` the
configured provider's `score`, map `ScoringResult` → response item. Iterating the single-txn
provider preserves determinism (a batch scores identically to N single calls). Empty
`transactions` → empty `results` (200).

### Ops endpoints (unauthenticated)
- `GET /healthz` — liveness, static 200.
- `GET /readyz` — readiness; trivially ready (no external deps), returns 200.
- `GET /metrics` — Prometheus exposition (see Observability below).

### Auth & errors
- A dependency validates `Authorization: Bearer <GARDA_SCORING_TOKEN>`; missing/mismatched → 401.
- Applies to `/v1/score` only. `/healthz`, `/readyz`, `/metrics` are open (for probes/scrapers).
- If `GARDA_SCORING_TOKEN` is unset in config, the app fails fast at startup (no unauthenticated
  score endpoint by accident).
- **HTTP status semantics** (api-design-principles): 200 success; 401 auth failure; 422 request
  validation (FastAPI/pydantic default); 500 only for genuine server faults. Errors return a
  **consistent JSON shape** (`{"detail": ...}` — FastAPI's default, kept uniform via an exception
  handler). Auth/validation failures are expected client errors and are logged at INFO/WARNING,
  never ERROR (python-observability).

## Configuration (pydantic-settings, `GARDA_` env prefix)

- `scorer: str = "label_replay"` — selects the provider via `get_scorer`.
- `scoring_token: str` (required) — the bearer token.
- `seed: str = "garda"`, `fn_rate: float = 0.05`, `fp_rate: float = 0.04` — passed to
  `LabelReplayScorer`.
- `log_level: str = "INFO"`.
- Thresholds stay as the `deterministic.py` module constants (0.8 / 0.5) for Phase 1 — not
  runtime-configurable (YAGNI); revisit only if a real need appears.

## Observability (prometheus-configuration + python-observability)

**Structured logging.** structlog configured for JSON output with the standard processor chain
(`merge_contextvars`, `add_log_level`, ISO `TimeStamper`, `format_exc_info`, `JSONRenderer`),
level from config. One log line per request (method, path, status, duration_ms) plus the
correlation id; the pure scorer domain does not log (keeps observability out of business logic).

**Correlation IDs.** An ASGI middleware reads `X-Correlation-ID` (or `X-Request-ID`), else
generates a UUID, binds it into `structlog.contextvars`, and echoes it back on the response
header. This lets a `/ingest`→`/v1/score` call chain (Phase 2) be traced end-to-end by a single
id.

**Metrics — the RED signals, bounded cardinality** (metric names `prefix_name_unit`, base units):
- `garda_scoring_requests_total{endpoint,method,status_code}` — counter (traffic + errors).
- `garda_scoring_request_duration_seconds{endpoint,method}` — histogram (latency); buckets tuned
  for a fast scorer (e.g. 1ms…250ms), informed by the SLO below.
- `garda_scoring_transactions_scored_total{status}` — counter over the **bounded** result status
  (`approved|flagged|blocked`, 3 values) — useful signal on how much traffic is being flagged.

Labels are strictly bounded: only the path **template** (not raw paths), method, status_code, and
the 3-value result status. **Never** label by `transaction_id`, `from_account`, or any unbounded
value (avoids cardinality explosion). `/metrics` is served via `prometheus-client`.

**SLO (informs buckets, light for Phase 1).** Target: `/v1/score` p99 < ~50 ms for a nominal
batch. Recorded as a note here; full SLO/alerting rules land with the deploy/observability stack
(Phase 6), not in this service.

## Packaging & ops

- `pyproject.toml` (uv): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`,
  `structlog`, `prometheus-client` (match the backend's versions/pattern); dev: `pytest`,
  `pytest-asyncio`, `httpx` (for the async test client), `ruff`, and a type checker (`mypy` or
  `pyright`) — the domain is fully typed and type-checking runs in CI (python-type-safety).
- Own-context `Dockerfile` (two-phase `uv sync --frozen --no-dev` — same shape as the backend /
  the decoupled pipeline), tracked `.dockerignore`, `.env.example`.
- Console entry / `CMD`: `uvicorn garda_ai_scoring.api.app:app --host 0.0.0.0 --port 8000`.
- Minimal CI: a GitHub Actions workflow running `ruff check` + type-check + `pytest` on push/PR.
  The build-and-deploy pipeline is Phase 6.

## Engineering standards (plugin conformance)

The build follows the `backend-development`, `python-development`, and `observability-monitoring`
plugin practices. Concretely, for this service:

- **API design** (backend-development:api-design-principles): resource/versioned URL (`/v1/score`),
  correct HTTP status codes (200/401/422/500), consistent JSON error shape, stateless, OpenAPI
  auto-docs (tags + response models + `operation_id`). Rate limiting is out of scope for an
  internal token-gated service (handled at the ingress/backend if ever needed).
- **Clean boundaries** (backend-development:architecture-patterns, python-design-patterns):
  transport (`api/`) is separate from domain (`scoring/`); the domain is a pure, side-effect-free
  function set (no I/O, no logging), so it is trivially unit-testable and the ML swap is isolated.
- **Python** (python-development): uv project + locked deps (uv-package-manager); ruff
  format/lint (python-code-style); full type hints + CI type-check (python-type-safety);
  pydantic-settings with `GARDA_` prefix and fail-fast validation (python-configuration);
  validation-first error handling with pydantic, no swallowed exceptions (python-error-handling);
  async endpoints, and if the scorer ever becomes CPU-heavy it moves to a threadpool executor to
  avoid blocking the event loop (async-python-patterns — noted, not needed for the sha256 scorer);
  pytest + fixtures + parametrized determinism cases (python-testing-patterns).
- **Observability** (observability-monitoring + python-observability): structured JSON logs,
  correlation-id middleware, RED metrics with bounded label cardinality and `prefix_name_unit`
  naming, observability covered by tests (see Observability + Testing sections above).

**Build execution:** implemented subagent-driven with `python-development:python-pro` /
`python-development:python-development-fastapi-pro` implementers (which apply the skills above),
plus review gates by `superpowers:code-reviewer` and an
`observability-monitoring:observability-monitoring-observability-engineer` pass to verify the
logging/metrics/correlation-id instrumentation meets the standards.

## Testing

- **Scorer unit tests** — port the pipeline's scorer tests: determinism (same input → same
  output), laundering→high-score / non-laundering→low-score distributions within the seeded
  noise, FP/FN behavior at the configured rates, risk-category bump (High/Medium), `status_for`
  thresholds, `typology_for` range, factory selection + the `ml`/unknown errors.
- **Determinism-parity lock** — at least one test asserting a fixed transaction yields an exact
  known `fraud_score`/`status`/`typology`, so the port can't silently drift from the pipeline's
  behavior.
- **API tests** (httpx against the app) — `/v1/score` batch happy path (order + `transaction_id`
  correlation), `from_risk_category` present vs absent changes the score as expected, empty batch
  → empty results, 401 without/with-wrong token, 422 on a malformed body, `/healthz` + `/readyz`
  200, `/metrics` exposes Prometheus text.
- **Observability tests** — assert the request metric increments and `/metrics` exposes the RED
  series after a scored request, and that a supplied `X-Correlation-ID` is echoed back on the
  response (python-observability: "test your observability").
- Green `pytest`, clean `ruff check`, and clean type-check (`mypy`/`pyright`) are the acceptance
  bar.

## C4 documentation (deliverable)

After implementation, generate C4 Component + Code docs for this repo via the c4-architecture
plugin into `garda-ai-scoring/docs/c4/` (consistent with the other repos). The system-level
Context/Container in `garda-ai-deploy` is updated when Phase 2 wires the backend to this service.
