# Garda AI — Backend API Design

**Date:** 2026-06-22
**Status:** Approved (brainstorming)
**Repo:** `garda-ai-backend`
**Anchor spec:** `garda-ai-deploy/docs/superpowers/specs/2026-06-22-system-architecture-design.md`

The backend is the API gateway. It owns the canonical database schema + migrations, serves every dashboard view via server-side aggregation, relays the live feed over WebSocket, and enforces auth/RBAC + PII masking. It does **not** score transactions (pipeline does) and never ships raw 5M-row result sets.

---

## 1. Stack

- **FastAPI** (async), Python 3.12, `uv` for deps.
- **SQLAlchemy 2.0** (async) + **asyncpg**; **Alembic** migrations.
- **Pydantic v2** for all request/response models → drives OpenAPI.
- **Redis** (`redis.asyncio`) for cache, rate-limit, refresh-token store, and WS pub/sub subscription.
- **prometheus-client**, **OpenTelemetry**, **structlog**.
- Layering (architecture-patterns): `api/` (routers) → `services/` (use cases) → `repositories/` (DB access) → `schema/` (shared DB models, extractable later). No business logic in routers; no SQL outside repositories.

## 2. Canonical database schema (owned here)

Migrations live in `garda-ai-backend/migrations` (Alembic) and **create the schema at init time** (an Alembic upgrade step run before ETL). Pipeline ETL assumes the tables exist and only loads data into them. Pipeline imports the model package `garda_ai_backend.schema` (or a generated DDL) so there is exactly one source of truth.

```
banks(
  id PK,                       -- bank id from CSV (e.g. 10, 3208)
  name text                    -- "Bank Rakyat Indonesia (BRI)"
)

entities(
  id PK,                       -- Entity ID (e.g. 80062E240)
  name text,                   -- Entity Name (masked at API layer)
  province text                -- synthetic seeded enrichment (Indonesian province)
)

accounts(
  id PK,                       -- Account Number (e.g. 80B779D80)
  bank_id FK -> banks,
  entity_id FK -> entities,
  risk_score numeric,          -- from accounts.csv
  risk_category text           -- Low | Medium | High
)

transactions(                  -- all ~5M rows, immutable historical truth
  id PK bigserial,
  event_time timestamptz,      -- parsed from Timestamp
  from_bank_id FK, from_account FK -> accounts,
  to_bank_id FK,   to_account FK -> accounts,
  amount_paid numeric, payment_currency text,
  amount_received numeric, receiving_currency text,
  payment_format text,         -- Reinvestment | Cheque | ACH | ...
  is_laundering boolean        -- ground-truth label
)

transaction_events(            -- scored, surfaced feed (written by replay worker)
  seq bigint GENERATED ALWAYS AS IDENTITY PK,   -- monotonic cursor
  transaction_id FK -> transactions,
  surfaced_at timestamptz,     -- = sim_now when emitted
  fraud_score numeric,         -- 0..1
  typology text NULL,          -- Fan-Out | Cycle | Smurfing | Gather-Scatter | Mule Account | Layering | ...
  status text                  -- approved | flagged | blocked
)

alerts(
  id PK, event_seq FK -> transaction_events,
  severity text, typology text, created_at timestamptz,
  acknowledged_by FK -> users NULL, acknowledged_at timestamptz NULL
)

users(
  id PK, email unique, password_hash text,   -- argon2id
  role text,                                  -- analyst | admin
  created_at timestamptz
)

sim_state( singleton row: sim_now timestamptz, speed numeric, running bool )
```

**Indexes:** `transactions(event_time)`, `transactions(from_account)`, `transactions(to_account)`, `transactions(is_laundering)`; `transaction_events(surfaced_at)`, `transaction_events(status)`, `transaction_events(typology)`, `transaction_events(transaction_id)`; `accounts(entity_id)`, `accounts(risk_category)`; `entities(province)`. Optional monthly time-partitioning on `transactions`.

## 3. Auth & RBAC

| Endpoint | Notes |
|---|---|
| `POST /api/v1/auth/login` | email+password → access JWT (15m) + refresh JWT (7d). Refresh stored in Redis (revocable). |
| `POST /api/v1/auth/refresh` | rotate refresh, issue new access. |
| `POST /api/v1/auth/logout` | revoke refresh in Redis. |
| `GET /api/v1/auth/me` | current user + role. |

- Argon2id hashing. Roles: `analyst` (read + acknowledge alerts), `admin` (+ unmasked PII, + replay controls).
- Dependency `require_role(...)` guards endpoints. Default deny.

## 4. View endpoints (server-side aggregation)

