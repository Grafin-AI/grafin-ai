# Shed Simulation — Backend Plan (Phase 5 ①)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the accelerated-simulation machinery from `grafin-ai-backend`: re-anchor reads from `sim_state.sim_now` to wall-clock `now()`, delete the `/sim` endpoints + `sim_state` table + `SimRepository`/schema/seed, and drop the redundant `sim_now` from the WS live-event message.

**Architecture:** The events now enter via `/ingest` (stamped `surfaced_at = now()`), so every read view's `surfaced_at <= sim_now` filter just re-binds to wall-clock `now()`. This is a **dependency swap** (`get_sim_now` → `get_now`) plus deletions — no query rewrites. Tests keep their deterministic 2025 fixture data by overriding `get_now` to the fixed `SIM_NOW` instant.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, pytest + testcontainers. No new deps.

**Spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-25-shed-simulation-design.md`

**Guardrail — do NOT remove:** `SystemHealthResponse.model_accuracy_simulated` / the "Simulated (Phase 1)" concept. That is scorer honesty, unrelated to the sim clock.

---

## Task 1: Re-anchor the read dependency (`get_sim_now` → `get_now`)

**Files:**
- Modify: `grafin_ai_backend/api/deps.py`
- Modify: `grafin_ai_backend/api/geo.py`, `api/metrics.py`, `api/transactions.py`, `api/users_view.py`, `api/analytics.py`
- Modify (tests): `tests/test_geo_endpoint.py`, `tests/test_metrics_endpoints.py`, `tests/test_analytics_endpoint.py`, `tests/test_users_view_endpoints.py`, `tests/test_transactions_endpoints.py`

- [ ] **Step 1: Replace the dependency in `api/deps.py`**

Remove the `SimRepository` import (`from grafin_ai_backend.repositories.sim import SimRepository`) and replace the whole `get_sim_now` / `SimNowDep` block:

```python
async def get_sim_now(session: SessionDep) -> datetime:
    """Shared dependency: the simulation clock, or 404 if uninitialized.

    Every view aggregate filters `surfaced_at <= sim_now`; this is the one
    typed source so view routers don't each re-implement the lookup.
    """
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized"
        )
    return sim_now


SimNowDep = Annotated[datetime, Depends(get_sim_now)]
```

with:

```python
def get_now() -> datetime:
    """Shared 'now' for the read views. Events enter via /ingest stamped
    surfaced_at = now(), so each view's `surfaced_at <= now` filter reflects
    real wall-clock-current data (the old accelerated sim clock is gone)."""
    return datetime.now(UTC)


NowDep = Annotated[datetime, Depends(get_now)]
```

Add `UTC` to the datetime import: `from datetime import UTC, datetime`. (`HTTPException`/`status` are still used by `get_current_user`/`require_role`, so keep those imports.)

- [ ] **Step 2: Swap the dependency in the 6 view routers**

In each of `api/geo.py`, `api/metrics.py`, `api/transactions.py`, `api/users_view.py`, `api/analytics.py`:
- Change the import `SimNowDep` → `NowDep` (in the `from grafin_ai_backend.api.deps import ...` line).
- Rename every `sim_now` identifier to `now` throughout the file (it is used **only** as this dependency variable in these files — signatures `sim_now: SimNowDep` → `now: NowDep`, and its uses like `sim_now.isoformat()`, `sim_now - window`, `repo.overview(sim_now)` → `now...`). Occurrence guide: geo (1 param + 2 uses), metrics (3 params + several cache-key/window uses), transactions (1 param + 1 use), users_view (2 params + 2 uses), analytics (1 param + several uses).

Example — `api/transactions.py` handler after the change:
```python
from grafin_ai_backend.api.deps import CurrentUserDep, SessionDep, NowDep
...
@router.get("/live", response_model=LiveResponse)
async def live(
    session: SessionDep,
    now: NowDep,
    _: CurrentUserDep,
    after_seq: int | None = None,
    limit: int = Query(default=50, le=200),
) -> LiveResponse:
    rows = await TransactionsRepository(session).live_window(now, after_seq, limit)
    return LiveResponse(items=[LiveItem(**r) for r in rows])
```

The repository methods are UNCHANGED (they still take a `datetime`).

- [ ] **Step 3: Override `get_now` to the fixed `SIM_NOW` in the 5 endpoint-test client fixtures**

Each of the 5 endpoint test files has a `client` fixture that already depends on the `seeded_dataset` fixture (whose return value **is** `SIM_NOW`) and sets `app.dependency_overrides[deps.get_session] = _override_session`. Add one line right after it, reusing that fixture value so the deterministic 2025 data stays in-window — no import needed:

```python
    app.dependency_overrides[deps.get_now] = lambda: seeded_dataset
