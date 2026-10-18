# garda-ai-scoring Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the pipeline's scorer into a standalone, stateless `garda-ai-scoring` FastAPI service exposing a versioned, token-gated batch `POST /v1/score`, instrumented per the backend/python/observability plugin standards.

**Architecture:** Pure domain (`scoring/`, a faithful behavior-identical port) kept separate from the transport layer (`api/`). RED metrics + structured logs + correlation IDs. No DB, no Redis — the response is a pure function of the request.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, pydantic v2 + pydantic-settings, structlog, prometheus-client, pytest + httpx, ruff + mypy. Mirrors `garda-ai-backend` conventions.

**Spec:** `docs/superpowers/specs/2026-06-25-scoring-service-design.md`. **Anchor:** `garda-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`.

---

## File structure

```
garda-ai-scoring/
├── pyproject.toml                      # uv project + deps + ruff/mypy/pytest config
├── .python-version                     # 3.12
├── .env.example                        # GARDA_SCORING_TOKEN=...
├── .dockerignore
├── Dockerfile                          # own-context, two-phase uv sync
├── README.md
├── .github/workflows/ci.yml            # ruff + mypy + pytest
├── garda_ai_scoring/
│   ├── __init__.py
│   ├── config.py                       # pydantic-settings (fail-fast token)
│   ├── observability.py                # registry + RED metrics + structlog config
│   ├── scoring/                        # PURE DOMAIN — ported verbatim (imports renamed)
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── deterministic.py
│   │   ├── label_replay.py
│   │   └── factory.py                  # + optional kwargs to inject config (see Task 2)
│   └── api/                            # TRANSPORT
│       ├── __init__.py
│       ├── schemas.py                  # pydantic request/response models
│       ├── auth.py                     # bearer-token dependency
│       ├── middleware.py               # correlation-id + RED metrics
│       ├── routes.py                   # /v1/score router
│       └── app.py                      # FastAPI assembly + /healthz /readyz /metrics
└── tests/
    ├── conftest.py                     # client + token fixtures
    ├── test_types.py                   # ported
    ├── test_deterministic.py           # ported
    ├── test_label_replay.py            # ported
    ├── test_scoring_factory.py         # ported
    ├── test_config.py                  # new
    ├── test_auth.py                    # new
    ├── test_score_api.py               # new (+ determinism-parity lock)
    └── test_observability.py           # new
```

---

### Task 1: Scaffold the uv project

**Files:**
- Create: `pyproject.toml`, `.python-version`, `garda_ai_scoring/__init__.py`, `garda_ai_scoring/scoring/__init__.py`, `garda_ai_scoring/api/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "garda-ai-scoring"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "structlog>=24.4",
    "prometheus-client>=0.21",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create `.python-version`**

```
3.12
```

- [ ] **Step 3: Create the empty package markers**

Create empty files: `garda_ai_scoring/__init__.py`, `garda_ai_scoring/scoring/__init__.py`, `garda_ai_scoring/api/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4: Sync and verify the toolchain**

Run: `uv sync`
Expected: resolves and installs fastapi/pydantic/structlog/prometheus-client + dev tools; creates `uv.lock`.
Run: `uv run ruff check .`
Expected: `All checks passed!` (no code yet).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .python-version garda_ai_scoring tests
git commit -m "chore: scaffold garda-ai-scoring uv project"
```

---

### Task 2: Port the scoring domain (behavior-identical)

The domain is copied from `../garda-ai-pipeline/garda_ai_pipeline/scoring/`. Determinism MUST be preserved exactly (same seed/keys/thresholds).

**Files:**
- Create: `garda_ai_scoring/scoring/{types,deterministic,label_replay,factory}.py`
- Test: `tests/{test_types,test_deterministic,test_label_replay,test_scoring_factory}.py`

- [ ] **Step 1: Copy the four domain modules**

Copy each file from `../garda-ai-pipeline/garda_ai_pipeline/scoring/` to `garda_ai_scoring/scoring/` **unchanged except the internal import package**: replace every `garda_ai_pipeline.scoring` with `garda_ai_scoring.scoring`.

Files to copy verbatim (only that import rename): `types.py`, `deterministic.py`, `label_replay.py`.

- [ ] **Step 2: Copy `factory.py` and extend it to forward config**

Copy `factory.py`, rename the import, and widen `get_scorer` so the service can inject config (defaults are identical to today, so behavior is unchanged):

```python
from garda_ai_scoring.scoring.label_replay import LabelReplayScorer
from garda_ai_scoring.scoring.types import ScoringProvider


