# Dataset Time + Data Clock — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard present the dataset's timeline — `event_time` (from the CSV) drives every chart, window and label, with "now" derived from the data instead of the wall clock.

**Architecture:** `event_time` is denormalized onto `transaction_events` (indexed) so every read query stays a single-table indexed scan. `surfaced_at` is retained as real ingestion time (preserving detection lag). A new `get_data_now()` dependency returns `max(event_time)`, falling back to wall-clock on an empty DB. The sim sends each row's CSV timestamp.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres, pytest, React/TypeScript.

**Spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-08-12-dataset-time-design.md`

**Repo root:** `/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories/`

**Commit identity (every commit):** author `Thariq Iskandar Zulkarnain M P <thariqiskandar9@gmail.com>`, trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Commit locally to `main`; do **not** push.

**Task order matters:** Task 1 (schema + fixtures) must precede Task 4 (views), because the new column is NOT NULL and fixtures must populate it before queries depend on it.

**Backend test baseline:** 98 tests currently pass (`cd grafin-ai-backend && uv run pytest -q`). Run this first and record the number; it must not regress.

---

## Task 1: Backend — add `event_time` to `transaction_events`

**Files:**
- Modify: `grafin-ai-backend/grafin_ai_backend/schema/transactions.py`
- Create: `grafin-ai-backend/migrations/versions/d3c7e1f5a204_add_event_time_to_events.py`
- Modify: `grafin-ai-backend/tests/conftest.py`
- Modify: `grafin-ai-backend/tests/test_schema.py`

- [ ] **Step 1: Add the column to the model**

In `schema/transactions.py`, in class `TransactionEvent`, add `event_time` directly after `surfaced_at`:

```python
    surfaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Business time of the transaction (denormalized from transactions.event_time so the
    # read views stay single-table). surfaced_at stays = ingestion time, so
    # (surfaced_at - event_time) remains a usable detection-lag signal.
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
```

- [ ] **Step 2: Write the migration**

Create `migrations/versions/d3c7e1f5a204_add_event_time_to_events.py`:

```python
"""add event_time to transaction_events

Revision ID: d3c7e1f5a204
Revises: b2f1a9c4d7e0
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3c7e1f5a204"
down_revision: Union[str, Sequence[str], None] = "b2f1a9c4d7e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable, backfill from the parent transaction, then enforce NOT NULL so the
    # migration is safe on a populated database.
    op.add_column(
        "transaction_events",
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE transaction_events te "
        "SET event_time = t.event_time "
        "FROM transactions t "
        "WHERE te.transaction_id = t.id"
    )
    op.alter_column("transaction_events", "event_time", nullable=False)
    op.create_index(
        "ix_transaction_events_event_time", "transaction_events", ["event_time"]
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_events_event_time", table_name="transaction_events")
    op.drop_column("transaction_events", "event_time")
```

- [ ] **Step 3: Align the test fixture so both tables agree**

In `tests/conftest.py`, the fixture currently seeds transaction `event_time` at hours 10–13 (`9 + i`) while events use `surfaced_at` hours 9, 10, 11, 11 — and `SIM_NOW` is 12:00. Denormalizing without fixing this would push txn 4 (13:00) outside the window and silently change results.

Change `_txn` to take an explicit hour, and make `_ev` set both timestamps to that same hour.

Replace the `_txn` helper and its `add_all` block with:

```python
    def _txn(i, frm, to, amount, launder, hour):
        return Transaction(
            id=i, event_time=datetime(2025, 9, 1, hour, tzinfo=UTC),
            from_bank_id="10", from_account=frm, to_bank_id="20", to_account=to,
            amount_paid=Decimal(amount), payment_currency="IDR",
            amount_received=Decimal(amount), receiving_currency="IDR",
            payment_format="ACH", is_laundering=launder,
        )
    session.add_all([
        _txn(1, "ACC1", "ACC2", "15000000", True, 9),
        _txn(2, "ACC2", "ACC1", "250000", False, 10),
        _txn(3, "ACC1", "ACC2", "5000000", True, 11),
        _txn(4, "ACC2", "ACC1", "150000", False, 11),
    ])
```

Replace the `_ev` helper with (same hour drives both columns):

```python
    def _ev(seq, tid, score, typ, status, hour):
        ts = datetime(2025, 9, 1, hour, tzinfo=UTC)
        return TransactionEvent(
            seq=seq, transaction_id=tid, surfaced_at=ts, event_time=ts,
            fraud_score=Decimal(score), typology=typ, status=status,
        )
```

Leave the `_ev(...)` call list unchanged — hours 9, 10, 11, 11 now match their transactions, and all four remain `<= SIM_NOW` (12:00).

- [ ] **Step 4: Update the schema test**

In `tests/test_schema.py`, the assertion listing `transaction_events` columns must include `event_time`. Find the set literal for that table and add `"event_time"` to it. (The file already asserts a `transactions` column set containing `event_time`; make sure you edit the **transaction_events** assertion, not that one.)

- [ ] **Step 5: Run the backend tests**

Run: `cd grafin-ai-backend && uv run pytest -q`
Expected: same pass count as the baseline (98), no failures. Views still read `surfaced_at` at this point, and because fixture hours now align, results are unchanged.

- [ ] **Step 6: Commit**

```bash
cd grafin-ai-backend
git add grafin_ai_backend/schema/transactions.py migrations/versions/d3c7e1f5a204_add_event_time_to_events.py tests/conftest.py tests/test_schema.py
git commit -m "feat: denormalize event_time onto transaction_events

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Backend — ingest populates `event_time`

**Files:**
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/ingest.py`
- Modify: `grafin-ai-backend/tests/test_ingest_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ingest_api.py` (near the existing `test_ingest_publish_matches_persisted_event_time` at ~line 278, which posts a transaction with `event_time: "2026-06-25T09:00:00Z"`):

Add it directly after `test_ingest_publish_matches_persisted_event_time` (~line 293). All helpers used here already exist in the file: `_TXN` (payload constant, line ~41), `_ingest_headers()`, `_FakeScoring`, `get_scoring_client`, and the `client`/`session`/`seeded_reference` fixtures. Imports (`select`, `TransactionEvent`, `datetime`, `UTC`) are already present.

```python
async def test_event_row_carries_transaction_event_time(client, session, seeded_reference):
    """The denormalized transaction_events.event_time mirrors the producer's event_time,
    while surfaced_at stays ingestion (wall-clock) time — so detection lag stays measurable."""
    app = client._app
    app.dependency_overrides[get_scoring_client] = lambda: _FakeScoring()
    try:
        r = await client.post(
            "/api/v1/ingest", json={"transactions": [_TXN]}, headers=_ingest_headers()
        )
    finally:
        app.dependency_overrides.pop(get_scoring_client, None)
    assert r.status_code == 200

    ev = (
        await session.execute(
            select(TransactionEvent).where(TransactionEvent.transaction_id == 40217)
        )
    ).scalar_one()
    assert ev.event_time == datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    assert ev.surfaced_at != ev.event_time  # ingestion time is "now", not the CSV time
```

Note: tests in this file do not carry a `@pytest.mark.asyncio` decorator (asyncio mode is configured project-wide) — match that style.

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd grafin-ai-backend && uv run pytest tests/test_ingest_api.py::test_event_row_carries_transaction_event_time -q`
Expected: FAIL — `event_time` is not populated (NOT NULL violation or missing attribute).

- [ ] **Step 3: Populate it in the repository**

In `repositories/ingest.py`, inside `persist()`, build a lookup before `event_values` and use it. The incoming `transactions` list uses key `"id"` for the transaction id and already carries `"event_time"` (built in `api/ingest.py` as `{"id": t.transaction_id, "event_time": t.event_time, ...}`).

Insert immediately before the `event_values = [` line:

```python
            event_time_by_id = {t["id"]: t["event_time"] for t in transactions}
```

Then add the field to each event dict:

```python
            event_values = [
                {
                    "transaction_id": tid,
                    "surfaced_at": now,
                    "event_time": event_time_by_id[tid],
                    "fraud_score": scores_by_id[tid]["fraud_score"],
                    "typology": scores_by_id[tid]["typology"],
                    "status": scores_by_id[tid]["status"],
                }
                for tid in new_ids
            ]
```

- [ ] **Step 4: Run the tests**

Run: `cd grafin-ai-backend && uv run pytest -q`
Expected: baseline + 1 test, all passing.

- [ ] **Step 5: Commit**

```bash
cd grafin-ai-backend
git add grafin_ai_backend/repositories/ingest.py tests/test_ingest_api.py
git commit -m "feat: ingest writes denormalized event_time on the event row

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Backend — the data clock

**Files:**
- Modify: `grafin-ai-backend/grafin_ai_backend/api/deps.py`
- Create: `grafin-ai-backend/tests/test_data_clock.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_clock.py`:

```python
from datetime import UTC, datetime

import pytest

from grafin_ai_backend.api import deps


@pytest.mark.asyncio
async def test_data_clock_returns_latest_event_time(session, seeded_dataset):
    """'Now' on the dataset timeline is the newest ingested event_time (11:00 in the fixture)."""
    assert await deps.get_data_now(session) == datetime(2025, 9, 1, 11, tzinfo=UTC)


@pytest.mark.asyncio
async def test_data_clock_falls_back_to_wall_clock_when_empty(session):
    """An empty database must not error — fall back to wall-clock now()."""
    before = datetime.now(UTC)
    value = await deps.get_data_now(session)
    assert value >= before
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd grafin-ai-backend && uv run pytest tests/test_data_clock.py -q`
Expected: FAIL with `AttributeError: module ... has no attribute 'get_data_now'`.

- [ ] **Step 3: Replace `get_now` with `get_data_now`**

In `api/deps.py`, add these imports to the existing import block:

```python
from sqlalchemy import func, select

from grafin_ai_backend.schema import TransactionEvent
```

Then replace the whole `get_now` function and the `NowDep` line (currently lines ~81-88) with:

```python
async def get_data_now(session: SessionDep) -> datetime:
    """'Now' on the dataset's timeline: the latest event_time we have ingested.

    The views replay a historical dataset, so anchoring their windows to the wall
    clock would leave every window empty. Falls back to wall-clock now() on an empty
    database so a fresh install shows an empty dashboard rather than erroring.

    NOTE: auth/token expiry must NEVER use this clock — see security/tokens.py.
    """
    latest = await session.scalar(select(func.max(TransactionEvent.event_time)))
    return latest or datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_data_now)]
```

`NowDep` keeps its name, so no view signature changes.

- [ ] **Step 4: Run the tests**

Run: `cd grafin-ai-backend && uv run pytest tests/test_data_clock.py -q`
Expected: 2 passed.

- [ ] **Step 5: Update the 5 dependency overrides**

The view tests pin the clock via `app.dependency_overrides[deps.get_now]`. Rename the symbol in each (the lambda stays — FastAPI replaces the whole dependency, so no session parameter is needed):

Files: `tests/test_analytics_endpoint.py`, `tests/test_geo_endpoint.py`, `tests/test_metrics_endpoints.py`, `tests/test_transactions_endpoints.py`, `tests/test_users_view_endpoints.py`

In each, change:
```python
    app.dependency_overrides[deps.get_now] = lambda: seeded_dataset
```
to:
```python
    app.dependency_overrides[deps.get_data_now] = lambda: seeded_dataset
```

- [ ] **Step 6: Confirm no stale references remain**

Run: `cd grafin-ai-backend && grep -rn "get_now" grafin_ai_backend/ tests/ || echo "clean"`
Expected: `clean`.

- [ ] **Step 7: Run the full suite**

Run: `cd grafin-ai-backend && uv run pytest -q`
Expected: baseline + 3, all passing.

- [ ] **Step 8: Commit**

```bash
cd grafin-ai-backend
git add grafin_ai_backend/api/deps.py tests/
git commit -m "feat: data clock — 'now' is max(event_time), not the wall clock

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Backend — read views window on `event_time`

**Files:**
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/metrics.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/analytics.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/geo.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/users_view.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/transactions.py`

Every `surfaced_at` used as a **window bound or bucket key** becomes `event_time`. `surfaced_at` stays in SELECT payloads.

- [ ] **Step 1: `metrics.py` — three methods**

- In `overview()` (line ~25): `.where(TransactionEvent.surfaced_at <= now)` → `.where(TransactionEvent.event_time <= now)`
- In `volume()` (lines ~39, 45, 46):
  - `bucket = func.date_trunc(trunc, TransactionEvent.surfaced_at).label("bucket")` → `...TransactionEvent.event_time...`
  - `.where(TransactionEvent.surfaced_at <= now)` → `.where(TransactionEvent.event_time <= now)`
  - `.where(TransactionEvent.surfaced_at >= lower)` → `.where(TransactionEvent.event_time >= lower)`
- In `heatmap()` (lines ~57, 58, 61):
  - `dow = cast(func.extract("dow", TransactionEvent.surfaced_at), Integer).label("dow")` → `...event_time...`
  - `hour = cast(func.extract("hour", TransactionEvent.surfaced_at), Integer).label("hour")` → `...event_time...`
  - `.where(TransactionEvent.surfaced_at <= now)` → `.where(TransactionEvent.event_time <= now)`

- [ ] **Step 2: `analytics.py` — two filters**

Both `.where(TransactionEvent.surfaced_at <= now)` occurrences (in the typology aggregate and in `confusion_counts()`) become `.where(TransactionEvent.event_time <= now)`.

- [ ] **Step 3: `geo.py` — one filter**

`.where(TransactionEvent.surfaced_at <= now)` → `.where(TransactionEvent.event_time <= now)`.

- [ ] **Step 4: `users_view.py` — one join condition**

```python
            .join(
                TransactionEvent,
                (TransactionEvent.transaction_id == Transaction.id)
                & (TransactionEvent.event_time <= now),
                isouter=True,
            )
```

- [ ] **Step 5: `transactions.py` — filter only, keep the payload**

Change `.where(TransactionEvent.surfaced_at <= now)` → `.where(TransactionEvent.event_time <= now)`.

**Keep** `TransactionEvent.surfaced_at` in the SELECT column list and `"surfaced_at": r.surfaced_at.isoformat()` in the returned dict — Task 5 adds `event_time` alongside it.

- [ ] **Step 6: Confirm no window filter was missed**

Run: `cd grafin-ai-backend && grep -rn "surfaced_at" grafin_ai_backend/repositories/`
Expected: the only remaining hits are `ingest.py` (`"surfaced_at": now` on write) and `transactions.py` (the SELECT column + payload key). No `surfaced_at <= now`, `>= lower`, `date_trunc`, or `extract` remain.

- [ ] **Step 7: Run the full suite**

Run: `cd grafin-ai-backend && uv run pytest -q`
Expected: all passing (fixture hours were aligned in Task 1, so results are unchanged).

- [ ] **Step 8: Commit**

```bash
cd grafin-ai-backend
git add grafin_ai_backend/repositories/
git commit -m "feat: read views window on event_time (dataset timeline)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Backend — live feed carries `event_time`

**Files:**
- Modify: `grafin-ai-backend/grafin_ai_backend/api/ingest.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/repositories/transactions.py`
- Modify: `grafin-ai-backend/grafin_ai_backend/api/view_schemas.py`
- Modify: `grafin-ai-backend/tests/test_ingest_api.py`

The WS push and the `after_seq=` backfill must agree field-for-field, or the dashboard's live list and its reconnect-backfill would disagree.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ingest_api.py`:

There is already a publish test in this file that ends with assertions like `assert "surfaced_at" in message` / `assert "sim_now" not in message` (~line 270). **Locate that test, read how it subscribes and reads `message`, and copy that exact pattern** — do not invent new pub/sub fixtures. Then add the new test immediately after it:

```python
async def test_published_message_includes_event_time(client, seeded_reference):
    """The WS payload carries event_time so the dashboard labels events on the dataset
    timeline; surfaced_at stays for detection-lag."""
    # <-- same subscribe + post + read-message scaffolding as the existing publish test above
    assert message["event_time"] == "2026-06-25T09:00:00+00:00"
    assert "surfaced_at" in message
```

The expected value is the ISO form of `_TXN["event_time"]` (`"2026-06-25T09:00:00Z"`) after Pydantic parsing — i.e. `"2026-06-25T09:00:00+00:00"`. If the assertion fails only on the `Z` vs `+00:00` suffix, assert on the parsed value instead:
`assert datetime.fromisoformat(message["event_time"]) == datetime(2026, 6, 25, 9, 0, tzinfo=UTC)`.

Simpler alternative if the existing publish test is easy to extend: add the two assertions to it rather than writing a new test. Either is acceptable — one new assertion of `event_time` on a published message is the requirement.

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd grafin-ai-backend && uv run pytest tests/test_ingest_api.py::test_published_message_includes_event_time -q`
Expected: FAIL — `KeyError: 'event_time'`.

- [ ] **Step 3: Add `event_time` to the published message**

In `api/ingest.py`, in the publish loop (~line 130), add the field to the `message` dict:

```python
            message = {
                "seq": e.seq, "transaction_id": e.transaction_id,
                "bank": bank_names.get(t.from_bank_id), "type": t.payment_format,
                "amount": float(t.amount_paid), "fraud_score": e.fraud_score,
                "typology": e.typology, "status": e.status,
                "surfaced_at": now_iso,
                "event_time": t.event_time.isoformat(),
            }
```

- [ ] **Step 4: Add `event_time` to the live backfill rows**

In `repositories/transactions.py`, in the live-list SELECT column list add `TransactionEvent.event_time` (right after `TransactionEvent.surfaced_at`), and add the key to the returned dict:

```python
                "status": r.status, "surfaced_at": r.surfaced_at.isoformat(),
                "event_time": r.event_time.isoformat(),
```

- [ ] **Step 5: Add the field to the response schema**

In `api/view_schemas.py`, add `event_time: str` to the **`LiveItem`** model (the one with `seq` / `surfaced_at` / `status`, backing `LiveResponse`). Keep `surfaced_at`.

Do **not** confuse it with `TransactionDetail`, which already has its own `event_time: str` and needs no change.

- [ ] **Step 6: Run the full suite**

Run: `cd grafin-ai-backend && uv run pytest -q`
Expected: baseline + 4, all passing.

- [ ] **Step 7: Commit**

```bash
cd grafin-ai-backend
git add grafin_ai_backend/api/ingest.py grafin_ai_backend/repositories/transactions.py grafin_ai_backend/api/view_schemas.py tests/test_ingest_api.py
git commit -m "feat: live feed and backfill carry event_time

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Sim — send each row's CSV timestamp

**Files:**
- Modify: `grafin-ai-sim/grafin_ai_sim/producer.py`
- Modify: `grafin-ai-sim/grafin_ai_sim/reader.py`
- Modify: `grafin-ai-sim/tests/` (the producer tests)

- [ ] **Step 1: Write the failing test**

Add to `grafin-ai-sim/tests/test_producer.py`, reusing the file's existing `StubClient` and `_txn(ordinal, minute)` helpers and `_noop_sleep` (all already defined there). Note `Producer` takes explicit kwargs — there is no `settings=` parameter.

`batch_size=10` puts both rows in ONE batch, which is what proves the stamp is per-row rather than one shared per-batch value:

```python
async def test_event_time_is_per_row_csv_timestamp():
    """event_time must be each row's own CSV timestamp — not the wall clock, and not a
    single stamp shared across the batch. The dashboard plots the dataset's timeline."""
    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=10,
        sleep=_noop_sleep, new_correlation_id=lambda: "cid",
    )
    await producer.run([_txn(1, 0), _txn(2, 5)])

    sent = client.calls[0][0]          # (txns, correlation_id) of the first call
    assert sent[0]["event_time"] == "2025-09-01T00:00:00+00:00"
    assert sent[1]["event_time"] == "2025-09-01T00:05:00+00:00"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd grafin-ai-sim && uv run pytest tests/test_producer.py -q`
Expected: FAIL. Two distinct failures are expected and both are correct:
- the new test fails on the wall-clock/shared stamp, **or** errors on the removed `now=` kwarg not yet being optional — either way it is red before the change;
- it may also fail construction because `now` is still a parameter — that is fine, Step 3/4 fix both.

- [ ] **Step 3: Stamp per row from the CSV**

In `producer.py`'s `flush()`, delete the line `stamp = self._now().isoformat()` and change the payload build to:

```python
            payloads: list[dict[str, object]] = [
                {**t.fields, "transaction_id": t.ordinal, "event_time": t.csv_ts.isoformat()}
                for t in batch
            ]
