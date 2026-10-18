# grafin-ai-ingest — Reference Seed Job (Phase 3)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Repo:** `grafin-ai-ingest` (NEW)
**Anchor spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`
**Depends on:** the backend-owned DB schema (banks / entities / accounts) — by contract, via a
committed DDL snapshot. No code dependency on any other service.

Phase 3 of the platform re-architecture. Extract the pipeline's reference-data ETL into a
standalone **one-shot seed job**: load `banks`, `entities` (+ deterministic geo province), and
`accounts` from the HI-Small accounts CSV into the backend-owned Postgres, idempotently. Run once
before the sim streams (Phase 4) so `/ingest`'s FK references (`from_account`/`to_account` →
`accounts`; `from_bank_id`/`to_bank_id` → `banks`) resolve.

This is a **behavior-identical port** of `grafin_ai_pipeline.etl.reference.load_reference` +
`grafin_ai_pipeline.geo` + the reference-relevant half of `grafin_ai_pipeline.etl.validate`,
repackaged as its own repo at the same engineering bar as `grafin-ai-scoring` (Phase 1).

## What this is (and is not)

- **A one-shot CLI job**, not a service. No FastAPI, no HTTP server, no Redis, no long-running
  process. It connects, loads, validates, logs a summary, and exits.
- **Reference/master data only** — `banks`, `entities`, `accounts`. It does **not** load
  `transactions` (those arrive via the backend `/ingest` path now), and does **not** touch
  `sim_state` (removed in Phase 5), `transaction_events`, or `alerts`.
- **No code dependency on the backend.** It shares the DB *by contract*: raw asyncpg SQL against
  the reference tables, with a committed DDL snapshot (`tests/schema.sql`) for its own tests —
  the same pattern established in the 2026-06-23 pipeline decouple.

## Configuration — `grafin_ai_ingest/config.py`

pydantic-settings, `env_prefix="GRAFIN_"`, `.env` supported (dev ergonomics), `extra="ignore"`:

- `database_url: str` — **required** (no default) so a misconfigured run fails fast at startup.
  Accepts either a bare `postgresql://` DSN or SQLAlchemy's `postgresql+asyncpg://` form; the DSN
  is normalized for asyncpg (`db.asyncpg_dsn`, ported verbatim).
- `data_dir: str = "../grafin-ai-data/HI-Small"` — directory holding `HI-Small_accounts.csv`.
- `batch_size: int = 5000` — accounts insert batch size (matches the pipeline's `_BATCH`).

## Data access — `grafin_ai_ingest/db.py`

Ported verbatim from `grafin_ai_pipeline/db.py`:
- `asyncpg_dsn(url)` — strips SQLAlchemy's `+asyncpg` so `asyncpg.connect` gets a bare DSN.
- `connect(url)` — `await asyncpg.connect(asyncpg_dsn(url))`.

Single connection, closed in a `finally`. No pool — a one-shot job does not need one.

## Geo enrichment — `grafin_ai_ingest/geo.py`

Ported **verbatim** from `grafin_ai_pipeline/geo.py` (must stay byte-for-byte behavior-identical so
the seeded province of any entity id is unchanged): the 15 Indonesian `PROVINCES`, the `_WEIGHTS`
distribution, `_BUCKET`, and `province_for_entity(entity_id)` — a stable, seeded assignment from
`sha256(entity_id)`. Deterministic: same entity id → same province, forever.

## Seed load — `grafin_ai_ingest/seed/reference.py`

Ported from `load_reference`, behavior-identical, with the CSV column contract preserved
(`Bank ID`, `Bank Name`, `Entity ID`, `Entity Name`, `Account Number`, `risk_score`,
`risk_category`). `_num(value)` parses `risk_score` to `Decimal` (None on bad/empty), and an empty
`risk_category` becomes `NULL`.

```
async def load_reference(conn, accounts_csv, *, batch_size=5000) -> LoadCounts
```
1. Stream the CSV once with `csv.DictReader`, de-duplicating banks by `Bank ID` and entities by
   `Entity ID` (`dict.setdefault`), and collecting account tuples.
2. `INSERT INTO banks (id, name) ... ON CONFLICT (id) DO NOTHING` (executemany).
3. `INSERT INTO entities (id, name, province) ... ON CONFLICT (id) DO NOTHING`, with
   `province = province_for_entity(eid)`.
4. `INSERT INTO accounts (id, bank_id, entity_id, risk_score, risk_category) ...
   ON CONFLICT (id) DO NOTHING`, in `batch_size` batches.

Insert order (banks/entities before accounts) guarantees the account FKs resolve.

### Conflict strategy — **insert-only (DO NOTHING)** on every table
Faithful to the existing pipeline behavior and the anchor spec's "idempotent via `ON CONFLICT`".
Re-running the seed fills gaps but never mutates rows that already exist; corrected reference data
in the CSV is applied only after the target rows are removed. Chosen for lowest risk and exact
parity with the proven loader (upsert-on-correction is explicitly out of scope — see below).

### Idempotency
Running the job N times produces the same table state as running it once: `DO NOTHING` means no
duplicate rows and no row churn. Safe to invoke at every deploy-init.

`load_reference` returns a small `LoadCounts` (banks, entities, accounts) result — the distinct
counts parsed from the CSV — used for the summary log (not a correctness gate; validation reads
the DB).

## Validation — `grafin_ai_ingest/seed/validate.py`

A **reference-only** port of the pipeline's `validate` (the transaction/orphan checks do not apply
— this job loads no transactions):