def get_scorer(
    name: str, *, seed: str = "garda", fn_rate: float = 0.05, fp_rate: float = 0.04
) -> ScoringProvider:
    """Select the scoring provider by config name."""
    if name == "label_replay":
        return LabelReplayScorer(seed=seed, fn_rate=fn_rate, fp_rate=fp_rate)
    if name == "ml":
        raise ValueError("scorer 'ml' (MLModelScorer) is not yet implemented (Phase 2)")
    raise ValueError(f"unknown scorer: {name!r}")
```

- [ ] **Step 3: Port the four domain test files**

Copy from `../garda-ai-pipeline/tests/`: `test_scoring_types.py` → `tests/test_types.py`, `test_deterministic.py`, `test_label_replay.py`, `test_scoring_factory.py`. In each, replace `garda_ai_pipeline.scoring` with `garda_ai_scoring.scoring`. Do not change assertions — they lock the ported behavior.

- [ ] **Step 4: Run the ported tests**

Run: `uv run pytest tests/test_types.py tests/test_deterministic.py tests/test_label_replay.py tests/test_scoring_factory.py -q`
Expected: all pass (the port is behavior-identical). If the factory test constructs `get_scorer("label_replay")` positionally it still passes (kwargs are optional).

- [ ] **Step 5: Type-check + commit**

Run: `uv run mypy garda_ai_scoring/scoring`
Expected: clean.

```bash
git add garda_ai_scoring/scoring tests/test_types.py tests/test_deterministic.py tests/test_label_replay.py tests/test_scoring_factory.py
git commit -m "feat: port scoring domain from pipeline (behavior-identical)"
```

---

### Task 3: Configuration (fail-fast token)

**Files:**
- Create: `garda_ai_scoring/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import pytest
from pydantic import ValidationError

from garda_ai_scoring.config import Settings


def test_settings_require_token(monkeypatch):
    monkeypatch.delenv("GARDA_SCORING_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", "s3cret")
    s = Settings()
    assert s.scoring_token == "s3cret"
    assert s.scorer == "label_replay"
    assert s.seed == "garda"
    assert s.fn_rate == 0.05
    assert s.fp_rate == 0.04
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: garda_ai_scoring.config`).

- [ ] **Step 3: Implement `garda_ai_scoring/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    # Required — the app must never expose /v1/score without a token (fail fast at startup).
    scoring_token: str

    scorer: str = "label_replay"
    seed: str = "garda"
    fn_rate: float = 0.05
    fp_rate: float = 0.04
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run to verify it passes + type-check**

Run: `uv run pytest tests/test_config.py -q` → PASS.
Run: `uv run mypy garda_ai_scoring/config.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_scoring/config.py tests/test_config.py
git commit -m "feat: pydantic-settings config with fail-fast scoring token"
```

---

### Task 4: Observability (metrics registry + logging)

**Files:**
- Create: `garda_ai_scoring/observability.py`

- [ ] **Step 1: Implement `garda_ai_scoring/observability.py`**

RED metrics with bounded labels (path *template*, method, status; result status has 3 values). Base-unit seconds histogram with buckets tuned for a fast scorer.

```python
import logging

import structlog
from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry()

REQUEST_COUNT = Counter(
    "garda_scoring_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status_code"],
    registry=REGISTRY,
)
REQUEST_DURATION = Histogram(
    "garda_scoring_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint", "method"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    registry=REGISTRY,
)
TRANSACTIONS_SCORED = Counter(
    "garda_scoring_transactions_scored_total",
    "Transactions scored, by result status",
    ["status"],  # bounded: approved | flagged | blocked
    registry=REGISTRY,
)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    )
```