```

- [ ] **Step 4: Remove the now-dead `now` seam**

`self._now` had exactly one use (the deleted line). Remove:
- the `now: Callable[[], datetime] | None = None,` constructor parameter (line ~45)
- the `self._now = now or (lambda: datetime.now(UTC))` assignment (line ~53)
- the `UTC` import if nothing else uses it. **Keep the `datetime` import** — `prev_last_ts: datetime | None` still needs it. Let `ruff` decide: run it after the edit and remove exactly what it flags.

Keep the `sleep` and `new_correlation_id` seams; they are still used.

**Two existing tests in `tests/test_producer.py` pass `now=` and must be updated** (they will otherwise fail with an unexpected-keyword `TypeError`):

1. `test_pacing_batching_and_stamping` (~line 28) — remove `now=lambda: fixed,` from the constructor and delete the now-unused `fixed = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)` line. Its stamping assertion at line ~46:
   ```python
       assert first_payload["event_time"] == fixed.isoformat()   # stamped from now
   ```
   becomes (the first row is `_txn(1, 0)` → `2025-09-01 00:00`):
   ```python
       assert first_payload["event_time"] == "2025-09-01T00:00:00+00:00"   # the row's own CSV time
   ```
   Everything else in that test (the `delays == [1.0, 2.0]` pacing assertion, `SimStats`) must stay **unchanged** — pacing behaviour is not changing, and that assertion is the guard proving it.

2. `test_dry_run_posts_nothing` (~line 52) — remove `now=lambda: datetime(2026, 8, 4, tzinfo=UTC),` from the constructor. No other change.

- [ ] **Step 5: Correct the stale comment in `reader.py`**

Line 10 currently reads:
```python
    csv_ts: datetime                # original CSV timestamp; used ONLY for pacing, never sent
