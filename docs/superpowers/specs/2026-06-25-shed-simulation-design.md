# Shed Simulation Machinery; Retire Pipeline (Phase 5)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Scope:** cross-repo — `garda-ai-backend`, `garda-ai-dashboard-web`, and the deletion of
`garda-ai-pipeline`.
**Anchor spec:** `garda-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`
**Depends on:** Phases 2 (backend `/ingest`) and 4 (`garda-ai-sim`) — the sim→ingest path is what
replaces the removed replay/sim-clock path.

Phase 5 removes the accelerated-simulation machinery now that transactions enter through the sim →
`/ingest` → scoring → persist → publish path. It re-anchors the read side from the DB-persisted
simulation clock (`sim_state.sim_now`) to **wall-clock `now()`**, deletes the `/sim` control
surface, the `sim_state` table, and the frontend Simulation page, and **deletes the retired
`garda-ai-pipeline` repo**.

This is the first re-architecture phase that **modifies the two established repos** rather than
adding new ones, so it is mostly *deletion + re-wiring* and leans hard on the review gates.

## Why the re-anchor is small

Every read aggregate currently depends on one shared FastAPI dependency, `get_sim_now`
(`api/deps.py`), which looks up `sim_state.sim_now` (404 if uninitialized) and each view filters
`surfaced_at <= sim_now`. Because the `/ingest` path already stamps `surfaced_at = now()` at
persist time (Phase 2), re-anchoring is a **dependency swap**: `get_sim_now` → `get_now` returning
`datetime.now(UTC)`. The view repositories are unchanged — they still take a `datetime` and filter
`surfaced_at <= it`; that bound is just wall-clock now instead of the sim clock. No query rewrites.

## What must NOT change (guard against over-deletion)

`model_accuracy_simulated` / the **"Simulated (Phase 1)"** banner is about the **label-replay
scorer** (honesty that accuracy is not a trained-model metric), NOT the sim clock. It stays in
`api/system.py` (`SystemHealthResponse.model_accuracy_simulated`) and in the frontend
(`App.tsx`). Do not remove it.

---

## ① Backend shed — `garda-ai-backend`

### Re-anchor (the core change)
- `api/deps.py`: replace `get_sim_now` / `SimNowDep` with:
  ```python
  from datetime import UTC, datetime
  def get_now() -> datetime:
      return datetime.now(UTC)
  NowDep = Annotated[datetime, Depends(get_now)]
  ```
  Remove the `SimRepository` import and the "404 if sim not initialized" behavior (reads are always
  available now).
- Swap `SimNowDep` → `NowDep` (and the param name `sim_now` → `now`) in the 6 view routers that use
  it: `api/geo.py`, `api/metrics.py` (×3 handlers), `api/transactions.py`, `api/users_view.py`
  (×2), `api/analytics.py`. The repository call sites keep passing a `datetime`; only the source
  changes.

### Delete
- `api/sim.py` — the `/api/v1/sim/state` (GET) + `/api/v1/sim/control` (POST) endpoints.
- `repositories/sim.py` — `SimRepository`.
- `schema/sim.py` — the `SimState` ORM model; remove its export from `schema/__init__.py`.
- `api/view_schemas.py` — `SimStateResponse` and `SimControlRequest`.
- `seed.py` — `ensure_sim_state` and its call in the seed entrypoint (stop seeding `sim_state`).
- `main.py` — remove the `/sim` router registration/import.

### `system/health`
- Drop the `SimRepository().get_sim_now()` lookup. `events_surfaced` becomes a plain total count:
  `SELECT count(*) FROM transaction_events` (with `surfaced_at = now()` on every event, the old
  `surfaced_at <= sim_now` filter now includes everything). Keep `db_ok`, `redis_ok`,
  `model_accuracy_simulated=True`. `SystemHealthResponse` shape is otherwise unchanged.

### WS live-event message contract
- `api/ingest.py`: stop publishing the redundant `sim_now` field in the Redis
  `garda:events:live` message. The message already carries `surfaced_at` (the real timestamp the
  frontend uses); `sim_now` was kept only for shape-compat in Phase 2. This is the one place the
  shed changes the live-event contract — the frontend change (②) matches it.

### Migration
- New Alembic revision (down-revision = current head `c105fac3e957`): `op.drop_table("sim_state")`
  in `upgrade`; `downgrade` recreates it (id PK singleton, `sim_now timestamptz NOT NULL`,
  `speed numeric NOT NULL default 1.0`, `running bool NOT NULL default false`, the
  `sim_state_singleton` check `id = 1`). `tests/test_migrations.py` must stay green (round-trip
  upgrade/downgrade).

### Tests (the main churn)
- **Delete** `tests/test_sim_endpoints.py`.
- `tests/conftest.py`: remove the `SimState` seed (`session.add(SimState(...))`) and its import.
  The event-surfacing helper inserts events at fixed 2025 timestamps; since those are all `<= now()`,
  after the re-anchor **every seeded event is visible**. View tests that previously relied on
  `SIM_NOW` windowing a *subset* must instead seed exactly the events they assert (drop the
  windowing assumption), and use `datetime.now(UTC)`-relative expectations where needed.