- [ ] **Step 2: Type-check + commit**

Run: `uv run mypy garda_ai_scoring/observability.py` → clean.
(Observability is exercised via the API tests in Task 7; no standalone test here.)

```bash
git add garda_ai_scoring/observability.py
git commit -m "feat: observability — RED metrics registry + structlog config"
```

---

### Task 5: Bearer-token auth dependency

**Files:**
- Create: `garda_ai_scoring/api/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:
```python
import pytest
from fastapi import HTTPException

from garda_ai_scoring.api.auth import _verify


def test_verify_accepts_matching():
    _verify("Bearer s3cret", "s3cret")  # no raise


@pytest.mark.parametrize("header", [None, "s3cret", "Bearer wrong", "Basic s3cret"])
def test_verify_rejects(header):
    with pytest.raises(HTTPException) as exc:
        _verify(header, "s3cret")
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_auth.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `garda_ai_scoring/api/auth.py`**

Auth reads the token only from settings; never expose a request-controllable override (avoids a query-param auth bypass).

```python
import hmac

from fastapi import Header, HTTPException, status

from garda_ai_scoring.config import get_settings


def _verify(authorization: str | None, token: str) -> None:
    """Pure bearer-token check (unit-testable without the HTTP/env layer)."""
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.encode(), token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: validate the bearer token against the configured secret.

    Reads the token ONLY from settings — nothing request-controllable can override it.
    """
    _verify(authorization, get_settings().scoring_token)
```

- [ ] **Step 4: Run to verify it passes + type-check**

Run: `uv run pytest tests/test_auth.py -q` → PASS.
Run: `uv run mypy garda_ai_scoring/api/auth.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_scoring/api/auth.py tests/test_auth.py
git commit -m "feat: bearer-token auth dependency (constant-time compare)"
```

---

### Task 6: API schemas, middleware, routes, app assembly

**Files:**
- Create: `garda_ai_scoring/api/schemas.py`, `garda_ai_scoring/api/middleware.py`, `garda_ai_scoring/api/routes.py`, `garda_ai_scoring/api/app.py`

- [ ] **Step 1: Implement `garda_ai_scoring/api/schemas.py`**

```python
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

RiskCategory = Literal["Low", "Medium", "High"]
Status = Literal["approved", "flagged", "blocked"]


class ScoreRequestItem(BaseModel):
    transaction_id: int
    from_account: str
    to_account: str
    amount: Decimal
    payment_format: str
    is_laundering: bool
    event_time: datetime
    from_risk_category: RiskCategory | None = None


class ScoreRequest(BaseModel):
    transactions: list[ScoreRequestItem]


class ScoreResultItem(BaseModel):
    transaction_id: int
    fraud_score: float
    typology: str | None
    status: Status


class ScoreResponse(BaseModel):
    results: list[ScoreResultItem]
```

- [ ] **Step 2: Implement `garda_ai_scoring/api/middleware.py`**

Correlation-id binding + RED metrics, with a bounded path label (route template, or `"unmatched"`).

```python
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from garda_ai_scoring.observability import REQUEST_COUNT, REQUEST_DURATION

_logger = structlog.get_logger()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        cid = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or uuid.uuid4().hex
        )
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = time.perf_counter() - start
            structlog.contextvars.clear_contextvars()

        route = request.scope.get("route")
        endpoint = getattr(route, "path", None) or "unmatched"
        REQUEST_COUNT.labels(endpoint, request.method, str(response.status_code)).inc()
        REQUEST_DURATION.labels(endpoint, request.method).observe(elapsed)
        response.headers["X-Correlation-ID"] = cid
        _logger.info(
            "request",
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response
```

- [ ] **Step 3: Implement `garda_ai_scoring/api/routes.py`**