```

(`seeded_dataset` is the `SIM_NOW` datetime returned by the fixture; `deps` is already imported in these fixtures. This avoids any `from tests.conftest import ...` path fragility.)

- [ ] **Step 4: Run the affected endpoint tests**

Run: `uv run pytest tests/test_geo_endpoint.py tests/test_metrics_endpoints.py tests/test_analytics_endpoint.py tests/test_users_view_endpoints.py tests/test_transactions_endpoints.py -q`
Expected: all PASS (same data window as before, now via the `get_now` override). If any assertion depended on the sim clock differently, fix the expectation — the data is identical to before.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: re-anchor read views from sim clock to wall-clock now()"
```

---

## Task 2: Drop `sim_now` from the WS live-event message

**Files:**
- Modify: `grafin_ai_backend/api/ingest.py`
- Modify: `tests/test_ingest_api.py`

- [ ] **Step 1: Remove the field from the published message**

In `api/ingest.py`, the message dict (around line 130-135) has:
```python
                "surfaced_at": now_iso, "sim_now": now_iso,
```
Change it to:
```python
                "surfaced_at": now_iso,
```

- [ ] **Step 2: Update the publish test**

In `tests/test_ingest_api.py`, replace the assertion:
```python
    assert "sim_now" in message
```
with:
```python
    assert "sim_now" not in message
```
(Keep `assert "surfaced_at" in message`.)

- [ ] **Step 3: Run the ingest tests**

Run: `uv run pytest tests/test_ingest_api.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: drop redundant sim_now from the live-event message"
```

---

## Task 3: Delete the `/sim` control surface

**Files:**
- Delete: `grafin_ai_backend/api/sim.py`, `grafin_ai_backend/repositories/sim.py`, `tests/test_sim_endpoints.py`
- Modify: `grafin_ai_backend/main.py`, `grafin_ai_backend/api/view_schemas.py`

- [ ] **Step 1: Delete the files**

```bash
git rm grafin_ai_backend/api/sim.py grafin_ai_backend/repositories/sim.py tests/test_sim_endpoints.py
```

- [ ] **Step 2: Remove the router from `main.py`**

Delete the import line `from grafin_ai_backend.api.sim import router as sim_router` and the registration line `app.include_router(sim_router)`.

- [ ] **Step 3: Remove the sim schemas from `api/view_schemas.py`**

Delete the `SimStateResponse` and `SimControlRequest` classes (lines 6-16). If `datetime` is no longer imported/used elsewhere in the file after this, leave the import only if still needed (check — it likely is used by other schemas; if not, remove it to keep ruff clean).

- [ ] **Step 4: Verify no dangling references**

Run: `uv run ruff check grafin_ai_backend && grep -rn "SimStateResponse\|SimControlRequest\|api.sim\|repositories.sim\|SimRepository" grafin_ai_backend tests || echo "clean"`
Expected: ruff clean; grep prints `clean` (no matches).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: remove the /sim state+control endpoints and SimRepository"
```

---

## Task 4: Simplify `system/health` (drop the sim lookup)

**Files:**
- Modify: `grafin_ai_backend/api/system.py`
- Modify (if needed): `tests/test_system_endpoint.py`

- [ ] **Step 1: Rewrite the health handler**

Replace `api/system.py` with (removes the `SimRepository` import + lookup; `events_surfaced` becomes a plain total; `model_accuracy_simulated` STAYS):

```python
from fastapi import APIRouter
from sqlalchemy import func, select, text

from grafin_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from grafin_ai_backend.api.view_schemas import SystemHealthResponse
from grafin_ai_backend.schema import TransactionEvent

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health", response_model=SystemHealthResponse)
async def health(session: SessionDep, redis: RedisDep, _: CurrentUserDep) -> SystemHealthResponse:
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    surfaced = (
        await session.execute(select(func.count()).select_from(TransactionEvent))
    ).scalar_one()

    return SystemHealthResponse(
        db_ok=db_ok,
        redis_ok=redis_ok,
        events_surfaced=int(surfaced),
        model_accuracy_simulated=True,  # Phase 1 label-replay — not a trained-model metric
    )
```

- [ ] **Step 2: Update the system-endpoint test if it asserted a sim-windowed count**

Run: `uv run pytest tests/test_system_endpoint.py -q`
If a test asserted `events_surfaced` equal to a sim-windowed subset or expected a 404 on uninitialized sim, update it: `events_surfaced` is now the total `transaction_events` count (the `seeded_dataset` has 4). Keep `db_ok`/`redis_ok`/`model_accuracy_simulated` assertions.
Expected after fix: PASS.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: system/health no longer depends on the sim clock"
```

---

## Task 5: Remove the `SimState` model, seed, and test fixtures

