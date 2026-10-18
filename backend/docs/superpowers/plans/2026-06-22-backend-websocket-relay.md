# Backend WebSocket Relay Implementation Plan (Plan 2C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the authenticated live WebSocket relay `WS /api/v1/ws/live` to `grafin-ai-backend`. It subscribes to the Redis channel the pipeline worker (Plan 3) publishes scored events to and fans each event out to connected dashboard clients, with per-connection backpressure (drop-to-latest + resync hint). Clients backfill gaps via the already-built uncached `GET /api/v1/transactions/live?after_seq=`.

**Architecture:** A shared channel constant (`realtime/channels.py`) is the single source of truth both backend and pipeline use. WS auth is a pure helper (`api/ws_auth.py`) reusing the existing JWT `decode_token` — browsers can't set the `Authorization` header on a WS handshake, so the access token arrives as a `?token=` query param. The relay handler authenticates, accepts, subscribes to Redis pub/sub, and runs a bounded-queue reader/writer pair so a slow client gets dropped-to-latest with a `{"type":"resync"}` hint rather than blocking the server.

**Tech Stack:** FastAPI/Starlette WebSockets, redis.asyncio pub/sub, PyJWT (existing), pytest + Starlette TestClient + testcontainers Redis.

---

## File structure

```
grafin_ai_backend/
├── realtime/
│   ├── __init__.py            # CREATE (empty)
│   └── channels.py            # CREATE: LIVE_EVENTS_CHANNEL constant (shared with pipeline)
├── api/
│   ├── ws_auth.py             # CREATE: authenticate_ws_token(token, secret) -> CurrentUser | None
│   └── ws.py                  # CREATE: WS /api/v1/ws/live relay
└── main.py                    # MODIFY: include ws router
tests/
├── test_ws_auth.py
└── test_ws_live.py
```

---

### Task 1: Shared channel constant + WS token auth

**Files:**
- Create: `grafin_ai_backend/realtime/__init__.py` (empty), `grafin_ai_backend/realtime/channels.py`
- Create: `grafin_ai_backend/api/ws_auth.py`
- Test: `tests/test_ws_auth.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ws_auth.py`:
```python
from grafin_ai_backend.api.ws_auth import authenticate_ws_token
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.security.tokens import create_access_token, create_refresh_token

S = "test-secret"


def test_channel_constant_is_stable():
    assert LIVE_EVENTS_CHANNEL == "grafin:events:live"


def test_valid_access_token():
    t = create_access_token(subject="3", role="admin", secret=S, ttl_min=15)
    u = authenticate_ws_token(t, S)
    assert u is not None
    assert u.id == 3
    assert u.role == "admin"


def test_rejects_empty():
    assert authenticate_ws_token("", S) is None


def test_rejects_garbage():
    assert authenticate_ws_token("not-a-jwt", S) is None


def test_rejects_wrong_secret():
    t = create_access_token(subject="3", role="admin", secret=S, ttl_min=15)
    assert authenticate_ws_token(t, "other-secret") is None


def test_rejects_refresh_token():
    t = create_refresh_token(subject="3", secret=S, ttl_days=7)
    assert authenticate_ws_token(t, S) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ws_auth.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`grafin_ai_backend/realtime/__init__.py`:
```python
```
(empty file)

`grafin_ai_backend/realtime/channels.py`:
```python
# Redis pub/sub channel the pipeline replay worker publishes scored events to and
# the backend WebSocket relay subscribes to. Shared constant — keep both in sync.
LIVE_EVENTS_CHANNEL = "grafin:events:live"
```

`grafin_ai_backend/api/ws_auth.py`:
```python
from grafin_ai_backend.api.deps import CurrentUser
from grafin_ai_backend.security.tokens import InvalidToken, decode_token