```python
from functools import lru_cache

from fastapi import APIRouter, Depends

from garda_ai_scoring.api.auth import require_token
from garda_ai_scoring.api.schemas import (
    ScoreRequest,
    ScoreResponse,
    ScoreResultItem,
)
from garda_ai_scoring.config import get_settings
from garda_ai_scoring.observability import TRANSACTIONS_SCORED
from garda_ai_scoring.scoring.factory import get_scorer
from garda_ai_scoring.scoring.types import ScoringContext, ScoringProvider, TxnInput

router = APIRouter(prefix="/v1", tags=["scoring"])


@lru_cache(maxsize=1)
def _provider() -> ScoringProvider:
    s = get_settings()
    return get_scorer(s.scorer, seed=s.seed, fn_rate=s.fn_rate, fp_rate=s.fp_rate)


@router.post("/score", response_model=ScoreResponse, dependencies=[Depends(require_token)])
async def score(body: ScoreRequest) -> ScoreResponse:
    provider = _provider()
    results: list[ScoreResultItem] = []
    for item in body.transactions:
        txn = TxnInput(
            transaction_id=item.transaction_id,
            from_account=item.from_account,
            to_account=item.to_account,
            amount=item.amount,
            payment_format=item.payment_format,
            is_laundering=item.is_laundering,
            event_time=item.event_time,
        )
        ctx = ScoringContext(from_risk_category=item.from_risk_category)
        r = await provider.score(txn, ctx)
        TRANSACTIONS_SCORED.labels(r.status).inc()
        results.append(
            ScoreResultItem(
                transaction_id=item.transaction_id,
                fraud_score=r.fraud_score,
                typology=r.typology,
                status=r.status,  # type: ignore[arg-type]
            )
        )
    return ScoreResponse(results=results)
```

- [ ] **Step 4: Implement `garda_ai_scoring/api/app.py`**

```python
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from garda_ai_scoring.api.middleware import ObservabilityMiddleware
from garda_ai_scoring.api.routes import router as scoring_router
from garda_ai_scoring.config import get_settings
from garda_ai_scoring.observability import REGISTRY, configure_logging

settings = get_settings()  # validates config (fails fast if GARDA_SCORING_TOKEN unset)
configure_logging(settings.log_level)

app = FastAPI(title="Garda AI Scoring", version="0.1.0")
app.add_middleware(ObservabilityMiddleware)
app.include_router(scoring_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    # Stateless: ready as soon as the process is up.
    return Response(content='{"status":"ready"}', media_type="application/json")


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 5: Type-check**

Run: `uv run mypy garda_ai_scoring` → clean. (The single `# type: ignore` on the middleware `call_next` param and the `status` Literal cast are acceptable and documented.)

- [ ] **Step 6: Commit**

```bash
git add garda_ai_scoring/api
git commit -m "feat: /v1/score API — schemas, RED middleware, routes, app assembly"
```

---

### Task 7: API + observability tests

**Files:**
- Create: `tests/conftest.py`, `tests/test_score_api.py`, `tests/test_observability.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def token() -> str:
    return "test-token"


@pytest.fixture
def client(token, monkeypatch):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", token)
    # Import inside the fixture so the app reads the patched env at import time.
    from garda_ai_scoring.config import get_settings

    get_settings.cache_clear()
    from garda_ai_scoring.api.app import app

    return TestClient(app)


@pytest.fixture
def auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Write `tests/test_score_api.py`**

```python
from garda_ai_scoring.scoring.factory import get_scorer
from garda_ai_scoring.scoring.types import ScoringContext, TxnInput

_TXN = {
    "transaction_id": 123,
    "from_account": "0009abc",
    "to_account": "0011def",
    "amount": "15000.00",
    "payment_format": "ACH",
    "is_laundering": True,
    "event_time": "2026-06-25T09:00:00Z",
}


def test_score_requires_token(client):
    r = client.post("/v1/score", json={"transactions": [_TXN]})
    assert r.status_code == 401