- `tests/test_schema.py`: drop `SimState` assertions.
- `tests/test_seed.py`: drop the `ensure_sim_state` assertions.
- `tests/test_ingest_api.py`: the publish assertion must **no longer expect `sim_now`** in the
  message; assert the remaining fields (incl. `surfaced_at`).
- Re-run the affected view tests (metrics/analytics/geo/users_view/transactions) and fix expectations
  that assumed sim-clock windowing. Keep everything else green.

### Engineering standards
Follows the backend's existing bar (`backend-development`, `python-development`,
`observability-monitoring`). No new deps. The change is additive-safe at runtime for the *new* path
(ingest already drives events); it *removes* the old path. Review gates: `code-reviewer` +
`security-auditor` (deletion of an auth-adjacent control surface + a schema migration warrant a pass).

---

## ② Frontend shed — `garda-ai-dashboard-web`

**Author note:** this repo's local git author is currently the BRI corp email — **set it to
`Thariq Iskandar Zulkarnain M P <thariqiskandar9@gmail.com>` before the first commit** (as done in
the other repos).

### Delete
- `components/SimulationControl.tsx` and `components/SimulationControl.test.tsx`.
- `api/queries.ts`: `useSimState` and `useSimControl` hooks; drop the `SimState` import.
- `api/types.ts`: the `SimState` interface; and remove `sim_now` from the live-event message
  interface (the field at `types.ts:105`) to match the backend WS change.
- `components/Sidebar.tsx`: the admin-only `simItem` nav entry and its insertion into
  `navigationItems`.
- `App.tsx`: the `SimulationControl` import and the `currentView === '/simulation'` route branch.
- `api/useLiveTransactions.*`: stop reading/carrying `sim_now`; update
  `useLiveTransactions.test.tsx` fixtures that include `sim_now`.

### Keep
- The `model_accuracy_simulated` → "Simulated (Phase 1)" banner in `App.tsx`.
- `Header.test.tsx` already asserts the header has **no** simulation element — it stays green
  (the sim indicator was moved out earlier and is now fully gone).

### Tests / build
- `vitest` suite green after removals (the deleted components' tests go with them; the live-hook and
  any snapshot tests updated for the dropped `sim_now`). `npm run build` compiles (no dangling
  imports/types). No new sim UI is introduced.

### Engineering standards
Frontend removals only; no new dependencies. Review gate: `code-reviewer` (a `frontend-developer`
implementer + a quality pass — the risk is dangling imports / broken types / stale tests, not
security).

---

## ③ Retire `garda-ai-pipeline` — DELETE

Its code has been fully redistributed (scoring → `garda-ai-scoring`, reference ETL →
`garda-ai-ingest`, replay/producer → `garda-ai-sim`) and **nothing outside the pipeline imports
`garda_ai_pipeline`** (verified). Per the decision, **delete the directory** (`rm -rf
garda-ai-pipeline`). This removes its on-disk git history — **unrecoverable** unless pushed
elsewhere; done as the **last** Phase 5 step, after the backend + frontend sheds are complete and
green, and reported explicitly.

Its `docker-compose` services (`etl`, `replay`) are removed from `garda-ai-deploy` in **Phase 6**
(the compose rework); Phase 5 only deletes the repo. (If any Phase-5 change happens to touch the
compose file, leave the pipeline services alone — that is Phase 6's job.)

---

## Sequencing & decomposition

One spec (this file), executed as **two plans then a deletion**, in order:
1. **Backend shed plan** (`garda-ai-backend/docs/superpowers/plans/2026-06-25-shed-simulation-backend.md`)
   — it owns the contracts (WS message, `/sim` removal, `system/health`), so it goes first.
2. **Frontend shed plan** (`garda-ai-dashboard-web/docs/superpowers/plans/2026-06-25-shed-simulation-frontend.md`)
   — adapts to the backend contract changes.
3. **Pipeline deletion** — a single verified step after both are green.

Each plan is subagent-driven with review gates, per the established flow.

## Contract-change summary (for consumers)

- **Removed endpoints:** `GET /api/v1/sim/state`, `POST /api/v1/sim/control` (both gone → 404).
- **WS `garda:events:live` message:** loses the `sim_now` field; `surfaced_at` remains the
  authoritative event time.
- **`GET /api/v1/system/health`:** same response shape; `events_surfaced` is now a total count and
  the endpoint no longer 404s on an uninitialized sim (there is no sim).
- **View endpoints:** unchanged shapes; they now reflect wall-clock-current data (no sim windowing).
- **DB:** `sim_state` table dropped (Alembic migration).

## Out of scope (later / YAGNI)

- **Compose / deploy rework** (removing pipeline `etl`/`replay` services, adding the new service
  set, infra IaC) — **Phase 6**.
- **Re-introducing any pause/speed control** — the sim owns pacing locally now (Phase 4); the
  platform has no server-side clock to control.
- **Data retention / time-window tuning** on the read side — the views keep their existing windows,
  now anchored to real time; tuning them is a separate concern.