**Files:**
- Delete: `grafin_ai_backend/schema/sim.py`
- Modify: `grafin_ai_backend/schema/__init__.py`, `grafin_ai_backend/seed.py`, `tests/conftest.py`, `tests/test_schema.py`, `tests/test_seed.py`

- [ ] **Step 1: Delete the model + export**

```bash
git rm grafin_ai_backend/schema/sim.py
```
In `schema/__init__.py`, remove `from grafin_ai_backend.schema.sim import SimState` and remove `"SimState"` from `__all__` (and the trailing reference in the list).

- [ ] **Step 2: Remove sim seeding from `seed.py`**

Delete the `ensure_sim_state` function, the `from grafin_ai_backend.schema import SimState` import, and its call in `_main`:
```python
        await ensure_sim_state(
            session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0
        )
```
`_main` keeps `ensure_admin(...)` + `session.commit()`. (`datetime`/`UTC` are still used by `ensure_admin`.)

- [ ] **Step 3: Remove the `SimState` seed from `tests/conftest.py`**

Remove `SimState` from the `from grafin_ai_backend.schema import (...)` tuple, and delete the line:
```python
    session.add(SimState(id=1, sim_now=SIM_NOW, speed=Decimal("60"), running=True))
```
**Keep** the `SIM_NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)` constant and `return SIM_NOW` — they now serve only as the fixed instant the fixture data is built around and the `get_now` test override uses.

- [ ] **Step 4: Update `test_schema.py` and `test_seed.py`**

- `test_schema.py`: remove any `SimState` import and assertions about the `sim_state` table/model.
- `test_seed.py`: remove the `ensure_sim_state` import and its test(s); keep the `ensure_admin` test.

- [ ] **Step 5: Verify + run**

Run: `grep -rn "SimState\|ensure_sim_state\|sim_state" grafin_ai_backend tests || echo clean`
Expected: `clean` (only the Alembic migration in Task 6 will reference `sim_state`, not added yet).
Run: `uv run pytest tests/test_schema.py tests/test_seed.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: remove the SimState model, seed, and test fixtures"
```

---

## Task 6: Alembic migration — drop `sim_state`

**Files:**
- Create: `migrations/versions/<newrev>_drop_sim_state.py`

- [ ] **Step 1: Write the migration**

Create the file (pick any unused 12-hex `revision` id; `down_revision` is the current head `c105fac3e957`):

```python
"""drop sim_state

Revision ID: b2f1a9c4d7e0
Revises: c105fac3e957
Create Date: 2026-06-25

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f1a9c4d7e0"
down_revision: Union[str, Sequence[str], None] = "c105fac3e957"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("sim_state")


def downgrade() -> None:
    op.create_table(
        "sim_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sim_now", sa.DateTime(timezone=True), nullable=False),
        sa.Column("speed", sa.Numeric(), server_default=sa.text("1.0"), nullable=False),
        sa.Column("running", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("id = 1", name="sim_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
```

- [ ] **Step 2: Run the migration round-trip test**

Run: `uv run pytest tests/test_migrations.py -q`
Expected: PASS (the migrated schema now matches `Base.metadata`, which no longer has `sim_state`; upgrade→downgrade round-trips).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Alembic migration dropping the sim_state table"
```

---

## Task 7: Full verification

- [ ] **Step 1: Run the whole suite + lint + type-check**

Run: `uv run pytest -q && uv run ruff check grafin_ai_backend && uv run mypy grafin_ai_backend`
Expected: all green. (The pre-existing 12 unrelated ruff errors noted in earlier phases, if still present, are out of scope — do not touch files you didn't change in this plan; scope ruff to the changed files if needed: `uv run ruff check <changed files>`.)

- [ ] **Step 2: Confirm no sim residue in code**

Run: `grep -rn "sim_now\|SimState\|SimRepository\|/sim\|get_sim_now\|SimNowDep\|ensure_sim_state" grafin_ai_backend || echo "clean"`
Expected: `clean`.

- [ ] **Step 3: Commit any final fixups (if the previous steps required them)**

```bash
git add -A
git commit -m "chore: backend sim-shed cleanup" || echo "nothing to commit"
```

---

## Definition of Done

- `uv run pytest -q` green; `uv run ruff check grafin_ai_backend` clean on changed files; `uv run mypy grafin_ai_backend` clean.
- Reads anchored to wall-clock `now()` via `get_now`/`NowDep`; no `get_sim_now`/`SimNowDep`.
- `/sim/*` endpoints, `SimRepository`, `SimState` model + `sim_state` table (Alembic drop), and the sim schemas/seed are gone.
- The WS live-event message no longer carries `sim_now`.
- `model_accuracy_simulated` / "Simulated (Phase 1)" is PRESERVED.
- All commits authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer.
```
