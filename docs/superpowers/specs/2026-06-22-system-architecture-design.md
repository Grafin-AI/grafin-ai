# Garda AI — System Architecture Design

**Date:** 2026-06-22
**Status:** Approved (brainstorming)
**Scope:** Cross-cutting anchor spec for the Garda AI real-time AML detection platform. Owns the system-wide contracts that the per-repo specs depend on.

Related specs:
- `garda-ai-backend/docs/superpowers/specs/2026-06-22-backend-api-design.md`
- `garda-ai-pipeline/docs/superpowers/specs/2026-06-22-pipeline-scoring-design.md`
- `garda-ai-dashboard-web/docs/superpowers/specs/2026-06-22-frontend-integration-design.md`

---

## 1. Purpose

Turn the static `garda-ai-dashboard-web` mock dashboard into a real-time Anti-Money-Laundering (AML) monitoring platform backed by a database and live transaction feed, optimized across architecture, performance, security, observability, and deployment.

Built for the OJK Hackathon 2025. Data source is the IBM AML **HI-Small** dataset, localized to Indonesian banks and IDR.

## 2. Repository topology (polyrepo)

| Repo | Function |
|---|---|
| `garda-ai-dashboard-web` *(exists)* | React 18 frontend — all dashboard views, API client, WS hook, auth UI |
| `garda-ai-backend` | FastAPI REST + WebSocket gateway, auth/RBAC, view aggregations. **Owns canonical DB schema + migrations.** |
| `garda-ai-pipeline` | ETL (CSV→Postgres), replay worker (accelerated clock), scoring engine module (`ScoringProvider`) |
| `garda-ai-deploy` | docker-compose, Terraform, Prometheus, Grafana, CI/CD glue, this spec |
| `garda-ai-data` *(exists)* | Dataset CSVs (kept out of code repos) |

**Boundary decisions:**
- **Backend owns the DB schema + migrations.** Pipeline consumes the same table definitions (a lightweight shared schema package published from backend, or a generated SQL DDL file pipeline reads). One source of truth for the data model.
- **API/WS contract is OpenAPI.** Backend publishes OpenAPI; frontend generates its TypeScript types from it. No shared package across the language boundary.
- **Scoring stays a module inside pipeline**, hidden behind the transport-agnostic `ScoringProvider` interface, so it can be extracted into a standalone model-serving API later with no change to the worker, DB, or dashboard.

## 3. Component architecture

```
   CSV (5M txns, 518K accounts)
        │  ETL (one-time, COPY)
        ▼
   ┌─────────────┐         ┌──────────────────────────────────────────┐
   │ PostgreSQL  │◀────────│ Replay Worker (pipeline)                  │
   │  + Redis    │  write  │ walk txns by timestamp on accel. clock → │
   └─────────────┘  +commit│ ScoringProvider.score() → COMMIT →       │
        ▲    │             │ publish to Redis pub/sub                 │
        │    │             └──────────────────────────────────────────┘
        │    │ read                          │ notify
   ┌────┴────▼─────────────────────┐         ▼
   │ FastAPI (backend)             │   Redis channel
   │ REST views · auth · WS relay  │◀────────┘
   └───────────────────────────────┘
        │ REST + WS
        ▼
   ┌───────────────────────────────┐
   │ React dashboard (frontend)    │
   │ TanStack Query + WS hook      │
   └───────────────────────────────┘
        │  metrics scraped by
        ▼
   Prometheus → Grafana
```

**Stack:** FastAPI (async, SQLAlchemy 2.0 + asyncpg), PostgreSQL, Redis (pub/sub + cache + rate-limit + refresh-token store), React 18 + TanStack Query, Prometheus + Grafana, Docker Compose + Terraform.

## 4. Simulation clock (the "real-time" model)

The dataset is historical (~1 month, ~5M transactions). "Real-time" is produced by **replaying** transactions in timestamp order on a configurable accelerated clock (e.g. 1 hour of data = 1 second wall-clock; speed is a config knob for demos).

- The replay worker's cursor position defines **`sim_now`** — the simulation's current instant.
- `sim_now` is published to Redis and exposed via the API so the frontend can display it.
- **All view queries filter `event_time ≤ sim_now`.** Every chart, metric, and aggregate reflects "what has happened so far in the simulation," giving a coherent live experience rather than dumping the whole month at once.

## 5. Data-consistency contract (dual-write resolution)

**Postgres is the single source of truth. The WebSocket is a notification layer, never a second data store.**

Rules (binding on backend + pipeline):
1. **Commit-then-notify.** The replay worker writes the scored event to Postgres and waits for the transaction to commit *before* publishing to Redis/WS. Anything that reaches the dashboard is already durable in the DB — never the reverse.
2. **Monotonic cursor.** Every surfaced event has a gap-free monotonically increasing `seq` (bigint identity). Clients track the highest `seq` seen.
3. **Resync on connect/reconnect.** On mount or socket reconnect, the frontend first fetches the authoritative recent window from REST (from the DB), *then* subscribes to WS and appends only events with `seq` greater than its cursor. Events missed during a disconnect are backfilled by the next REST fetch.

**Guarantee:** eventually consistent, never divergent. The dashboard may briefly lag the DB by a beat but can never show an event the DB lacks, nor permanently miss one the DB has.