```
Change to:
```python
    csv_ts: datetime                # original CSV timestamp; paces sending AND is sent as event_time
```

- [ ] **Step 6: Run the sim suite + typecheck**

Run:
```bash
cd grafin-ai-sim
uv run pytest -q
uv run ruff check .
uv run mypy --strict grafin_ai_sim
```
Expected: all tests pass; ruff clean (it will flag unused imports if Step 4 left any); mypy clean.

- [ ] **Step 7: Commit**

```bash
cd grafin-ai-sim
git add grafin_ai_sim/ tests/
git commit -m "feat: send each row's CSV timestamp as event_time

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Frontend — show dataset time in the live feed

**Files:**
- Modify: `grafin-ai-dashboard-web/src/api/types.ts`
- Modify: `grafin-ai-dashboard-web/src/api/useLiveTransactions.ts`
- Modify: `grafin-ai-dashboard-web/src/components/TransactionMonitor.tsx`
- Modify: `grafin-ai-dashboard-web/src/api/types.test.ts`
- Modify: `grafin-ai-dashboard-web/src/api/useLiveTransactions.test.tsx`

**Note:** this repo has no TypeScript toolchain (no `tsconfig.json`, no `typescript` dependency), so `tsc --noEmit` is unavailable. Verify with `npm test` and `npm run build`.

