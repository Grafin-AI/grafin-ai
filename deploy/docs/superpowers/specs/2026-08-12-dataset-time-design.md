# Dataset Time + Data Clock — Design

**Date:** 2026-08-12
**Status:** Approved (design)
**Scope:** Make the dashboard's timeline the *dataset's* timeline instead of wall-clock "today".

---

## Problem

The dashboard shows today's date (`2026-08-12T02:00:00`) on every chart and stat card. That is the Phase 4 streaming model ② ("now-stamped, real cadence") working as designed: the sim reads each row's CSV timestamp, uses it **only to pace** sending, then stamps the event with the wall clock ([`reader.py:10`](../../../grafin-ai-sim/grafin_ai_sim/reader.py), [`producer.py:73`](../../../grafin-ai-sim/grafin_ai_sim/producer.py)). Separately, every read view buckets and filters on `transaction_events.surfaced_at` (ingestion time, also wall clock) — e.g. `date_trunc(trunc, surfaced_at)` in `repositories/metrics.py:39`, which is literally the chart's X axis.

The user wants the platform to present the dataset's real timeline. The HI-Small dataset spans **2025/09/01 00:20 → 2025/09/10 23:37** (10 days, IDR/Indonesian banks).

## Goal

`event_time` (business time, straight from the CSV) drives every chart, window, and label. "Now" becomes a **data clock** derived from the data, so time windows stay populated as the replay advances.

**Non-goals:** changing the sim's pacing behaviour (unchanged); changing auth/session expiry (must stay wall-clock); adding a toggle to switch between time models (YAGNI — one model, chosen deliberately).

---

## Two clocks, kept distinct

| Column | Table | Meaning | After this change |
|---|---|---|---|
| `event_time` | `transactions` (+ denormalized onto `transaction_events`) | when the transaction **happened** (from the CSV) | drives all views, charts, windows |
| `surfaced_at` | `transaction_events` | when the backend **saw** it (wall clock) | retained for audit + detection lag |

Keeping both preserves a genuinely useful AML signal — **detection lag** (`surfaced_at - event_time`) — which collapsing the two would destroy forever.

## Approach: denormalize `event_time` onto `transaction_events`

Chosen over (a) joining `transactions` into every aggregate — adds a join to each of 6 aggregate queries — and (b) collapsing `surfaced_at = event_time` — cheapest but makes `surfaced_at` a lie.

`event_time` is immutable once written, so denormalization carries no update-anomaly risk. It keeps every read query a **single-table, indexed scan**, exactly as today; the queries change by one column name.

---

## Changes

### 1. Backend — schema

New Alembic migration, `down_revision = "b2f1a9c4d7e0"` (current head, `drop_sim_state`):

1. `ADD COLUMN transaction_events.event_time TIMESTAMPTZ NULL`
2. Backfill: `UPDATE transaction_events te SET event_time = t.event_time FROM transactions t WHERE te.transaction_id = t.id`
3. `ALTER COLUMN ... SET NOT NULL`
4. `CREATE INDEX ix_transaction_events_event_time ON transaction_events (event_time)`

Downgrade reverses (drop index, drop column). The three-step add/backfill/not-null keeps the migration safe on a populated database even though our local runs start clean.

`schema/transactions.py`: `TransactionEvent` gains
`event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)`.

### 2. Backend — ingest writes it

`repositories/ingest.py` `event_values` (~line 74) gains `"event_time": <the transaction's event_time>` alongside the existing `"surfaced_at": now`. The value comes from the client-supplied `event_time` already present on each request item, keyed by transaction id (the same mapping style as `scores_by_id`).

`api/ingest.py` keeps `now = datetime.now(UTC)` for `surfaced_at` — unchanged.

### 3. Backend — the data clock

`api/deps.py`: replace `get_now()` with

```python
async def get_data_now(session: SessionDep) -> datetime:
    """'Now' on the dataset's timeline: the latest event_time we have ingested.
    Falls back to wall-clock now() on an empty database so a fresh install
    behaves sanely (empty dashboard rather than an error)."""
    result = await session.scalar(select(func.max(TransactionEvent.event_time)))
    return result or datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_data_now)]
```

