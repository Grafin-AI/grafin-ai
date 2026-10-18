# grafin-ai-ingest — C4 Component

**Container:** `grafin-ai-ingest` — a one-shot CLI **job** (not a long-running service). Runs at
deploy-init / on demand, seeds reference data, exits.

## Components

- **CLI / Orchestrator** (`seed/run.py`) — the `grafin-ingest` entrypoint. Configures logging,
  reads settings, opens one asyncpg connection, drives load → validate, emits the structured
  summary, maps outcomes to exit codes (0/1/2/3), closes the connection.
- **Reference Loader** (`seed/reference.py`) — parses the accounts CSV, de-duplicates banks and
  entities, enriches entities with a province, and inserts all three tables
  `ON CONFLICT DO NOTHING` (idempotent). Returns `LoadCounts`.
- **Validator** (`seed/validate.py`) — reads row counts and referential-integrity spot checks
  back from the DB; returns a `ValidationReport` with an `ok` gate.
- **Geo** (`geo.py`) — deterministic, seeded province assignment (`sha256(entity_id)`).
- **Config** (`config.py`) — `GRAFIN_`-prefixed settings; `database_url` required (fail-fast).
- **DB** (`db.py`) — asyncpg DSN normalization + connect.
- **Observability** (`observability.py`) — structlog JSON logging.

## Relationships & boundaries

- Writes **only** the reference tables (`banks`, `entities`, `accounts`) of the backend-owned
  Postgres. Shares the DB **by contract** — a committed DDL snapshot (`tests/schema.sql`) for
  tests; **no import of any other service**.
- No inbound network surface, no auth, no Redis. Reads a local CSV; writes Postgres; exits.
- Ordering: must run **before** the sim streams (Phase 4) so `/ingest` FK references resolve;
  and **after** the backend Alembic migrations create the schema.