- [ ] **Step 1: Add `event_time` to the types**

In `src/api/types.ts`, add `event_time: string;` (keeping `surfaced_at`) to **both** interfaces that carry `surfaced_at`, so the REST backfill and the WS push have matching shapes:
- `LiveItem` (~line 37-47, backing `LiveResponse` — the `after_seq=` backfill)
- `LiveEvent` (~line 93-103 — the WS message)

- [ ] **Step 2: Carry it through the hook**

In `src/api/useLiveTransactions.ts` line ~49, add the field to the mapped object:

```ts
          typology: ev.typology, status: ev.status, surfaced_at: ev.surfaced_at,
          event_time: ev.event_time,
```

- [ ] **Step 3: Render dataset time**

In `src/components/TransactionMonitor.tsx` line ~218, change:
```tsx
                        {formatTime(item.surfaced_at)}
```
to:
```tsx
                        {formatTime(item.event_time)}
```

- [ ] **Step 4: Update the fixtures**

- `src/api/types.test.ts` line ~12: add `event_time: '2025-09-01T00:00:00Z',` to the object literal.
- `src/api/useLiveTransactions.test.tsx` lines ~27, 35, 39: add `event_time: 't'` to each of the three event literals (matching the existing `surfaced_at: 't'` style).

- [ ] **Step 5: Run the frontend tests and build**

