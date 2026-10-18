# Backend View Endpoints Implementation Plan (Plan 2B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement every dashboard read endpoint in `garda-ai-backend` — metrics overview, transaction volume, heatmap, fraud analytics, geographic provinces, user-risk list + profile detail, alerts list + ack, live transactions + transaction detail, system health, and the sim clock (state + admin control). All aggregate over `transaction_events` surfaced so far (`surfaced_at ≤ sim_now`), apply server-side PII masking, are role-gated, and Redis-cache the heavy aggregates.

**Architecture:** Continues the Plan-1/2A layering — `api/` routers (role-gated, no logic) → `services/` (use cases, masking, caching) → `repositories/` (all SQL) → `schema/`. PII masking lives in a serialization helper (never in repositories). `sim_now` is read from the `sim_state` singleton. There is no live data yet (the pipeline in Plan 3 loads it), so tests seed a small fixed dataset via a shared fixture.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async (aggregations in SQL), Pydantic v2, redis.asyncio (aggregate cache), pytest + testcontainers (Postgres + Redis).

---

## Conventions used throughout

- **sim_now source:** `SimRepository.get_sim_now(session)` returns `sim_state.sim_now` (seeded row id=1). Every aggregate filters `transaction_events.surfaced_at <= sim_now`.
- **Status values:** `approved | flagged | blocked`. "Flagged" for dashboards = `status IN ('flagged','blocked')`.
- **Role gating:** read endpoints require `require_role("analyst", "admin")`; `POST /sim/control` requires `require_role("admin")`.
- **Masking:** applied in services via `garda_ai_backend/api/masking.py` for `analyst`; `admin` requests may pass `?unmasked=true` (audited-logged).
- **Caching:** `cached_json(redis, key, ttl, compute)` helper; key includes endpoint + a `sim_now` bucket + params.
- **Money:** `Decimal` in the DB → serialized as `float`/string in responses (Pydantic handles `Decimal`→JSON; use `float` fields in response models for the frontend).

## File structure (created/modified by this plan)

```
garda_ai_backend/
├── api/
│   ├── masking.py                 # CREATE: mask_name, mask_account_id, mask_payment_id
│   ├── cache.py                   # CREATE: cached_json(redis, key, ttl, compute)
│   ├── view_schemas.py            # CREATE: Pydantic response models for all views
│   ├── metrics.py                 # CREATE: /metrics/overview, /volume, /heatmap router
│   ├── analytics.py               # CREATE: /analytics/fraud router
│   ├── geo.py                     # CREATE: /geo/provinces router
│   ├── users_view.py              # CREATE: /users/risk, /users/{id}/profile router
│   ├── alerts.py                  # CREATE: /alerts, /alerts/{id}/ack router
│   ├── transactions.py            # CREATE: /transactions/live, /transactions/{id} router
│   ├── system.py                  # CREATE: /system/health router
│   └── sim.py                     # CREATE: /sim/state, /sim/control router
├── repositories/
│   ├── sim.py                     # CREATE: SimRepository (get_sim_now, get_state, update_state)
│   ├── metrics.py                 # CREATE: MetricsRepository (overview, volume, heatmap)
│   ├── analytics.py               # CREATE: AnalyticsRepository (typology dist, confusion counts)
│   ├── geo.py                     # CREATE: GeoRepository (province rollups)
│   ├── users_view.py              # CREATE: UserRiskRepository (risk list, profile aggregates)
│   ├── alerts.py                  # CREATE: AlertsRepository (list, ack)
│   └── transactions.py            # CREATE: TransactionsRepository (live window, by id)
├── services/
│   └── views.py                   # CREATE: thin services applying masking + caching over repos
└── main.py                        # MODIFY: include all view routers
tests/
├── conftest.py                    # MODIFY: add seeded_dataset fixture
├── test_view_masking.py
├── test_view_cache.py
├── test_sim_endpoints.py
├── test_metrics_endpoints.py
├── test_analytics_endpoint.py
├── test_geo_endpoint.py
├── test_users_view_endpoints.py
├── test_alerts_endpoints.py
├── test_transactions_endpoints.py
└── test_system_endpoint.py
```

---

### Task 1: Shared seeded-dataset fixture

A small deterministic dataset every view test reuses: 2 banks, 2 entities (with provinces), 2 accounts, 4 transactions (2 laundering), 4 transaction_events (mix of statuses/typologies), 1 alert, sim_state with `sim_now` after all events.

**Files:**
- Modify: `tests/conftest.py`
- Test: (used by later tasks; no standalone test)

- [ ] **Step 1: Add the fixture to `tests/conftest.py`**

Append at the end:
```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio as _pytest_asyncio

from garda_ai_backend.schema import (
    Account,
    Alert,
    Bank,
    Entity,
    SimState,
    Transaction,
    TransactionEvent,
)

SIM_NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)


@_pytest_asyncio.fixture
async def seeded_dataset(session):
    """Deterministic mini dataset for view-endpoint tests."""
    session.add_all([
        Bank(id="10", name="Bank Rakyat Indonesia (BRI)"),
        Bank(id="20", name="Bank Mandiri"),
        Entity(id="E1", name="Ahmad Setiawan", province="DKI Jakarta"),
        Entity(id="E2", name="Budi Santoso", province="Jawa Barat"),
    ])
    await session.flush()
    session.add_all([
        Account(id="ACC1", bank_id="10", entity_id="E1", risk_score=Decimal("80"), risk_category="High"),
        Account(id="ACC2", bank_id="20", entity_id="E2", risk_score=Decimal("10"), risk_category="Low"),
    ])
    await session.flush()

    def _txn(i, frm, to, amount, launder):
        return Transaction(
            id=i, event_time=datetime(2025, 9, 1, 9 + i, tzinfo=UTC),
            from_bank_id="10", from_account=frm, to_bank_id="20", to_account=to,
            amount_paid=Decimal(amount), payment_currency="IDR",
            amount_received=Decimal(amount), receiving_currency="IDR",
            payment_format="ACH", is_laundering=launder,
        )
    session.add_all([
        _txn(1, "ACC1", "ACC2", "15000000", True),
        _txn(2, "ACC2", "ACC1", "250000", False),
        _txn(3, "ACC1", "ACC2", "5000000", True),
        _txn(4, "ACC2", "ACC1", "150000", False),
    ])
    await session.flush()

    def _ev(seq, tid, score, typ, status, hour):
        return TransactionEvent(
            seq=seq, transaction_id=tid, surfaced_at=datetime(2025, 9, 1, hour, tzinfo=UTC),
            fraud_score=Decimal(score), typology=typ, status=status,
        )
    session.add_all([
        _ev(1, 1, "0.95", "Fan-Out", "blocked", 9),
        _ev(2, 2, "0.10", None, "approved", 10),
        _ev(3, 3, "0.78", "Smurfing", "flagged", 11),
        _ev(4, 4, "0.05", None, "approved", 11),
    ])
    await session.flush()
    session.add(Alert(
        id=1, event_seq=1, severity="high", typology="Fan-Out",
        created_at=datetime(2025, 9, 1, 9, tzinfo=UTC),
    ))
    session.add(SimState(id=1, sim_now=SIM_NOW, speed=Decimal("60"), running=True))
    await session.commit()
    return SIM_NOW
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `uv run pytest tests/test_config.py -q`
Expected: still green (the new fixture only adds importable code; no test uses it yet).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: shared seeded dataset fixture for view endpoints"
```