**Deferred hardening (not built now):** transactional outbox + Postgres `LISTEN/NOTIFY` or logical replication for zero-lag strict delivery at high throughput. Documented as a future step; the commit-then-notify + resync approach is sufficient at hackathon scale.

## 6. Security posture (production-leaning)

Authoritative requirements; per-repo specs implement their slice.

- **AuthN:** JWT access tokens (short TTL) + refresh tokens (longer TTL, stored and revocable in Redis). Argon2id password hashing.
- **AuthZ:** RBAC with roles `analyst` and `admin`. Enforced server-side per endpoint.
- **PII masking:** entity names and payment IDs are masked server-side by default (`A****** S******`, as the UI already expects). Unmasked values gated behind `admin` role. Masking happens in the API layer, never trusting the client.
- **Input validation:** Pydantic v2 models on every request; reject-by-default.
- **Transport:** TLS terminated at nginx; HSTS + security headers (CSP, X-Content-Type-Options, etc.).
- **Rate limiting:** per-IP and per-user (Redis token bucket), stricter on auth endpoints.
- **CORS:** explicit allowlist of frontend origins.
- **Injection safety:** parameterized queries only (SQLAlchemy); no string-built SQL.
- **Secrets:** environment variables, Vault-ready; never committed. `.env.example` documents required vars.
- **Verification:** `security-scanning` SAST run + a STRIDE threat-model pass before the platform is declared done.

## 7. Performance targets & tactics

- **Ingest:** `COPY`-based bulk load of 5M rows; batched, in timestamp order.
- **Reads:** server-side aggregation only — never ship raw 5M rows to the client. Sub-100ms p95 for dashboard aggregate endpoints.
- **DB:** async pool (asyncpg); indexes on `(event_time)`, `(from_account)`, `(to_account)`, `(is_laundering)`, `(status)`, `(typology)`; optional time partitioning on the transactions table.
- **Cache:** Redis-cached aggregate rollups with short TTLs keyed by `sim_now` bucket; invalidated as the clock advances.
- **Live feed:** WS fan-out via Redis pub/sub; backpressure + max in-flight per client; the live monitor holds a bounded window.
- **Frontend:** TanStack Query caching + pagination; WS appends bounded.

## 8. Observability

- **Logs:** structured JSON (request id, user id, route, latency).
- **Metrics:** Prometheus — HTTP latency/error rates, WS connections, replay throughput & lag, scoring latency, DB pool stats. Exposed at `/metrics` on backend and pipeline.
- **Dashboards:** Grafana provisioned with platform dashboards (API health, replay progress, fraud-rate over sim time).
- **Tracing:** OpenTelemetry spans across API → DB → Redis.
- **Health:** `/healthz` (liveness) and `/readyz` (readiness incl. DB + Redis) on each service.

## 9. Deployment

- **Local/demo:** `docker-compose.yml` in `garda-ai-deploy` brings up the whole stack with one command — postgres, redis, backend, pipeline (ETL job + replay worker), frontend (nginx), prometheus, grafana.
- **Cloud path:** Terraform skeleton for managed Postgres + container hosting; not required for the demo but scaffolded.
- **CI/CD:** GitHub Actions per repo — lint, test, SAST, build image, push; deploy workflow in `garda-ai-deploy`.

## 10. Build sequence (cross-repo)

1. **backend → pipeline:** schema created via backend Alembic migration (init step); pipeline ETL then loads CSVs into the tables → data in Postgres.
2. **pipeline:** `ScoringProvider` + `LabelReplayScorer`.
3. **pipeline:** replay worker (commit→publish) + Redis.
4. **backend:** auth/RBAC + view endpoints + WS relay + OpenAPI.
5. **frontend:** API client, generated types, TanStack Query, WS hook, auth/login, wire all views.
6. **deploy:** docker-compose, Prometheus, Grafana, security pass, observability.
7. **deploy:** CI/CD + Terraform skeleton.
8. **pipeline (Phase 2):** swap `LabelReplayScorer` → `MLModelScorer` (in-process now, HTTP client to standalone model API later) when the trained model lands.

## 11. C4 architecture documentation

Documented at all four C4 levels, split by what each level needs:

- **Context + Container (system-wide, authored now):** live in `garda-ai-deploy/docs/c4/` (`01-context.md`, `02-container.md`). Derived from this approved design — the correct source for these architectural levels — with Mermaid C4 diagrams. Judge/onboarding facing.
- **Component + Code (per repo, post-implementation):** generated by the **c4-architecture plugin** (bottom-up: `c4-code` → `c4-component`) against each repo's real code, as the final deliverable of that repo's build. Output goes in each repo under `docs/c4/`. Regenerated when code changes materially.
- After all repos are implemented, an optional full c4-architecture pass reconciles the per-repo Component/Code docs back up into the system Container/Context docs.

## 12. Open items / honest gaps

- **Geo-enrichment is synthetic.** The dataset has no province field; each account is assigned an Indonesian province via a deterministic seeded hash (stable, realistic distribution). Documented as synthetic enrichment — not real geolocation.
- **Phase-1 scores are derived from the ground-truth label**, not a model. Real precision/recall numbers appear only after Phase 2. The UI must not over-claim "model accuracy" while in Phase 1 (system-health card values become real metrics or are labeled as simulated).