Run:
```bash
cd grafin-ai-dashboard-web
npm test -- --watchAll=false
npm run build
```
Expected: all tests pass; build succeeds.

- [ ] **Step 6: Commit**

```bash
cd grafin-ai-dashboard-web
git add src/
git commit -m "feat: live feed shows dataset event_time

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Note: if `git config user.email` in this repo is not `thariqiskandar9@gmail.com`, set it locally first.

---

## Task 8: End-to-end verification with a fresh replay

**Files:** none (verification only)

The DB currently holds wall-clock-stamped rows dated 2026-08-12. They would out-rank every Sept-2025 row and pin the data clock to today, so a wipe is required. **The user has explicitly acknowledged this.**

- [ ] **Step 1: Wipe and rebuild**

```bash
cd grafin-ai-deploy
docker compose down -v
docker compose up -d --build
```

- [ ] **Step 2: Wait for the stack and confirm the seed**

```bash
docker compose ps
docker compose logs ingest --tail=20
```
Expected: `backend` healthy; `ingest` exited 0 with `seed.done` (~30470 banks / 166207 entities / 518573 accounts).

- [ ] **Step 3: Stream a bounded slice of the dataset**

```bash
cd grafin-ai-deploy
docker compose run --rm -e GRAFIN_LIMIT=20000 -e GRAFIN_SPEED=600 sim
```
Expected: `sim.batch` logs, ending with the run summary; no errors.

- [ ] **Step 4: Verify the stored timestamps are dataset time**

```bash
docker compose exec -T postgres psql -U "${POSTGRES_USER:-grafin}" -d "${POSTGRES_DB:-grafin}" \
  -c "select min(event_time), max(event_time), min(surfaced_at), max(surfaced_at) from transaction_events;"
