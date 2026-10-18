# Platform Re-architecture (v2) — Service Decomposition & Independent Deployability

**Date:** 2026-06-25
**Status:** Approved (brainstorming) — ANCHOR spec
**Supersedes:** the service topology + schema-ownership decisions in
`2026-06-22-system-architecture-design.md` (that spec's auth, masking, consistency, and
observability decisions still stand except where noted here).
**Repos affected:** all (`grafin-ai-backend`, `grafin-ai-dashboard-web`, `grafin-ai-deploy`, plus
three new repos), and the retirement of `grafin-ai-pipeline`.

## Purpose

Two goals drive this reshape:

1. **Independent deployability.** Deployment currently funnels through the single
   `grafin-ai-deploy` repo. Every service should build and deploy on its own; only *shared
   platform infra* is provisioned centrally.
2. **Cleaner service boundaries.** `grafin-ai-pipeline` is a grab-bag (ETL + scoring + replay
   worker). Scoring becomes its own service; the simulation becomes a local-only tool (it is a
   demo/dev data source, not a production platform component); reference-data seeding becomes a
   one-shot job. `grafin-ai-pipeline` is retired.

The through-line: transactions now enter the platform through a **backend ingest path** (not a
5M-row bulk load), the backend calls a **stateless scoring service**, and a **local simulation
producer** is what feeds transactions during a demo.

## Target architecture

### Deployed services

**`grafin-ai-backend`** — write + read core. Gains the ingest role; sheds simulation.
- `POST /ingest` — accepts a **batch** of transactions (from the sim or a real feed),
  authenticated by a machine **ingest token** (distinct from user JWTs).
- For the batch: calls the scoring service over HTTP, then persists `transactions` +
  `transaction_events` (+ `alerts` when blocked), and publishes to Redis `grafin:events:live`.
  This is the old replay-worker write logic, moved into the ingest handler.
- Unchanged: read/serve view endpoints, auth/RBAC, PII masking, WS relay, and ownership of the
  schema + Alembic migrations (still the single source of truth).
- **Removed:** `sim_state` table, `/sim/*` state+control endpoints, the accelerated-clock concept.

**`grafin-ai-scoring`** *(new)* — stateless scorer.
- `POST /score` — a batch of transactions → `[{fraud_score, typology, status}]`.
- `ScoringProvider` protocol: `LabelReplayScorer` now (derives the score from the
  `is_laundering` field that arrives with each transaction), `MLModelScorer` later — same
  contract, selected by a `scorer` config (`label` | `ml`).
- No DB, no Redis. Protected by a scoring token and/or private networking. Horizontally scalable
  (pure function of its input).

**`grafin-ai-dashboard-web`** — frontend.
- Remove the admin **Simulation page**, its Sidebar item, the sim-clock indicator, and the
  `useSimState` / `useSimControl` hooks.
- Everything else stays: live monitor (WS + REST resync), all view wiring, auth, role-gating.

### Tooling (not deployed as services)

**`grafin-ai-ingest`** *(new)* — one-shot reference/master-data seed.
- Loads `banks`, `entities` (+ seeded geo province), `accounts` (risk_score/risk_category),
  idempotent via `ON CONFLICT`. Streaming asyncpg load from the dataset CSVs.
- Connects to the backend-owned DB via asyncpg (raw SQL). Carries a **committed DDL snapshot**
  of the reference tables for its own tests (same pattern established in the 2026-06-23 pipeline
  decouple). No code dependency on the backend.
- Run before the sim streams (so FKs resolve) — at deploy init or on demand.

**`grafin-ai-sim`** *(new)* — local-only simulation producer.
- Reads the HI-Small labeled CSV, assigns `event_time` at a configurable/accelerated rate, and
  streams **batches** to the backend's `/ingest` using the ingest token.
- **Owns the clock, speed, and play/pause locally** (CLI flags / config). This is where the old
  replay controls live now.
- Never deployed. Points at a local *or* a deployed backend via base-URL config.

### Infra

**`grafin-ai-deploy`** — slims to:
- Shared-infra IaC (network, managed Postgres + Redis, DNS/TLS, container registry / cluster) —
  provisioned once. Target platform (AWS ECS Fargate vs GCP Cloud Run) decided in Phase 6.
- A local-dev `docker-compose` (backend + scoring + frontend + postgres + redis, with the ingest
  seed run once and the sim runnable locally).
- It is **no longer the deploy mechanism** — each service repo owns its Dockerfile + CI/CD and
  deploys itself.

**Retired:** `grafin-ai-pipeline` — code moves into `grafin-ai-scoring` + `grafin-ai-ingest` +
`grafin-ai-sim`.

## Data flow (deployed)

```
[grafin-ai-sim  (LOCAL)]  reads HI-Small CSV, paces at sim rate
        │  POST /ingest  (batch, ingest-token)
        ▼
   [backend] ──POST /score (batch)──▶ [scoring svc]  (stateless)
        │  ◀──── [{fraud_score, typology, status}] ────┘
        │  persist transactions + transaction_events (+ alerts)
        │  publish  grafin:events:live
        ▼
   [postgres]        [redis] ──▶ [backend WS relay] ──▶ [dashboard]
        ▲                                                    │
        └──────────────── REST read/serve ◀──────────────────┘
```

