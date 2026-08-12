# garda-ai-sim

Local-only simulation producer for the Garda AML platform. Streams the HI-Small
transactions CSV as batches to the backend `POST /api/v1/ingest` (bearer ingest token),
pacing by the CSV's real inter-arrival gaps compressed by `speed` (capped by `max_gap_s`)
and sending each row's own CSV timestamp as `event_time`. Owns pacing/speed/start-stop
locally. **Never deployed.**

## Preparing the dataset (once)

The replay reads `HI-Small_Trans_sorted.csv`, which does **not** ship with the dataset —
generate it first. The raw `HI-Small_Trans_part1/part2.csv` files are grouped by account
rather than by time: ~48% of consecutive rows step *backwards*, by up to 3.5 days. That
breaks two things at once — the gap-based pacing (negative gaps clamp to zero, so the
replay runs flat out) and the backend's `max(event_time)` data clock (it leaps ahead of
the rows still streaming in, so "last 24h" views empty out mid-run).

The timestamp format `YYYY/MM/DD HH:MM` is zero-padded and leads each line, so a plain
lexicographic sort is chronological:

```bash
cd ../garda-ai-data/HI-Small
head -1 HI-Small_Trans_part1.csv > HI-Small_Trans_sorted.csv
tail -q -n +2 HI-Small_Trans_part1.csv HI-Small_Trans_part2.csv | LC_ALL=C sort >> HI-Small_Trans_sorted.csv
```

Or run `make dataset-sort` from `garda-ai-deploy`. Takes ~20s and produces ~433 MB
(5,078,345 rows spanning 2025-09-01 00:00 → 2025-09-18 16:18, ≈3.3 txn/s at `speed=1`).
Point `GARDA_TRANS_FILES` at the raw parts if you deliberately want the unsorted source.

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
