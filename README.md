# garda-ai-sim

Local-only simulation producer for the Garda AML platform. Streams the HI-Small
transactions CSV as batches to the backend `POST /api/v1/ingest` (bearer ingest token),
pacing by the CSV's real inter-arrival gaps compressed by `speed` (capped by `max_gap_s`)
and stamping `event_time = now`. Owns pacing/speed/start-stop locally. **Never deployed.**

## Run

```bash
uv sync
GARDA_INGEST_TOKEN=<the backend GARDA_INGEST_TOKEN> \
GARDA_INGEST_URL=http://localhost:8000/api/v1/ingest \
GARDA_DATA_DIR=../garda-ai-data/HI-Small \
  uv run garda-sim
```

Useful knobs: `GARDA_SPEED` (pacing multiplier), `GARDA_BATCH_SIZE` (≤1000),
`GARDA_MAX_GAP_S` (cap on any single wait), `GARDA_LIMIT` (stop after N), `GARDA_DRY_RUN=true`
(build+log batches, don't POST). Ctrl-C stops gracefully.

Exit codes: `0` ok / interrupted · `1` backend rejected or unreachable · `2` Trans CSV not found.

## Test

```bash
uv run pytest -q
```