Transactions enter through **ingest**, so the DB grows with the stream instead of holding a
pre-loaded 5M rows — smaller footprint, friendlier to cheap managed Postgres. Reference data is
seeded first so FK references (`from_account`/`to_account` → `accounts`, banks) resolve.
(HI-Small was verified earlier to have 0 orphan txn accounts/banks, so a seeded reference set
covers the streamed transactions.)

## Contracts & boundaries

Consistent with the 2026-06-23 principle — **shared by contract, not by code; no service imports
another** (only `grafin-ai-deploy` references the others, for infra/compose):

- **Scoring API** (backend → scoring) and **Ingest API** (producer → backend) are HTTP/OpenAPI
  contracts. Types are duplicated by contract or generated — no shared code package.
- **Redis channel** `grafin:events:live` and the **DB schema** remain shared by contract (backend
  owns the schema/migrations; ingest keeps a committed DDL snapshot for its tests).
- **Auth:** user JWTs for the dashboard (unchanged); a separate machine **ingest token**
  (`GRAFIN_INGEST_TOKEN`) for the write path; scoring reached via a **scoring token**
  (`GRAFIN_SCORING_TOKEN`) and/or private networking.

### Scoring API (sketch — finalized in Phase 1's spec)
- `POST /score` → request `{ "transactions": [ {id, from_*, to_*, amount_*, payment_format,
  is_laundering, ...} ] }`; response `{ "results": [ {id, fraud_score, typology, status} ] }`.
- Stateless: the response is a pure function of the request. `status` ∈ (e.g.) `clear` |
  `flagged` | `blocked`; `typology` nullable.

### Ingest API (sketch — finalized in Phase 2's spec)
- `POST /ingest` (ingest-token) → a batch of transactions; backend scores + persists + publishes;
  returns per-item accepted/rejected with the assigned `seq`/id. Idempotent on the transaction
  `id` (upsert / `ON CONFLICT DO NOTHING`) so producer retries don't double-insert; Phase 2's
  spec finalizes the exact conflict handling.

## What is removed / changed in existing repos

- **backend:** drop `sim_state` (Alembic migration), `/sim/*` endpoints, sim-clock config; add
  `/ingest`, a scoring HTTP client, and the score→persist→publish path; add ingest-token auth.
  The transactions **bulk loader** concept is gone (transactions arrive via ingest).
- **frontend:** remove Simulation page, Sidebar item, sim-clock indicator, `useSimState` /
  `useSimControl`.
- **pipeline:** retired; ETL → ingest, scoring → scoring, replay/producer → sim.
- **deploy:** compose reworked to the new service set; infra IaC added; per-service CI/CD moves
  into each service repo.

## Testing strategy (per phase)

- **scoring:** unit tests for each `ScoringProvider` + `/score` contract tests. No DB.
- **backend:** `/ingest` handler tests with a mocked scoring client (persistence + publish +
  idempotency + ingest-token auth); WS unchanged; delete sim tests.
- **ingest:** seed idempotency tests against a committed DDL snapshot (asyncpg + testcontainers,
  as in the pipeline decouple).
- **sim:** producer tests (reads CSV → posts batches to a mock ingest; clock/rate logic).
- **frontend:** remove sim-page tests; keep the rest.

## Build order (each phase is independently shippable; the platform keeps working between phases)

1. **`grafin-ai-scoring`** — extract `ScoringProvider` into a standalone `/score` service
   (additive, safe). *Own spec + plan.*
2. **Backend ingest** — add `/ingest` + scoring client + score→persist→publish path. Until the
   sim is repointed, the existing replay worker can still run in parallel. *Own spec + plan.*
3. **`grafin-ai-ingest`** — extract the reference-seed ETL. *Plan (spec if needed).*
4. **`grafin-ai-sim`** — extract the producer, repointed to `POST /ingest`. *Plan (spec if needed).*
5. **Shed simulation** — remove `sim_state`/`/sim` from backend + the Simulation page from
   frontend; retire `grafin-ai-pipeline`. *Own plan.*
6. **Deploy split** — slim `grafin-ai-deploy` to infra + compose; per-service Dockerfiles/CI;
   choose AWS vs GCP and generate IaC via the cloud-infrastructure plugins. *Own spec + plan.*

Each phase gets brainstormed→spec'd→planned→implemented in order (subagent-driven), the same flow
used for the 2026-06-23 decouple. This anchor spec is the reference they all point back to.

## Out of scope (YAGNI)

- No shared "contracts" package or monorepo (reintroduces coupling).
- No real external transaction feed / account-upsert-on-ingest yet — ingest assumes reference
  data is seeded (demo path). A real feed with unknown accounts is a future concern.
- No message queue between producer and backend — direct HTTP `/ingest` batches are sufficient at
  demo scale; a queue can slot in later behind the same ingest contract.
- MLModelScorer implementation itself remains Phase-2-of-the-product (arrives via the `scorer=ml`
  switch once the model is trained); this reshape only makes room for it.