`NowDep` keeps its name, so the six view modules' signatures are untouched. Backed by the new index, `max()` is a fast backward index scan; **no caching initially** (add a short-TTL Redis cache only if it ever shows up in profiling — YAGNI).

FastAPI caches dependencies per request, so `get_data_now` and the endpoint body share one session; the clock read and the view queries see one consistent snapshot.

### 4. Backend — read views switch column

In these repositories, every `surfaced_at` used as a **window bound or bucket key** becomes `event_time`:

- `repositories/metrics.py` — `<= now` / `>= lower` filters, `date_trunc(...)` bucket (the chart X axis), `extract('dow'|'hour', ...)` (heatmap)
- `repositories/analytics.py` — two `<= now` filters
- `repositories/geo.py` — `<= now` filter
- `repositories/users_view.py` — `<= now` filter
- `repositories/transactions.py` — `<= now` filter; **keeps returning `surfaced_at` in the payload and additionally returns `event_time`**

### 5. Backend — live feed carries event_time

`api/ingest.py`'s Redis publish payload and `repositories/transactions.py`'s live-backfill rows both include `event_time` (ISO string) in addition to `surfaced_at`, so the WS push and the `after_seq=` backfill agree field-for-field.

### 6. Frontend

- `src/api/types.ts`: `LiveEvent` gains `event_time: string` (keep `surfaced_at`).
- `src/api/useLiveTransactions.ts:49`: carry `event_time` through the mapping.
- `src/components/TransactionMonitor.tsx:218`: render `formatTime(item.event_time)` instead of `surfaced_at`.
- Update the affected fixtures in `types.test.ts` / `useLiveTransactions.test.tsx`.

### 7. Sim

`producer.py` currently computes one `stamp = self._now().isoformat()` per **batch** (line 73) and applies it to every row (line 75). Change the payload build to stamp **per row** from the CSV:

```python
payloads: list[dict[str, object]] = [
    {**t.fields, "transaction_id": t.ordinal, "event_time": t.csv_ts.isoformat()} for t in batch
]
```

This makes `self._now` dead — line 73 was its only use. **Remove the `now` constructor parameter and `self._now`**, and drop the now-unused `datetime`/`UTC` imports if nothing else needs them; update any test that passes `now=`. (The `sleep` and `new_cid` injectable seams stay — they are still used.)

`reader.py`'s `SimTxn.csv_ts` comment ("used ONLY for pacing, never sent") is corrected — it is now the sent value too.

**Pacing logic is unchanged** — sleeps are still derived from CSV gaps.

### 8. Untouched (deliberately)

Auth: `security/tokens.py` uses its own `datetime.now(UTC)` for `iat`/`exp`. It must **never** use the data clock, or tokens would be dated 2025 and login would break. Verified already isolated — no change, but this is an explicit invariant.

---

## Testing

- **Backend:** `tests/conftest.py:113` seeds `TransactionEvent` — add `event_time` (fixtures already use Sept-2025 dates, so no date rework). Rename `deps.get_now` → `deps.get_data_now` in the 5 test files that override it. Update `test_schema.py` / `test_ingest_api.py` for the new column. A new test asserts the data clock returns `max(event_time)`, and another that it falls back to wall-clock on an empty table.
- **Frontend:** update the two fixture files; the live-feed test asserts `event_time` is rendered.
- **Sim:** a test asserts the payload's `event_time` equals the row's CSV timestamp (not the injected `now`), and that pacing is unaffected.
- **Migration:** the existing `test_migrations.py` revision-chain walk must stay green with the new head.

## Operational note

Existing rows are stamped `2026-08-12`. They would out-rank every Sept-2025 row and pin the data clock to today, leaving the dashboard empty. **This change requires `docker compose down -v` and a fresh replay.** The user has acknowledged this.

## Commits

Authored **Thariq Iskandar Zulkarnain M P `<thariqiskandar9@gmail.com>`** with trailer **`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`**, committed locally to each repo; no remote push.