def authenticate_ws_token(token: str, secret: str) -> CurrentUser | None:
    """Validate a WS access token (passed as ?token=). Returns the user or None."""
    if not token:
        return None
    try:
        claims = decode_token(token, secret=secret)
    except InvalidToken:
        return None
    if claims.get("type") != "access":
        return None
    return CurrentUser(id=int(claims["sub"]), role=claims["role"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ws_auth.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add grafin_ai_backend/realtime/ grafin_ai_backend/api/ws_auth.py tests/test_ws_auth.py
git commit -m "feat: shared live-events channel constant + WS token auth helper"
```

---

### Task 2: WebSocket relay handler

**Files:**
- Create: `grafin_ai_backend/api/ws.py`
- Modify: `grafin_ai_backend/main.py`
- Test: `tests/test_ws_live.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ws_live.py`:
```python
import json

import pytest
import redis as sync_redis
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from grafin_ai_backend.api import deps
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL
from grafin_ai_backend.redis_client import build_redis
from grafin_ai_backend.security.tokens import create_access_token


def _app(redis_url):
    from grafin_ai_backend.main import app
    app.dependency_overrides[deps.get_redis_dep] = lambda: build_redis(redis_url)
    return app


def test_ws_rejects_bad_token(redis_url):
    app = _app(redis_url)
    try:
        with TestClient(app) as tc:  # noqa: SIM117
            with pytest.raises(WebSocketDisconnect):
                with tc.websocket_connect("/api/v1/ws/live?token=bad") as ws:
                    ws.receive_json()
    finally:
        app.dependency_overrides.clear()


def test_ws_relays_published_event(redis_url):
    app = _app(redis_url)
    token = create_access_token(subject="1", role="analyst", secret="test-secret", ttl_min=15)
    try:
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/ws/live?token={token}") as ws:
                assert ws.receive_json()["type"] == "connected"
                pub = sync_redis.from_url(redis_url)
                event = {"seq": 5, "bank": "Bank BRI", "status": "blocked", "fraud_score": 0.95}
                pub.publish(LIVE_EVENTS_CHANNEL, json.dumps(event))
                msg = ws.receive_json()
                assert msg["seq"] == 5
                assert msg["status"] == "blocked"
                pub.close()
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ws_live.py -v`
Expected: FAIL (route missing → handshake rejected / 404).

- [ ] **Step 3: Implement the relay**

`grafin_ai_backend/api/ws.py`:
```python
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from grafin_ai_backend.api.deps import RedisDep, SettingsDep
from grafin_ai_backend.api.ws_auth import authenticate_ws_token
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL

router = APIRouter(tags=["ws"])

_QUEUE_MAX = 100
_RESYNC = json.dumps({"type": "resync"})


@router.websocket("/api/v1/ws/live")
async def ws_live(websocket: WebSocket, redis: RedisDep, settings: SettingsDep) -> None:
    user = authenticate_ws_token(
        websocket.query_params.get("token", ""), settings.jwt_secret
    )
    if user is None:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(LIVE_EVENTS_CHANNEL)
    await websocket.send_json({"type": "connected"})

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX)

    async def reader() -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if queue.full():
                    # slow client: drop the backlog and tell it to resync via REST
                    while not queue.empty():
                        queue.get_nowait()
                    await queue.put(_RESYNC)
                await queue.put(message["data"])
        except asyncio.CancelledError:
            raise

    async def writer() -> None:
        try:
            while True:
                await websocket.send_text(await queue.get())
        except asyncio.CancelledError:
            raise

    reader_task = asyncio.create_task(reader())
    writer_task = asyncio.create_task(writer())
    try:
        # block on inbound frames purely to detect client disconnect
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        await asyncio.gather(reader_task, writer_task, return_exceptions=True)
        await pubsub.unsubscribe(LIVE_EVENTS_CHANNEL)
        await pubsub.aclose()
```

- [ ] **Step 4: Wire into `main.py`**

Add with the other imports: `from grafin_ai_backend.api.ws import router as ws_router` and, after the other `include_router` calls, `app.include_router(ws_router)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_ws_live.py -v`
Expected: PASS (2 tests). Then full suite `uv run pytest -v` and `uv run ruff check grafin_ai_backend/`.

- [ ] **Step 6: Commit**

```bash
git add grafin_ai_backend/api/ws.py grafin_ai_backend/main.py tests/test_ws_live.py
git commit -m "feat: authenticated live WebSocket relay with backpressure"
```

---

### Task 3: C4 docs — WebSocket relay implemented

**Files:**
- Modify: `grafin-ai-backend/docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Regenerate**

Use the c4-architecture `c4-code` agent to add `realtime/channels.py`, `api/ws_auth.py`, `api/ws.py` to `docs/c4/04-code.md`; then the `c4-component` agent to move **WebSocket Relay** from planned to implemented in `docs/c4/03-component.md` (now the backend has no remaining "planned" API components for Plan 2). Note the shared `LIVE_EVENTS_CHANNEL` couples backend ↔ pipeline.

- [ ] **Step 2: Commit**

```bash
git add docs/c4/
git commit -m "docs(c4): WebSocket relay component implemented"
```

---

## Self-Review

**Spec coverage** (backend-api-design.md §5):
- `WS /api/v1/ws/live` authenticated (JWT) → Tasks 1–2. ✅
- Subscribes to the Redis channel the worker publishes to → `LIVE_EVENTS_CHANNEL`, Task 2. ✅
- Per-connection backpressure: bounded queue, drop-to-latest + resync hint → Task 2 reader/writer. ✅
- Client backfills via `GET /transactions/live?after_seq=` (built in Plan 2B; the relay forwards raw event JSON the worker publishes — the worker stamps the full message shape `{seq, transaction_id, bank, type, amount, fraud_score, typology, status, surfaced_at, sim_now}` in Plan 3). ✅
- C4 deliverable → Task 3. ✅
- **Dependency on Plan 3:** until the pipeline worker exists, nothing publishes to the channel in production; the relay is exercised in tests by publishing directly. The message *content* is owned by the worker — the relay is content-agnostic (forwards the published string verbatim), so no contract drift.

**Placeholder scan:** none — relay, auth, and channel are complete. The `?token=` query-param auth is a deliberate choice (WS handshakes can't carry `Authorization`), documented in the architecture note.

**Type consistency:** `authenticate_ws_token(token, secret) -> CurrentUser | None` returns the same `CurrentUser` dataclass used by the HTTP deps; `LIVE_EVENTS_CHANNEL` is referenced identically in the relay and tests (and will be imported by the Plan-3 worker). `RedisDep`/`SettingsDep` match the existing deps; the test overrides `get_redis_dep` exactly as the HTTP tests do.