def test_score_batch_happy_path(client, auth):
    body = {"transactions": [_TXN, {**_TXN, "transaction_id": 124, "is_laundering": False}]}
    r = client.post("/v1/score", json=body, headers=auth)
    assert r.status_code == 200
    results = r.json()["results"]
    assert [x["transaction_id"] for x in results] == [123, 124]
    for x in results:
        assert 0.0 <= x["fraud_score"] <= 1.0
        assert x["status"] in {"approved", "flagged", "blocked"}


async def test_score_matches_domain_exactly(client, auth):
    # Determinism-parity lock: API result == calling the domain scorer directly.
    r = client.post("/v1/score", json={"transactions": [_TXN]}, headers=auth)
    got = r.json()["results"][0]
    scorer = get_scorer("label_replay")
    expected = await scorer.score(
        TxnInput(
            transaction_id=123,
            from_account="0009abc",
            to_account="0011def",
            amount=__import__("decimal").Decimal("15000.00"),
            payment_format="ACH",
            is_laundering=True,
            event_time=__import__("datetime").datetime.fromisoformat("2026-06-25T09:00:00+00:00"),
        ),
        ScoringContext(from_risk_category=None),
    )
    assert got["fraud_score"] == expected.fraud_score
    assert got["status"] == expected.status
    assert got["typology"] == expected.typology


def test_risk_category_changes_score(client, auth):
    low = client.post("/v1/score", json={"transactions": [{**_TXN, "from_risk_category": "Low"}]},
                      headers=auth).json()["results"][0]["fraud_score"]
    high = client.post("/v1/score", json={"transactions": [{**_TXN, "from_risk_category": "High"}]},
                       headers=auth).json()["results"][0]["fraud_score"]
    assert high >= low  # High adds a bump (capped at 0.99)


def test_empty_batch(client, auth):
    r = client.post("/v1/score", json={"transactions": []}, headers=auth)
    assert r.status_code == 200
    assert r.json() == {"results": []}


def test_malformed_body_422(client, auth):
    r = client.post("/v1/score", json={"transactions": [{"transaction_id": "nope"}]}, headers=auth)
    assert r.status_code == 422