```
Expected: `event_time` min/max fall inside **2025-09-01 → 2025-09-10**, while `surfaced_at` shows today's date — proving the two clocks are correctly distinct.

- [ ] **Step 5: Verify the API reports the dataset timeline**

```bash
TOKEN=$(curl -s -X POST http://localhost:${BACKEND_HOST_PORT:-8000}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@grafin.local","password":"admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s "http://localhost:${BACKEND_HOST_PORT:-8000}/api/v1/metrics/volume?range=24h" \
  -H "Authorization: Bearer $TOKEN" | head -c 400
```
Expected: bucket timestamps in **September 2025**, not 2026.

- [ ] **Step 6: Verify the dashboard**

Open `http://localhost:${FRONTEND_HOST_PORT:-8080}`, sign in as `admin@grafin.local` / `admin`.
Expected: the Transaction Volume Trends X axis and the live feed both show **September 2025** timestamps; stat cards are populated (not zero).

- [ ] **Step 7: Record the outcome**

If any step fails, STOP and report the actual output rather than adjusting expectations. If all pass, note in the final report that the end-to-end replay was verified live.

---

## Definition of Done

- `transaction_events.event_time` exists, indexed and NOT NULL, populated on every ingest; migration upgrades and downgrades cleanly.
- `get_data_now()` returns `max(event_time)` with a wall-clock fallback; no reference to `get_now` remains anywhere.
- All six read modules window/bucket on `event_time`; `surfaced_at` survives only as a write value and a payload field.
- WS push and `after_seq=` backfill both carry `event_time`; the dashboard's live feed renders it.
- Sim sends each row's own CSV timestamp; pacing behaviour unchanged; the dead `now` seam removed; ruff + mypy --strict clean.
- Backend suite passes at baseline + 4 new tests; frontend tests and build pass.
- Auth still uses wall-clock time (`security/tokens.py` untouched) — login works after the change.
- A fresh replay shows September 2025 across the dashboard, with `surfaced_at` still showing real ingestion time.
- Every commit authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer; nothing pushed to any remote.
