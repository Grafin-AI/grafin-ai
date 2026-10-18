# garda-ai-ingest

One-shot reference/master-data seed for the Garda AML platform. Loads `banks`,
`entities` (+ deterministic geo province), and `accounts` from the HI-Small
accounts CSV into the backend-owned Postgres, idempotently (`ON CONFLICT DO NOTHING`).
Run once before the simulation streams transactions, so `/ingest` FK references resolve.

## Run

```bash
uv sync
GARDA_DATABASE_URL=postgresql://garda:garda@localhost:5432/garda \
GARDA_DATA_DIR=../garda-ai-data/HI-Small \
  uv run garda-ingest
```

Exit codes: `0` ok · `1` validation failed · `2` accounts CSV not found · `3` reference
tables not found (run the backend Alembic migrations first).

## Test

```bash
uv run pytest -q
```