---

### Task 2: PII masking helper

**Files:**
- Create: `garda_ai_backend/api/masking.py`
- Test: `tests/test_view_masking.py`

- [ ] **Step 1: Write the failing test**

`tests/test_view_masking.py`:
```python
from garda_ai_backend.api.masking import mask_account_id, mask_name


def test_mask_name_keeps_initials():
    assert mask_name("Ahmad Setiawan") == "A**** S****"
    assert mask_name("Budi") == "B****"
    assert mask_name("") == ""


def test_mask_account_id_keeps_last4():
    assert mask_account_id("80B779D80") == "*****9D80"
    assert mask_account_id("123") == "***"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_view_masking.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`garda_ai_backend/api/masking.py`:
```python
def mask_name(name: str) -> str:
    """Mask each word to its initial + asterisks: 'Ahmad Setiawan' -> 'A**** S****'."""
    if not name:
        return ""
    return " ".join(w[0] + "*" * (len(w) - 1) if len(w) > 1 else w[0] for w in name.split())


def mask_account_id(account_id: str) -> str:
    """Keep the last 4 chars, mask the rest. Short ids are fully masked."""
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def mask_payment_id(payment_id: str) -> str:
    return mask_account_id(payment_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_view_masking.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_backend/api/masking.py tests/test_view_masking.py
git commit -m "feat: server-side PII masking helpers"
```

---

### Task 3: Redis aggregate cache helper

**Files:**
- Create: `garda_ai_backend/api/cache.py`
- Test: `tests/test_view_cache.py`

- [ ] **Step 1: Write the failing test**

`tests/test_view_cache.py`:
```python
from garda_ai_backend.api.cache import cached_json


async def test_cached_json_computes_once(redis_client):
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"value": 42}

    first = await cached_json(redis_client, "k1", ttl=60, compute=compute)
    second = await cached_json(redis_client, "k1", ttl=60, compute=compute)
    assert first == {"value": 42}
    assert second == {"value": 42}
    assert calls["n"] == 1  # second call served from cache