```
async def validate(conn) -> ValidationReport
```
Reads back from the DB:
- `banks`, `entities`, `accounts` row counts.
- `entities_without_province` — `SELECT count(*) FROM entities WHERE province IS NULL` (should be 0;
  the geo enrichment always assigns one).
- `orphan_account_refs` — accounts whose `bank_id`/`entity_id` don't resolve (should be 0; a
  belt-and-suspenders check that the insert order held).

`ok = banks > 0 and entities > 0 and accounts > 0 and entities_without_province == 0 and
orphan_account_refs == 0`.

## Orchestration + CLI — `grafin_ai_ingest/seed/run.py`

The console entrypoint (`grafin-ingest` script + `python -m grafin_ai_ingest.seed.run`):

```
async def run_seed(data_dir, database_url, *, batch_size) -> ValidationReport
def main() -> None
```
- `configure_logging()` (structlog JSON), then structured events: `seed.start` (file),
  `seed.reference.done` (counts), `seed.validate` (**report), `seed.done` (duration_s).
- Resolves `accounts_csv = data_dir/HI-Small_accounts.csv`; if it is missing, log a clear
  `seed.error` and `raise SystemExit(2)` (actionable: "accounts CSV not found at <path>").
- On a **missing-schema** error (asyncpg `UndefinedTableError` — migrations not yet run), catch it
  and `raise SystemExit(3)` with a clear message ("reference tables not found — run the backend
  Alembic migrations first"), rather than a raw traceback.
- Fail-fast: if `not report.ok`, `raise SystemExit(1)` with the report — same contract as the old
  ETL runner. A clean run exits 0.
- Wraps the load in a timer for the `duration_s` field.

## Observability — `grafin_ai_ingest/observability.py`

Structured logging only — **no Prometheus/metrics server.** A one-shot job that exits does not fit
a scrape model, and the platform has no Pushgateway; the correct observability surface for a batch
job is a structured, parseable run record. `configure_logging(level="INFO")` mirrors the scoring
service's structlog config (contextvars merge, log level, ISO timestamp, exc_info, JSON renderer).
The `seed.done` summary carries `banks`, `entities`, `accounts`, `entities_without_province`, and
`duration_s` so a deploy-init log line fully captures the outcome. (If job-level metrics are ever
needed, a Pushgateway push slots in behind this same summary — noted, not built. Aligns with the
`observability-monitoring` plugin's batch-job guidance.)

## Testing

`pytest` + `pytest-asyncio` (auto mode) against a testcontainers Postgres, schema built from the
committed DDL snapshot (`tests/schema.sql`) — **no backend import**. Redis fixtures are dropped
(not needed). Ported/adapted from the pipeline's reference tests:

- `test_geo.py` — `province_for_entity` is deterministic and stable for known ids; every province
  returned is in `PROVINCES` (guards the verbatim port).
- `test_reference.py` — loads `banks`/`entities`/`accounts` from `data/accounts_sample.csv`;
  asserts counts (2 banks, 3 entities, 3 accounts), a specific account's `bank_id`/`entity_id`/
  `risk_score`/`risk_category`, and that a known entity's `province` equals
  `province_for_entity(id)`. **Idempotency:** load twice → counts unchanged. **DO NOTHING proof:**
  pre-insert an account row with a *different* `risk_category`, run the load, assert the pre-existing
  value is retained (the seed did not overwrite it).
- `test_validate.py` — after a good load, `report.ok is True` and counts are right; an empty DB
  gives `ok is False` (banks == 0).
- `test_run.py` — `run_seed` against the container: exit-0 semantics (returns an `ok` report),
  emits the summary; a missing CSV path → `SystemExit(2)`; a good run is idempotent when invoked
  twice.

`tests/schema.sql` is the committed DDL snapshot of the reference tables (`banks`, `entities`
+ `ix_entities_province`, `accounts` + its indexes and the two FKs). It carries **only** what this
job touches (the reference tables and the FK targets), not the full backend schema — the job never
references `transactions`/`events`/`alerts`/`users`/`sim_state`. `tests/data/accounts_sample.csv`
is copied from the pipeline's fixture.

## Engineering standards (plugin conformance)

Same bar as Phase 1 (`backend-development`, `python-development`, `observability-monitoring`):
- **python-development:** uv-managed, `ruff` (line-length 100), `mypy --strict` with the pydantic
  plugin, Python 3.12, `pytest-asyncio`. `LoadCounts` / `ValidationReport` are typed
  (dataclass/`NamedTuple`) — no bare dicts across boundaries.
- **observability-monitoring:** structured JSON logs with a complete, parseable run summary;
  clear, actionable failure logs; documented exit codes. (Batch job → logs, not a metrics server.)
- **backend-development / data:** idempotent, atomic-per-statement loads; fail-fast config and
  validation; a clear error taxonomy (exit 1 validation / 2 missing input / 3 missing schema);
  streaming batched inserts (bounded memory for the accounts set).
- **Reliability:** deterministic geo enrichment (seeded hash); connection always closed in
  `finally`; re-runnable safely (idempotent).

## Packaging / ops

- `pyproject.toml` (hatchling, uv) mirroring `grafin-ai-scoring`: deps `asyncpg`, `structlog`,
  `pydantic-settings`; dev `pytest`, `pytest-asyncio`, `testcontainers[postgres]`, `ruff`, `mypy`.
  `[project.scripts] grafin-ingest = "grafin_ai_ingest.seed.run:main"`.
- `Dockerfile` — a slim image running `uv run --no-sync grafin-ingest` (job container: runs to
  completion and exits; used by the deploy-init step / compose in Phase 6).
- `.github/workflows/ci.yml` — ruff + mypy + pytest (mirrors scoring's CI).
- `README.md`, `.env.example`, `.gitignore`, `.dockerignore`, `.python-version`.
- `docs/c4/{03-component,04-code}.md` — component + code-level docs for the seed job.

## Build order

Subagent-driven, `python-pro` implementer + `code-reviewer` and `security-auditor` review gates.
The security surface is small (a DB writer with no network input, no auth), but the reviews still
confirm the DDL-snapshot contract, SQL correctness/idempotency, and the config fail-fast.

## Out of scope (YAGNI / later phases)

- **Transactions load** — gone; transactions enter via the backend `/ingest` path (Phase 2).
- **Upsert-on-correction** (`ON CONFLICT DO UPDATE`) — not now; the seed is insert-only. Correcting
  live reference data is a future concern (truncate + reseed, or a dedicated correction path).
- **A metrics server / Pushgateway** — not for a one-shot job (see Observability).
- **Owning the schema / migrations** — the backend remains the single source of truth; this job
  keeps a committed DDL snapshot for tests only and assumes the schema is already migrated.
- **A real external reference feed** — the seed reads the committed HI-Small accounts CSV; a live
  feed is out of scope for the demo path.