Aggregates run over `transaction_events` **surfaced so far** (`surfaced_at ≤ sim_now`, inherently true since the worker stamps `surfaced_at = sim_now` at emission) — so every view reflects the simulation's current state. Precision/recall joins those events back to `transactions.is_laundering`.

All responses are Pydantic models → typed OpenAPI. Aggregates are Redis-cached with short TTL keyed by `sim_now` bucket.

| View (frontend component) | Endpoint | Returns |
|---|---|---|
| Live Monitor | `GET /api/v1/transactions/live?after_seq=&limit=` | recent `transaction_events` joined to txn (id, bank, type, amount, fraud_score, typology, status, surfaced_at, `seq`). Resync source. |
| Transaction detail modal | `GET /api/v1/transactions/{id}` | full txn + event + derived analysis (recipient bank, channel, risk factors, typology explanation). |
| Metrics Overview | `GET /api/v1/metrics/overview` | total txns, flagged, blocked, total amount, fraud rate, deltas vs prior window. |
| Transaction Volume | `GET /api/v1/metrics/volume?range=24h\|weekly\|monthly\|yearly` | time-bucketed series of volume + flagged count. |
| Heatmap | `GET /api/v1/metrics/heatmap` | day-of-week × hour activity matrix (7×24). |
| Fraud Analytics | `GET /api/v1/analytics/fraud` | typology distribution `[{typology, total_amount, count}]` + detection metrics (precision/recall/F1 vs `is_laundering`). |
| Geographic Map | `GET /api/v1/geo/provinces` | `[{name, fraud_count, change_pct, risk_level}]` over seeded province enrichment. |
| User Risk Profiling (list) | `GET /api/v1/users/risk?risk=&q=&page=` | paginated entity profiles: id, masked name, entity type, risk_level, risk_score, total_txns, flagged_txns, total_amount, location, last_activity. |
| User profile detail modal | `GET /api/v1/users/{entity_id}/profile` | extended profile: KYC status, linked accounts, monthly activity series, risk history series, transaction pattern (weekday/weekend/night), risk factors. |
| Alerts Panel | `GET /api/v1/alerts?status=` · `POST /api/v1/alerts/{id}/ack` | active alerts; analyst can acknowledge. |
| System Health | `GET /api/v1/system/health` | API latency, replay throughput/lag, active WS connections, DB pool, model/accuracy (real metric or labeled "simulated" in Phase 1). |
| Sim clock | `GET /api/v1/sim/state` · `POST /api/v1/sim/control` *(admin)* | current `sim_now`, speed, running; start/pause/seek (admin). |

## 5. WebSocket relay

- `WS /api/v1/ws/live` — authenticated (JWT in connect). Backend subscribes to the Redis channel the worker publishes to and fans scored events out to connected clients.
- Message: `{ seq, transaction_id, bank, type, amount, fraud_score, typology, status, surfaced_at, sim_now }`.
- Client sends its `last_seq`; gaps are not backfilled over WS — the client backfills via `GET /transactions/live?after_seq=` (consistency contract §5 of anchor spec).
- Per-connection backpressure: bounded send queue; drop-to-latest with a "resync" hint if a slow client falls behind.

## 6. PII masking (server-side, never trust client)

- `entities.name` → `A****** S******`; payment/account ids partially masked. Applied in the service layer for `analyst`. `admin` may request unmasked via an explicit flag, logged for audit.

## 7. Performance

- Async DB pool sized to container; statement timeouts.
- Aggregation in SQL; Redis rollup cache (TTL ~ one sim-clock tick) keyed by endpoint + `sim_now` bucket + params; invalidated as clock advances.
- Cursor pagination on lists; never `OFFSET` deep scans.
- p95 < 100ms for aggregate endpoints (excluding cold cache).

## 8. Observability & ops

- `/metrics` (Prometheus), `/healthz`, `/readyz` (checks DB + Redis).
- structlog JSON with request id; OTel spans API→DB→Redis.
- OpenAPI served at `/openapi.json`; **frontend generates TS types from it** (contract sync).

## 9. Testing

- TDD (backend-development): unit (services with fake repos), integration (testcontainers Postgres + Redis), contract (OpenAPI schema snapshot), auth/RBAC + masking tests. pytest + httpx async client.

## 10. C4 documentation (deliverable)

After implementation, generate **C4 Component + Code** docs via the c4-architecture plugin (bottom-up against this repo's code) into `garda-ai-backend/docs/c4/`. System-wide Context + Container live in `garda-ai-deploy/docs/c4/`.

## 11. Out of scope here

- Scoring logic and replay loop → `garda-ai-pipeline`.
- Deployment manifests, Prometheus/Grafana provisioning → `garda-ai-deploy`.