async def test_cached_json_separate_keys(redis_client):
    async def compute_a():
        return {"v": "a"}

    async def compute_b():
        return {"v": "b"}

    assert await cached_json(redis_client, "ka", ttl=60, compute=compute_a) == {"v": "a"}
    assert await cached_json(redis_client, "kb", ttl=60, compute=compute_b) == {"v": "b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_view_cache.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`garda_ai_backend/api/cache.py`:
```python
import json
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis


async def cached_json(
    redis: Redis, key: str, ttl: int, compute: Callable[[], Awaitable[Any]]
) -> Any:
    """Return cached JSON for ``key`` or compute, store (ttl seconds), and return it."""
    cached = await redis.get(f"agg:{key}")
    if cached is not None:
        return json.loads(cached)
    value = await compute()
    await redis.set(f"agg:{key}", json.dumps(value, default=str), ex=ttl)
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_view_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_backend/api/cache.py tests/test_view_cache.py
git commit -m "feat: redis aggregate cache helper (cached_json)"
```

---

### Task 4: Sim repository + sim endpoints

**Files:**
- Create: `garda_ai_backend/repositories/sim.py`
- Create: `garda_ai_backend/api/view_schemas.py` (started here, extended later)
- Create: `garda_ai_backend/api/sim.py`
- Modify: `garda_ai_backend/main.py` (include sim router)
- Test: `tests/test_sim_endpoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sim_endpoints.py`:
```python
from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token

SECRET = "test-secret"


def _auth(role: str) -> dict:
    token = create_access_token(subject="1", role=role, secret=SECRET, ttl_min=15)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)

    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_get_sim_state(client):
    r = await client.get("/api/v1/sim/state", headers=_auth("analyst"))
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert body["speed"] == 60.0
    assert body["sim_now"].startswith("2025-09-01")


async def test_sim_control_requires_admin(client):
    r = await client.post(
        "/api/v1/sim/control", json={"running": False}, headers=_auth("analyst")
    )
    assert r.status_code == 403


async def test_sim_control_admin_updates(client):
    r = await client.post(
        "/api/v1/sim/control",
        json={"running": False, "speed": 120.0},
        headers=_auth("admin"),
    )
    assert r.status_code == 200
    assert r.json()["running"] is False
    assert r.json()["speed"] == 120.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sim_endpoints.py -v`
Expected: FAIL (router/modules missing).

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/sim.py`:
```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import SimState


class SimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_state(self) -> SimState | None:
        return await self._session.get(SimState, 1)

    async def get_sim_now(self) -> datetime | None:
        state = await self.get_state()
        return state.sim_now if state else None

    async def update_state(
        self,
        running: bool | None = None,
        speed: float | None = None,
        sim_now: datetime | None = None,
    ) -> SimState:
        state = await self._session.get(SimState, 1)
        if state is None:
            raise ValueError("sim_state not seeded")
        if running is not None:
            state.running = running
        if speed is not None:
            state.speed = Decimal(str(speed))
        if sim_now is not None:
            state.sim_now = sim_now
        await self._session.flush()
        return state
```

- [ ] **Step 4: Start the view schemas**

`garda_ai_backend/api/view_schemas.py`:
```python
from datetime import datetime

from pydantic import BaseModel


class SimStateResponse(BaseModel):
    sim_now: datetime
    speed: float
    running: bool


class SimControlRequest(BaseModel):
    running: bool | None = None
    speed: float | None = None
    sim_now: datetime | None = None
```

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/sim.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep, require_role
from garda_ai_backend.api.view_schemas import SimControlRequest, SimStateResponse
from garda_ai_backend.repositories.sim import SimRepository

router = APIRouter(prefix="/api/v1/sim", tags=["sim"])


@router.get("/state", response_model=SimStateResponse)
async def get_state(session: SessionDep, _: CurrentUserDep) -> SimStateResponse:
    state = await SimRepository(session).get_state()
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    return SimStateResponse(sim_now=state.sim_now, speed=float(state.speed), running=state.running)


@router.post("/control", response_model=SimStateResponse)
async def control(
    body: SimControlRequest,
    session: SessionDep,
    _: CurrentUserDep = Depends(require_role("admin")),
) -> SimStateResponse:
    repo = SimRepository(session)
    state = await repo.update_state(running=body.running, speed=body.speed, sim_now=body.sim_now)
    await session.commit()
    return SimStateResponse(sim_now=state.sim_now, speed=float(state.speed), running=state.running)
```

- [ ] **Step 6: Wire the router into `main.py`**

In `garda_ai_backend/main.py`, after the existing `app.include_router(auth_router)` line, add:
```python
from garda_ai_backend.api.sim import router as sim_router

app.include_router(sim_router)
```
(Place the import with the other imports at the top and the `include_router` call after `auth_router`.)

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_sim_endpoints.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/sim.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/sim.py garda_ai_backend/main.py tests/test_sim_endpoints.py
git commit -m "feat: sim repository + /sim/state and /sim/control (admin) endpoints"
```

---

### Task 5: Metrics repository + overview/volume/heatmap endpoints

**Files:**
- Create: `garda_ai_backend/repositories/metrics.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/metrics.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_metrics_endpoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_metrics_endpoints.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_overview(client):
    r = await client.get("/api/v1/metrics/overview", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["total_transactions"] == 4
    assert body["flagged"] == 1     # status 'flagged'
    assert body["blocked"] == 1     # status 'blocked'
    assert body["total_amount"] == 20400000.0   # 15m+250k+5m+150k
    assert 0.0 <= body["fraud_rate"] <= 1.0


async def test_overview_requires_auth(client):
    r = await client.get("/api/v1/metrics/overview")
    assert r.status_code in (401, 403)


async def test_volume_buckets(client):
    r = await client.get("/api/v1/metrics/volume?range=24h", headers=_auth())
    assert r.status_code == 200
    series = r.json()["series"]
    assert isinstance(series, list)
    assert all({"bucket", "count", "flagged"} <= set(p) for p in series)


async def test_heatmap_shape(client):
    r = await client.get("/api/v1/metrics/heatmap", headers=_auth())
    assert r.status_code == 200
    cells = r.json()["cells"]
    # 7 days x 24 hours
    assert len(cells) == 7
    assert all(len(row) == 24 for row in cells)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics_endpoints.py -v`
Expected: FAIL (modules/router missing).

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/metrics.py`:
```python
from datetime import datetime

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Transaction, TransactionEvent


class MetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def overview(self, sim_now: datetime) -> dict:
        flagged = func.sum(case((TransactionEvent.status == "flagged", 1), else_=0))
        blocked = func.sum(case((TransactionEvent.status == "blocked", 1), else_=0))
        stmt = (
            select(
                func.count().label("total"),
                func.coalesce(flagged, 0).label("flagged"),
                func.coalesce(blocked, 0).label("blocked"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("amount"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= sim_now)
        )
        row = (await self._session.execute(stmt)).one()
        total = row.total or 0
        risky = (row.flagged or 0) + (row.blocked or 0)
        return {
            "total_transactions": total,
            "flagged": int(row.flagged or 0),
            "blocked": int(row.blocked or 0),
            "total_amount": float(row.amount or 0),
            "fraud_rate": (risky / total) if total else 0.0,
        }

    async def volume(self, sim_now: datetime) -> list[dict]:
        bucket = func.date_trunc("hour", TransactionEvent.surfaced_at).label("bucket")
        flagged = func.sum(
            case((TransactionEvent.status.in_(("flagged", "blocked")), 1), else_=0)
        )
        stmt = (
            select(bucket, func.count().label("count"), func.coalesce(flagged, 0).label("flagged"))
            .where(TransactionEvent.surfaced_at <= sim_now)
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"bucket": r.bucket.isoformat(), "count": int(r.count), "flagged": int(r.flagged)}
            for r in rows
        ]

    async def heatmap(self, sim_now: datetime) -> list[list[int]]:
        dow = cast(func.extract("dow", TransactionEvent.surfaced_at), Integer)
        hour = cast(func.extract("hour", TransactionEvent.surfaced_at), Integer)
        stmt = (
            select(dow.label("dow"), hour.label("hour"), func.count().label("count"))
            .where(TransactionEvent.surfaced_at <= sim_now)
            .group_by("dow", "hour")
        )
        rows = (await self._session.execute(stmt)).all()
        grid = [[0] * 24 for _ in range(7)]
        for r in rows:
            grid[int(r.dow)][int(r.hour)] = int(r.count)
        return grid
```

- [ ] **Step 4: Add view schemas**

Append to `garda_ai_backend/api/view_schemas.py`:
```python
class MetricsOverviewResponse(BaseModel):
    total_transactions: int
    flagged: int
    blocked: int
    total_amount: float
    fraud_rate: float


class VolumePoint(BaseModel):
    bucket: str
    count: int
    flagged: int


class VolumeResponse(BaseModel):
    series: list[VolumePoint]


class HeatmapResponse(BaseModel):
    cells: list[list[int]]
```
(Keep the existing imports; `BaseModel` is already imported.)

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/metrics.py`:
```python
from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import (
    HeatmapResponse,
    MetricsOverviewResponse,
    VolumeResponse,
)
from garda_ai_backend.repositories.metrics import MetricsRepository
from garda_ai_backend.repositories.sim import SimRepository

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


async def _sim_now(session) -> "object":
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    return sim_now


@router.get("/overview", response_model=MetricsOverviewResponse)
async def overview(
    session: SessionDep, redis: RedisDep, _: CurrentUserDep
) -> MetricsOverviewResponse:
    sim_now = await _sim_now(session)
    repo = MetricsRepository(session)
    data = await cached_json(
        redis, f"overview:{sim_now.isoformat()}", ttl=5, compute=lambda: repo.overview(sim_now)
    )
    return MetricsOverviewResponse(**data)


@router.get("/volume", response_model=VolumeResponse)
async def volume(
    session: SessionDep, redis: RedisDep, _: CurrentUserDep, range: str = "24h"
) -> VolumeResponse:
    sim_now = await _sim_now(session)
    repo = MetricsRepository(session)
    series = await cached_json(
        redis, f"volume:{range}:{sim_now.isoformat()}", ttl=5,
        compute=lambda: repo.volume(sim_now),
    )
    return VolumeResponse(series=series)


@router.get("/heatmap", response_model=HeatmapResponse)
async def heatmap(
    session: SessionDep, redis: RedisDep, _: CurrentUserDep
) -> HeatmapResponse:
    sim_now = await _sim_now(session)
    repo = MetricsRepository(session)
    cells = await cached_json(
        redis, f"heatmap:{sim_now.isoformat()}", ttl=5, compute=lambda: repo.heatmap(sim_now)
    )
    return HeatmapResponse(cells=cells)
```

- [ ] **Step 6: Wire the router into `main.py`**

Add the import and `app.include_router(metrics_router)` (alias the import as `metrics_router`).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_metrics_endpoints.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/metrics.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/metrics.py garda_ai_backend/main.py tests/test_metrics_endpoints.py
git commit -m "feat: metrics overview/volume/heatmap endpoints (cached)"
```

---

### Task 6: Fraud analytics endpoint

**Files:**
- Create: `garda_ai_backend/repositories/analytics.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/analytics.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_analytics_endpoint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_analytics_endpoint.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_fraud_analytics(client):
    r = await client.get("/api/v1/analytics/fraud", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    typ = {d["typology"]: d for d in body["distribution"]}
    assert "Fan-Out" in typ and "Smurfing" in typ
    assert typ["Fan-Out"]["count"] == 1
    m = body["detection"]
    # events with status flagged/blocked are the positive predictions; labels from is_laundering
    assert {"precision", "recall", "f1"} <= set(m)
    assert 0.0 <= m["precision"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_analytics_endpoint.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/analytics.py`:
```python
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Transaction, TransactionEvent


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def typology_distribution(self, sim_now: datetime) -> list[dict]:
        stmt = (
            select(
                TransactionEvent.typology.label("typology"),
                func.count().label("count"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("amount"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= sim_now)
            .where(TransactionEvent.typology.is_not(None))
            .group_by(TransactionEvent.typology)
            .order_by(func.count().desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"typology": r.typology, "count": int(r.count), "total_amount": float(r.amount)}
            for r in rows
        ]

    async def confusion_counts(self, sim_now: datetime) -> dict:
        """Predicted-positive = status in (flagged, blocked); actual = is_laundering."""
        predicted = TransactionEvent.status.in_(("flagged", "blocked"))
        actual = Transaction.is_laundering.is_(True)
        tp = func.sum(case((predicted & actual, 1), else_=0))
        fp = func.sum(case((predicted & ~actual, 1), else_=0))
        fn = func.sum(case((~predicted & actual, 1), else_=0))
        stmt = (
            select(func.coalesce(tp, 0), func.coalesce(fp, 0), func.coalesce(fn, 0))
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.surfaced_at <= sim_now)
        )
        tp_v, fp_v, fn_v = (await self._session.execute(stmt)).one()
        return {"tp": int(tp_v), "fp": int(fp_v), "fn": int(fn_v)}
```

- [ ] **Step 4: Add view schemas**

Append to `garda_ai_backend/api/view_schemas.py`:
```python
class TypologyCount(BaseModel):
    typology: str
    count: int
    total_amount: float


class DetectionMetrics(BaseModel):
    precision: float
    recall: float
    f1: float


class FraudAnalyticsResponse(BaseModel):
    distribution: list[TypologyCount]
    detection: DetectionMetrics
```

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/analytics.py`:
```python
from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import (
    DetectionMetrics,
    FraudAnalyticsResponse,
    TypologyCount,
)
from garda_ai_backend.repositories.analytics import AnalyticsRepository
from garda_ai_backend.repositories.sim import SimRepository

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _metrics(c: dict) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


@router.get("/fraud", response_model=FraudAnalyticsResponse)
async def fraud(
    session: SessionDep, redis: RedisDep, _: CurrentUserDep
) -> FraudAnalyticsResponse:
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    repo = AnalyticsRepository(session)

    async def compute() -> dict:
        return {
            "distribution": await repo.typology_distribution(sim_now),
            "detection": _metrics(await repo.confusion_counts(sim_now)),
        }

    data = await cached_json(redis, f"fraud:{sim_now.isoformat()}", ttl=5, compute=compute)
    return FraudAnalyticsResponse(
        distribution=[TypologyCount(**d) for d in data["distribution"]],
        detection=DetectionMetrics(**data["detection"]),
    )
```

- [ ] **Step 6: Wire into `main.py`** (import as `analytics_router`, include it).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_analytics_endpoint.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/analytics.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/analytics.py garda_ai_backend/main.py tests/test_analytics_endpoint.py
git commit -m "feat: fraud analytics endpoint (typology distribution + precision/recall/f1)"
```

---

### Task 7: Geographic provinces endpoint

**Files:**
- Create: `garda_ai_backend/repositories/geo.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/geo.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_geo_endpoint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_geo_endpoint.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_geo_provinces(client):
    r = await client.get("/api/v1/geo/provinces", headers=_auth())
    assert r.status_code == 200
    provinces = {p["name"]: p for p in r.json()["provinces"]}
    # the flagged/blocked event's from_account ACC1 -> entity E1 -> DKI Jakarta
    assert "DKI Jakarta" in provinces
    assert provinces["DKI Jakarta"]["fraud_count"] >= 1
    assert provinces["DKI Jakarta"]["risk_level"] in ("low", "medium", "high")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geo_endpoint.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/geo.py`:
```python
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Entity, Transaction, TransactionEvent


class GeoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def province_fraud_counts(self, sim_now: datetime) -> list[dict]:
        """Count flagged/blocked events by the sending account's entity province."""
        stmt = (
            select(Entity.province.label("province"), func.count().label("fraud_count"))
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .join(Account, Account.id == Transaction.from_account)
            .join(Entity, Entity.id == Account.entity_id)
            .where(TransactionEvent.surfaced_at <= sim_now)
            .where(TransactionEvent.status.in_(("flagged", "blocked")))
            .where(Entity.province.is_not(None))
            .group_by(Entity.province)
            .order_by(func.count().desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"province": r.province, "fraud_count": int(r.fraud_count)} for r in rows]
```

- [ ] **Step 4: Add view schemas**

Append:
```python
class ProvinceFraud(BaseModel):
    name: str
    fraud_count: int
    change_pct: float
    risk_level: str


class GeoResponse(BaseModel):
    provinces: list[ProvinceFraud]
```

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/geo.py`:
```python
from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.cache import cached_json
from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import GeoResponse, ProvinceFraud
from garda_ai_backend.repositories.geo import GeoRepository
from garda_ai_backend.repositories.sim import SimRepository


def _risk_level(count: int) -> str:
    if count >= 100:
        return "high"
    if count >= 20:
        return "medium"
    return "low"


router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.get("/provinces", response_model=GeoResponse)
async def provinces(session: SessionDep, redis: RedisDep, _: CurrentUserDep) -> GeoResponse:
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    repo = GeoRepository(session)
    data = await cached_json(
        redis, f"geo:{sim_now.isoformat()}", ttl=10,
        compute=lambda: repo.province_fraud_counts(sim_now),
    )
    return GeoResponse(
        provinces=[
            ProvinceFraud(
                name=d["province"], fraud_count=d["fraud_count"],
                change_pct=0.0, risk_level=_risk_level(d["fraud_count"]),
            )
            for d in data
        ]
    )
```
(`change_pct` is 0.0 for now — a prior-window delta is a Plan-3 enhancement once historical replay windows exist; documented, not faked.)

- [ ] **Step 6: Wire into `main.py`** (import as `geo_router`, include it).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_geo_endpoint.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/geo.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/geo.py garda_ai_backend/main.py tests/test_geo_endpoint.py
git commit -m "feat: geographic province fraud distribution endpoint"
```

---

### Task 8: Transactions live + detail endpoints

**Files:**
- Create: `garda_ai_backend/repositories/transactions.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/transactions.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_transactions_endpoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_transactions_endpoints.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_live_window_orders_desc_and_paginates(client):
    r = await client.get("/api/v1/transactions/live?limit=2", headers=_auth())
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    seqs = [i["seq"] for i in items]
    assert seqs == sorted(seqs, reverse=True)   # newest first
    assert {"seq", "bank", "amount", "fraud_score", "status"} <= set(items[0])


async def test_live_after_seq_backfill(client):
    r = await client.get("/api/v1/transactions/live?after_seq=2", headers=_auth())
    assert r.status_code == 200
    seqs = [i["seq"] for i in r.json()["items"]]
    assert all(s > 2 for s in seqs)


async def test_transaction_detail(client):
    r = await client.get("/api/v1/transactions/1", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert body["typology"] == "Fan-Out"
    assert body["status"] == "blocked"
    assert body["amount"] == 15000000.0


async def test_transaction_detail_404(client):
    r = await client.get("/api/v1/transactions/999", headers=_auth())
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_transactions_endpoints.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/transactions.py`:
```python
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Bank, Transaction, TransactionEvent


class TransactionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_window(
        self, sim_now: datetime, after_seq: int | None, limit: int
    ) -> list[dict]:
        stmt = (
            select(
                TransactionEvent.seq,
                TransactionEvent.transaction_id,
                TransactionEvent.fraud_score,
                TransactionEvent.typology,
                TransactionEvent.status,
                TransactionEvent.surfaced_at,
                Transaction.amount_paid,
                Transaction.payment_format,
                Bank.name.label("bank"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .join(Bank, Bank.id == Transaction.from_bank_id)
            .where(TransactionEvent.surfaced_at <= sim_now)
        )
        if after_seq is not None:
            stmt = stmt.where(TransactionEvent.seq > after_seq).order_by(TransactionEvent.seq.asc())
        else:
            stmt = stmt.order_by(TransactionEvent.seq.desc())
        stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "seq": r.seq, "transaction_id": r.transaction_id, "bank": r.bank,
                "type": r.payment_format, "amount": float(r.amount_paid),
                "fraud_score": float(r.fraud_score), "typology": r.typology,
                "status": r.status, "surfaced_at": r.surfaced_at.isoformat(),
            }
            for r in rows
        ]

    async def detail(self, transaction_id: int) -> dict | None:
        stmt = (
            select(
                Transaction.id, Transaction.amount_paid, Transaction.payment_currency,
                Transaction.payment_format, Transaction.is_laundering, Transaction.event_time,
                Bank.name.label("bank"),
                TransactionEvent.fraud_score, TransactionEvent.typology, TransactionEvent.status,
            )
            .select_from(Transaction)
            .join(Bank, Bank.id == Transaction.from_bank_id)
            .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
            .where(Transaction.id == transaction_id)
        )
        r = (await self._session.execute(stmt)).first()
        if r is None:
            return None
        return {
            "id": r.id, "bank": r.bank, "amount": float(r.amount_paid),
            "currency": r.payment_currency, "type": r.payment_format,
            "fraud_score": float(r.fraud_score), "typology": r.typology,
            "status": r.status, "is_laundering": r.is_laundering,
            "event_time": r.event_time.isoformat(),
        }
```

- [ ] **Step 4: Add view schemas**

Append:
```python
class LiveItem(BaseModel):
    seq: int
    transaction_id: int
    bank: str
    type: str
    amount: float
    fraud_score: float
    typology: str | None
    status: str
    surfaced_at: str


class LiveResponse(BaseModel):
    items: list[LiveItem]


class TransactionDetail(BaseModel):
    id: int
    bank: str
    amount: float
    currency: str
    type: str
    fraud_score: float
    typology: str | None
    status: str
    is_laundering: bool
    event_time: str
```

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/transactions.py`:
```python
from fastapi import APIRouter, HTTPException, Query, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep
from garda_ai_backend.api.view_schemas import LiveItem, LiveResponse, TransactionDetail
from garda_ai_backend.repositories.sim import SimRepository
from garda_ai_backend.repositories.transactions import TransactionsRepository

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("/live", response_model=LiveResponse)
async def live(
    session: SessionDep,
    _: CurrentUserDep,
    after_seq: int | None = None,
    limit: int = Query(default=50, le=200),
) -> LiveResponse:
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    rows = await TransactionsRepository(session).live_window(sim_now, after_seq, limit)
    return LiveResponse(items=[LiveItem(**r) for r in rows])


@router.get("/{transaction_id}", response_model=TransactionDetail)
async def detail(transaction_id: int, session: SessionDep, _: CurrentUserDep) -> TransactionDetail:
    row = await TransactionsRepository(session).detail(transaction_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return TransactionDetail(**row)
```
(Live is NOT cached — it must reflect the newest events immediately; it's the REST resync source for the WebSocket in Plan 2C.)

- [ ] **Step 6: Wire into `main.py`** (import as `transactions_router`, include it).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_transactions_endpoints.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/transactions.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/transactions.py garda_ai_backend/main.py tests/test_transactions_endpoints.py
git commit -m "feat: transactions live window (resync source) + detail endpoints"
```

---

### Task 9: User risk list + profile detail endpoints (with masking)

**Files:**
- Create: `garda_ai_backend/repositories/users_view.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/users_view.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_users_view_endpoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_users_view_endpoints.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth(role: str = "analyst") -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role=role, secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_user_risk_list_masks_name_for_analyst(client):
    r = await client.get("/api/v1/users/risk", headers=_auth("analyst"))
    assert r.status_code == 200
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "A**** S****"   # masked
    assert profiles["E1"]["risk_level"] == "High"


async def test_user_risk_list_unmasked_for_admin(client):
    r = await client.get("/api/v1/users/risk?unmasked=true", headers=_auth("admin"))
    assert r.status_code == 200
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "Ahmad Setiawan"   # unmasked for admin


async def test_user_risk_unmasked_denied_for_analyst(client):
    r = await client.get("/api/v1/users/risk?unmasked=true", headers=_auth("analyst"))
    # analyst cannot unmask: request is honored but name stays masked
    profiles = {p["entity_id"]: p for p in r.json()["profiles"]}
    assert profiles["E1"]["name"] == "A**** S****"


async def test_user_profile_detail(client):
    r = await client.get("/api/v1/users/E1/profile", headers=_auth("analyst"))
    assert r.status_code == 200
    body = r.json()
    assert body["entity_id"] == "E1"
    assert body["name"] == "A**** S****"
    assert body["total_transactions"] >= 1
    assert body["province"] == "DKI Jakarta"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_users_view_endpoints.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/users_view.py`:
```python
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Entity, Transaction, TransactionEvent


class UserRiskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def risk_list(self, sim_now: datetime, risk: str | None, limit: int) -> list[dict]:
        flagged = func.count().filter(TransactionEvent.status.in_(("flagged", "blocked")))
        stmt = (
            select(
                Entity.id.label("entity_id"),
                Entity.name.label("name"),
                Entity.province.label("province"),
                Account.risk_score.label("risk_score"),
                Account.risk_category.label("risk_category"),
                func.count(TransactionEvent.seq).label("total_txns"),
                flagged.label("flagged_txns"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("total_amount"),
            )
            .select_from(Entity)
            .join(Account, Account.entity_id == Entity.id)
            .join(Transaction, Transaction.from_account == Account.id, isouter=True)
            .join(
                TransactionEvent,
                (TransactionEvent.transaction_id == Transaction.id)
                & (TransactionEvent.surfaced_at <= sim_now),
                isouter=True,
            )
            .group_by(Entity.id, Entity.name, Entity.province, Account.risk_score, Account.risk_category)
        )
        if risk:
            stmt = stmt.where(Account.risk_category == risk)
        stmt = stmt.order_by(Account.risk_score.desc().nulls_last()).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [
            {
                "entity_id": r.entity_id, "name": r.name, "province": r.province,
                "risk_level": r.risk_category, "risk_score": float(r.risk_score or 0),
                "total_transactions": int(r.total_txns), "flagged_transactions": int(r.flagged_txns),
                "total_amount": float(r.total_amount),
            }
            for r in rows
        ]

    async def profile(self, sim_now: datetime, entity_id: str) -> dict | None:
        rows = await self.risk_list(sim_now, risk=None, limit=1000)
        for r in rows:
            if r["entity_id"] == entity_id:
                return r
        return None
```

- [ ] **Step 4: Add view schemas**

Append:
```python
class RiskProfile(BaseModel):
    entity_id: str
    name: str
    province: str | None
    risk_level: str | None
    risk_score: float
    total_transactions: int
    flagged_transactions: int
    total_amount: float


class UserRiskResponse(BaseModel):
    profiles: list[RiskProfile]
```

- [ ] **Step 5: Implement the router (with masking)**

`garda_ai_backend/api/users_view.py`:
```python
from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep
from garda_ai_backend.api.masking import mask_name
from garda_ai_backend.api.view_schemas import RiskProfile, UserRiskResponse
from garda_ai_backend.repositories.sim import SimRepository
from garda_ai_backend.repositories.users_view import UserRiskRepository

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _shape(row: dict, user, unmasked: bool) -> RiskProfile:
    allow_unmasked = unmasked and user.role == "admin"
    name = row["name"] if allow_unmasked else mask_name(row["name"])
    return RiskProfile(**{**row, "name": name})


@router.get("/risk", response_model=UserRiskResponse)
async def risk(
    session: SessionDep,
    user: CurrentUserDep,
    risk: str | None = None,
    unmasked: bool = False,
    limit: int = 100,
) -> UserRiskResponse:
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    rows = await UserRiskRepository(session).risk_list(sim_now, risk, limit)
    return UserRiskResponse(profiles=[_shape(r, user, unmasked) for r in rows])


@router.get("/{entity_id}/profile", response_model=RiskProfile)
async def profile(
    entity_id: str, session: SessionDep, user: CurrentUserDep, unmasked: bool = False
) -> RiskProfile:
    sim_now = await SimRepository(session).get_sim_now()
    if sim_now is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sim not initialized")
    row = await UserRiskRepository(session).profile(sim_now, entity_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return _shape(row, user, unmasked)
```

- [ ] **Step 6: Wire into `main.py`** (import as `users_view_router`, include it).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_users_view_endpoints.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/users_view.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/users_view.py garda_ai_backend/main.py tests/test_users_view_endpoints.py
git commit -m "feat: user risk list + profile endpoints with role-aware PII masking"
```

---

### Task 10: Alerts list + acknowledge endpoints

**Files:**
- Create: `garda_ai_backend/repositories/alerts.py`
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/alerts.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_alerts_endpoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_alerts_endpoints.py`:
```python
from datetime import UTC, datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth(role: str = "analyst") -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role=role, secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_list_alerts(client):
    r = await client.get("/api/v1/alerts", headers=_auth())
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["typology"] == "Fan-Out"
    assert alerts[0]["acknowledged"] is False


async def test_ack_alert(client):
    r = await client.post("/api/v1/alerts/1/ack", headers=_auth())
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
    # now filtered out of the active list
    r2 = await client.get("/api/v1/alerts?status=active", headers=_auth())
    assert all(a["id"] != 1 for a in r2.json()["alerts"])


async def test_ack_missing_alert_404(client):
    r = await client.post("/api/v1/alerts/999/ack", headers=_auth())
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_alerts_endpoints.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the repository**

`garda_ai_backend/repositories/alerts.py`:
```python
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Alert


class AlertsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(self, active_only: bool) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc())
        if active_only:
            stmt = stmt.where(Alert.acknowledged_at.is_(None))
        return list((await self._session.execute(stmt)).scalars().all())

    async def acknowledge(self, alert_id: int, user_id: int) -> Alert | None:
        alert = await self._session.get(Alert, alert_id)
        if alert is None:
            return None
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
        await self._session.flush()
        return alert
```

- [ ] **Step 4: Add view schemas**

Append:
```python
class AlertItem(BaseModel):
    id: int
    event_seq: int
    severity: str
    typology: str | None
    created_at: str
    acknowledged: bool


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
```

- [ ] **Step 5: Implement the router**

`garda_ai_backend/api/alerts.py`:
```python
from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep
from garda_ai_backend.api.view_schemas import AlertItem, AlertsResponse
from garda_ai_backend.repositories.alerts import AlertsRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _item(a) -> AlertItem:
    return AlertItem(
        id=a.id, event_seq=a.event_seq, severity=a.severity, typology=a.typology,
        created_at=a.created_at.isoformat(), acknowledged=a.acknowledged_at is not None,
    )


@router.get("", response_model=AlertsResponse)
async def list_alerts(session: SessionDep, _: CurrentUserDep, status: str = "all") -> AlertsResponse:
    rows = await AlertsRepository(session).list_alerts(active_only=(status == "active"))
    return AlertsResponse(alerts=[_item(a) for a in rows])


@router.post("/{alert_id}/ack", response_model=AlertItem)
async def ack(alert_id: int, session: SessionDep, user: CurrentUserDep) -> AlertItem:
    alert = await AlertsRepository(session).acknowledge(alert_id, user.id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    await session.commit()
    return _item(alert)
```

- [ ] **Step 6: Wire into `main.py`** (import as `alerts_view_router`, include it).

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_alerts_endpoints.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add garda_ai_backend/repositories/alerts.py garda_ai_backend/api/view_schemas.py garda_ai_backend/api/alerts.py garda_ai_backend/main.py tests/test_alerts_endpoints.py
git commit -m "feat: alerts list + acknowledge endpoints"
```

---

### Task 11: System health endpoint

**Files:**
- Modify: `garda_ai_backend/api/view_schemas.py`
- Create: `garda_ai_backend/api/system.py`
- Modify: `garda_ai_backend/main.py`
- Test: `tests/test_system_endpoint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_system_endpoint.py`:
```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.api import deps
from garda_ai_backend.redis_client import build_redis
from garda_ai_backend.security.tokens import create_access_token


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject='1', role='analyst', secret='test-secret', ttl_min=15)}"}


@pytest_asyncio.fixture
async def client(session, redis_url, seeded_dataset, monkeypatch):
    async def _override_session():
        yield session

    test_redis = build_redis(redis_url)
    await test_redis.flushdb()
    monkeypatch.setattr(deps, "get_redis", lambda: test_redis)
    from garda_ai_backend.main import app
    app.dependency_overrides[deps.get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await test_redis.aclose()


async def test_system_health(client):
    r = await client.get("/api/v1/system/health", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["db_ok"] is True
    assert body["redis_ok"] is True
    assert body["model_accuracy_simulated"] is True   # Phase 1: not a real model metric
    assert "events_surfaced" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_system_endpoint.py -v`
Expected: FAIL.

- [ ] **Step 3: Add view schema**

Append to `garda_ai_backend/api/view_schemas.py`:
```python
class SystemHealthResponse(BaseModel):
    db_ok: bool
    redis_ok: bool
    events_surfaced: int
    model_accuracy_simulated: bool
```

- [ ] **Step 4: Implement the router**

`garda_ai_backend/api/system.py`:
```python
from fastapi import APIRouter
from sqlalchemy import func, select, text

from garda_ai_backend.api.deps import CurrentUserDep, RedisDep, SessionDep
from garda_ai_backend.api.view_schemas import SystemHealthResponse
from garda_ai_backend.repositories.sim import SimRepository
from garda_ai_backend.schema import TransactionEvent

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

    sim_now = await SimRepository(session).get_sim_now()
    surfaced = 0
    if sim_now is not None:
        surfaced = (
            await session.execute(
                select(func.count())
                .select_from(TransactionEvent)
                .where(TransactionEvent.surfaced_at <= sim_now)
            )
        ).scalar_one()

    return SystemHealthResponse(
        db_ok=db_ok,
        redis_ok=redis_ok,
        events_surfaced=int(surfaced),
        model_accuracy_simulated=True,  # Phase 1 label-replay — not a trained-model metric
    )
```

- [ ] **Step 5: Wire into `main.py`** (import as `system_router`, include it).

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_system_endpoint.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add garda_ai_backend/api/view_schemas.py garda_ai_backend/api/system.py garda_ai_backend/main.py tests/test_system_endpoint.py
git commit -m "feat: system health endpoint (db/redis/events; phase-1 simulated flag)"
```

---

### Task 12: Full-suite gate + OpenAPI sanity + C4 docs

**Files:**
- Modify: `garda-ai-backend/docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Run the full suite + lint**

Run: `uv run pytest -v` (expect all green, ~39 prior + the new view tests) and `uv run ruff check garda_ai_backend/`.
Expected: all PASS / clean. Fix any failures before proceeding.

- [ ] **Step 2: Verify OpenAPI lists every new route**

Run a quick check that the app exposes the endpoints:
```bash
uv run python -c "from garda_ai_backend.main import app; print(sorted(r.path for r in app.routes))"
```
Expected: includes `/api/v1/metrics/overview`, `/api/v1/metrics/volume`, `/api/v1/metrics/heatmap`, `/api/v1/analytics/fraud`, `/api/v1/geo/provinces`, `/api/v1/transactions/live`, `/api/v1/transactions/{transaction_id}`, `/api/v1/users/risk`, `/api/v1/users/{entity_id}/profile`, `/api/v1/alerts`, `/api/v1/alerts/{alert_id}/ack`, `/api/v1/system/health`, `/api/v1/sim/state`, `/api/v1/sim/control`.

- [ ] **Step 3: Regenerate C4 docs**

Use the c4-architecture `c4-code` agent to add the new view modules (api/{masking,cache,view_schemas,metrics,analytics,geo,users_view,alerts,transactions,system,sim}, repositories/{sim,metrics,analytics,geo,users_view,alerts,transactions}) to `docs/c4/04-code.md`, then the `c4-component` agent to move "REST view-aggregation endpoints" and "PII masking" and "Aggregate caching" from planned to implemented in `docs/c4/03-component.md` (keep WebSocket relay as planned for Plan 2C).

- [ ] **Step 4: Commit**

```bash
git add docs/c4/
git commit -m "docs(c4): add view-endpoint components (metrics/analytics/geo/users/alerts/transactions/system/sim)"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-22-backend-api-design.md` §4):
- Live Monitor `/transactions/live?after_seq=&limit=` → Task 8. ✅
- Transaction detail `/transactions/{id}` → Task 8. ✅
- Metrics Overview `/metrics/overview` → Task 5. ✅
- Volume `/metrics/volume?range=` → Task 5. ✅
- Heatmap `/metrics/heatmap` (7×24) → Task 5. ✅
- Fraud Analytics `/analytics/fraud` (typology dist + precision/recall/F1 vs is_laundering) → Task 6. ✅
- Geographic `/geo/provinces` → Task 7. ✅
- User Risk list `/users/risk` → Task 9. ✅
- User profile `/users/{entity_id}/profile` → Task 9. ✅
- Alerts `/alerts` + `/alerts/{id}/ack` → Task 10. ✅
- System Health `/system/health` (with Phase-1 "simulated" flag) → Task 11. ✅
- Sim clock `/sim/state` + `/sim/control` (admin) → Task 4. ✅
- §4 filter `surfaced_at ≤ sim_now` → every repository. ✅
- §6 PII masking server-side, admin-unmask → Tasks 2, 9. ✅
- §7 caching (sim_now-bucket keys, short TTL), cursor-style live window, no raw-row dumps → Tasks 3,5,6,7,8. ✅
- §3 role gating (`require_role`) → all routers; admin-only `/sim/control` → Task 4. ✅
- C4 deliverable → Task 12. ✅
- **Deferred to Plan 2C (intentionally):** WebSocket relay `/ws/live`. **Deferred/simplified honestly:** `change_pct` province delta (0.0 until replay windows exist), system-health latency/throughput/WS-count fields (real values once the worker + WS exist — Plan 2C/3).

**Placeholder scan:** none — every endpoint has complete repo SQL, schema, router, and test. `change_pct=0.0` is explicitly documented as a deferred delta, not a hidden stub.

**Type consistency:** response models in `view_schemas.py` are consumed exactly by their routers; repo dict keys match the `BaseModel(**d)` field names in each task (`entity_id/name/province/risk_level/risk_score/total_transactions/flagged_transactions/total_amount`; `seq/transaction_id/bank/type/amount/fraud_score/typology/status/surfaced_at`; `tp/fp/fn`→precision/recall/f1). `SimRepository.get_sim_now()` is used identically across every view router. Masking (`mask_name`) is applied in Task 9 only where names are returned. All routers gate on `CurrentUserDep`; `/sim/control` adds `require_role("admin")`.
