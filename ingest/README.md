# grafin-ai-ingest

One-shot reference/master-data seed for the Grafin AML platform. Loads `banks`,
`entities` (+ deterministic geo province), and `accounts` from the HI-Small
accounts CSV into the backend-owned Postgres, idempotently (`ON CONFLICT DO NOTHING`).
Run once before the simulation streams transactions, so `/ingest` FK references resolve.

## Run

```bash
uv sync
GRAFIN_DATABASE_URL=postgresql://grafin:grafin@localhost:5432/grafin \
GRAFIN_DATA_DIR=../grafin-ai-data/HI-Small \
  uv run grafin-ingest
```

Exit codes: `0` ok · `1` validation failed · `2` accounts CSV not found · `3` reference
tables not found (run the backend Alembic migrations first).

## Test

```bash
uv run pytest -q
```