```

- [ ] **Step 3: Write `tests/test_observability.py`**

```python
def test_health_and_ready(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_metrics_exposes_red_series(client, auth):
    client.post("/v1/score", json={"transactions": [{
        "transaction_id": 1, "from_account": "a", "to_account": "b",
        "amount": "1.00", "payment_format": "ACH", "is_laundering": False,
        "event_time": "2026-06-25T09:00:00Z"}]}, headers=auth)
    body = client.get("/metrics").text
    assert "garda_scoring_requests_total" in body
    assert "garda_scoring_request_duration_seconds" in body
    assert "garda_scoring_transactions_scored_total" in body


def test_correlation_id_echoed(client, auth):
    r = client.get("/healthz", headers={"X-Correlation-ID": "abc-123"})
    assert r.headers["X-Correlation-ID"] == "abc-123"
```

- [ ] **Step 4: Run the full suite + lint + type-check**

Run: `uv run pytest -q`
Expected: all pass (ported domain tests + config/auth + API + observability).
Run: `uv run ruff check .` → clean. Run: `uv run mypy garda_ai_scoring` → clean.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_score_api.py tests/test_observability.py
git commit -m "test: /v1/score API, determinism-parity lock, observability"
```

---

### Task 8: Packaging — Dockerfile, CI, README, env example

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `.env.example`, `README.md`, `.github/workflows/ci.yml`

- [ ] **Step 1: Create `Dockerfile`** (own-context, two-phase sync — same shape as the backend)

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_scoring ./garda_ai_scoring
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "garda_ai_scoring.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
.mypy_cache
.git
docs
tests
```

- [ ] **Step 3: Create `.env.example`**

```
GARDA_SCORING_TOKEN=change-me
GARDA_SCORER=label_replay
GARDA_LOG_LEVEL=INFO
```

- [ ] **Step 4: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: pip install uv
      - name: Sync
        run: uv sync --frozen
      - name: Lint
        run: uv run ruff check .
      - name: Type-check
        run: uv run mypy garda_ai_scoring
      - name: Test
        env:
          GARDA_SCORING_TOKEN: ci-token
        run: uv run pytest -q
```

- [ ] **Step 5: Create `README.md`**

```markdown
# garda-ai-scoring

Stateless fraud-scoring service for the Garda AI platform. Exposes a token-gated batch
`POST /v1/score` that returns `{fraud_score, typology, status}` per transaction. No database,
no Redis — the response is a pure function of the request.

## Run
```
uv sync
GARDA_SCORING_TOKEN=dev uv run uvicorn garda_ai_scoring.api.app:app --reload
```

## Test / lint / type-check
```
GARDA_SCORING_TOKEN=t uv run pytest -q
uv run ruff check .
uv run mypy garda_ai_scoring
```

Config (env, `GARDA_` prefix): `SCORING_TOKEN` (required), `SCORER` (`label_replay`|`ml`),
`SEED`, `FN_RATE`, `FP_RATE`, `LOG_LEVEL`. Ops: `/healthz`, `/readyz`, `/metrics`.
Contract + design: `docs/superpowers/specs/2026-06-25-scoring-service-design.md`.
```

- [ ] **Step 6: Verify the image builds**

Run: `docker build -t garda-scoring:test .`
Expected: build succeeds (two-phase `uv sync --frozen` with no lockfile-staleness complaint).
Then: `docker image rm garda-scoring:test || true`.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore .env.example README.md .github
git commit -m "build: Dockerfile (own context), CI (ruff+mypy+pytest), README, env example"
```

---

### Task 9: C4 documentation

**Files:**
- Create: `docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Generate C4 Component + Code docs**

Run the `c4-architecture` plugin's `c4-code` agent over `garda_ai_scoring/` and the `c4-component` agent to synthesize, writing into `docs/c4/` — matching the other repos' C4 layout. Document the `scoring/` domain vs `api/` transport boundary, the `/v1/score` contract, the RED metrics, and that the service is stateless (no DB/Redis).

- [ ] **Step 2: Commit**

```bash
git add docs/c4
git commit -m "docs: C4 component + code for garda-ai-scoring"
```

---

## Self-Review

**Spec coverage:**
- Faithful port (types/deterministic/label_replay/factory) → Task 2 (+ determinism-parity lock in Task 7). ✅
- Batch `POST /v1/score`, versioned, `approved|flagged|blocked`, optional `from_risk_category` → Tasks 6–7. ✅
- Bearer-token auth, fail-fast if unset → Tasks 3 (required field) + 5 (dependency) + app import (Task 6). ✅
- Ops parity `/healthz` `/readyz` `/metrics` → Task 6. ✅
- Observability: structlog JSON, correlation-id middleware, RED metrics with bounded labels + `prefix_name_unit`, observability tests → Tasks 4, 6, 7. ✅
- Config (pydantic-settings, `GARDA_` prefix, scorer/seed/rates) → Task 3. ✅
- Packaging: own-context Dockerfile, `.dockerignore`, `.env.example`, CI (ruff+mypy+pytest) → Task 8. ✅
- Type-safety (mypy strict) across all tasks; API-design (versioned URL, status codes, error shape) in Tasks 5–6. ✅
- C4 docs → Task 9. ✅
- MLModelScorer stays a guard (ported factory `ml` branch); deploy pipeline deferred to Phase 6. ✅ (out of scope, honored)

**Placeholder scan:** none — every code step has full content; ported files reference exact source paths + the single import-rename transform.

**Type consistency:** `TxnInput`/`ScoringContext`/`ScoringResult`/`ScoringProvider` used in `routes.py` match the ported `scoring/types.py`. `get_scorer(name, *, seed, fn_rate, fp_rate)` (Task 2) matches the call in `routes.py::_provider` (Task 6). Request/response models (`ScoreRequest`/`ScoreResponse`) match the router signature and the tests. Metric objects (`REQUEST_COUNT`/`REQUEST_DURATION`/`TRANSACTIONS_SCORED`) defined in Task 4 are imported unchanged in Tasks 6. `get_settings` (Task 3) `.cache_clear()` used by the test fixture (Task 7).
