# grafin-ai-sim

Local-only simulation producer for the Grafin AML platform. Streams the HI-Small
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
cd ../grafin-ai-data/HI-Small
head -1 HI-Small_Trans_part1.csv > HI-Small_Trans_sorted.csv
tail -q -n +2 HI-Small_Trans_part1.csv HI-Small_Trans_part2.csv | LC_ALL=C sort >> HI-Small_Trans_sorted.csv
```

Or run `make dataset-sort` from `grafin-ai-deploy`. Takes ~20s and produces ~433 MB
(5,078,345 rows spanning 2025-09-01 00:00 → 2025-09-18 16:18, ≈3.3 txn/s at `speed=1`).
Point `GRAFIN_TRANS_FILES` at the raw parts if you deliberately want the unsorted source.

## Run

```bash
uv sync
GRAFIN_INGEST_TOKEN=<the backend GRAFIN_INGEST_TOKEN> \
GRAFIN_INGEST_URL=http://localhost:8000/api/v1/ingest \
GRAFIN_DATA_DIR=../grafin-ai-data/HI-Small \
  uv run grafin-sim
```

Useful knobs: `GRAFIN_SPEED` (pacing multiplier), `GRAFIN_BATCH_SIZE` (≤1000),
`GRAFIN_MAX_GAP_S` (cap on any single wait; `0` disables pacing entirely),
`GRAFIN_SKIP` (advance past the first N rows without sending them),
`GRAFIN_LIMIT` (stop after N sent), `GRAFIN_DRY_RUN=true` (build+log batches, don't POST).
Ctrl-C stops gracefully.

## Starting mid-dataset, and resuming

`GRAFIN_SKIP` advances past rows without sending them. Ordinals keep counting from 1, so
`transaction_id` stays the row's true CSV position — which is what makes both of these work:

**Pre-populate then go live.** Load a block of history unpaced, then stream onward from where
it stopped, so the two line up instead of overlapping:

```bash
# history: rows 1,869,371..2,076,752 (all of 2025-09-03), as fast as the backend accepts
GRAFIN_SKIP=1869370 GRAFIN_LIMIT=207382 GRAFIN_MAX_GAP_S=0 GRAFIN_BATCH_SIZE=1000 uv run grafin-sim

# live: continue from 2025-09-04 at 1 dataset-hour per wall-minute
GRAFIN_SKIP=2076752 GRAFIN_SPEED=60 GRAFIN_BATCH_SIZE=100 uv run grafin-sim
```

**Resume after stopping.** The database already knows where you stopped, because
`transaction_id` is the CSV ordinal:

```sql
SELECT max(transaction_id) FROM transactions;   -- use as the next GRAFIN_SKIP
```

Re-sending rows is safe either way (the backend dedups by `transaction_id`), but each one
still costs a scoring call — so skipping is much faster than replaying from the start.

Exit codes: `0` ok / interrupted · `1` backend rejected or unreachable · `2` Trans CSV not found.

## Test

```bash
uv run pytest -q
```
