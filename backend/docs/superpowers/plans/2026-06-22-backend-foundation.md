# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `garda-ai-backend` service skeleton with the canonical PostgreSQL schema, Alembic migrations, typed config, async DB access, and health/metrics endpoints — the foundation every other repo depends on.

**Architecture:** FastAPI (async) layered as `api/ → services/ → repositories/ → schema/`. SQLAlchemy 2.0 async models in `schema/` are the single source of truth for the data model; Alembic creates the schema at init. This plan delivers the runnable skeleton + schema only; auth and view endpoints come in Plan 2.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2.0 (async) + asyncpg, Alembic, Pydantic v2 + pydantic-settings, prometheus-client, structlog, pytest + testcontainers.

---

## File structure (created by this plan)

```
garda-ai-backend/
├── pyproject.toml                      # uv project + deps + tool config
├── .env.example                        # documented required env vars
├── garda_ai_backend/
│   ├── __init__.py
│   ├── config.py                       # pydantic-settings Settings
│   ├── db.py                           # async engine + session factory
│   ├── observability.py                # structlog + prometheus setup
│   ├── main.py                         # FastAPI app, health/metrics routes
│   └── schema/
│       ├── __init__.py                 # exports Base + all models
│       ├── base.py                     # DeclarativeBase
│       ├── reference.py                # banks, entities, accounts
│       ├── transactions.py             # transactions, transaction_events
│       ├── alerts.py                   # alerts
│       ├── users.py                    # users
│       └── sim.py                      # sim_state
├── migrations/                         # Alembic (env.py + versions/)
│   ├── env.py
│   └── versions/
└── tests/
    ├── conftest.py                     # testcontainers Postgres fixture
    ├── test_health.py
    └── test_schema.py
```

Each `schema/*.py` groups tables that change together. `db.py`, `config.py`, `observability.py` each own one concern.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `garda_ai_backend/__init__.py`
- Create: `.env.example`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "garda-ai-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "prometheus-client>=0.21",
    "structlog>=24.4",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "testcontainers[postgres]>=4.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create package marker**

`garda_ai_backend/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `.env.example`**

```bash
# Database
GARDA_DATABASE_URL=postgresql+asyncpg://garda:garda@localhost:5432/garda
# App
GARDA_ENV=development
GARDA_LOG_LEVEL=INFO
```

- [ ] **Step 4: Install deps and verify**

Run: `uv sync`
Expected: resolves and creates `.venv` with no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml garda_ai_backend/__init__.py .env.example uv.lock
git commit -m "chore: scaffold garda-ai-backend project"
```

---

### Task 2: Typed configuration

**Files:**
- Create: `garda_ai_backend/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from garda_ai_backend.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("GARDA_ENV", "production")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.env == "production"
    assert s.log_level == "INFO"  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: garda_ai_backend.config`.

- [ ] **Step 3: Write minimal implementation**

`garda_ai_backend/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    database_url: str
    env: str = "development"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_backend/config.py tests/test_config.py
git commit -m "feat: typed settings via pydantic-settings"
```

---

### Task 3: Schema base + reference tables

**Files:**
- Create: `garda_ai_backend/schema/base.py`
- Create: `garda_ai_backend/schema/reference.py`
- Create: `garda_ai_backend/schema/__init__.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_schema.py`:
```python
from garda_ai_backend.schema import Base, Bank, Entity, Account


def test_reference_tables_registered():
    tables = Base.metadata.tables
    assert "banks" in tables
    assert "entities" in tables
    assert "accounts" in tables
    # accounts links to bank + entity
    cols = {c.name for c in tables["accounts"].columns}
    assert {"id", "bank_id", "entity_id", "risk_score", "risk_category"} <= cols
    # entity carries seeded province
    assert "province" in {c.name for c in tables["entities"].columns}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: garda_ai_backend.schema`.

- [ ] **Step 3: Write the base**

`garda_ai_backend/schema/base.py`:
```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Write the reference models**

`garda_ai_backend/schema/reference.py`:
```python
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from garda_ai_backend.schema.base import Base


class Bank(Base):
    __tablename__ = "banks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    province: Mapped[str | None] = mapped_column(String, index=True)  # seeded enrichment


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric)
    risk_category: Mapped[str | None] = mapped_column(String, index=True)

    bank: Mapped["Bank"] = relationship()
    entity: Mapped["Entity"] = relationship()
```

- [ ] **Step 5: Write the package exporter**

`garda_ai_backend/schema/__init__.py`:
```python
from garda_ai_backend.schema.base import Base
from garda_ai_backend.schema.reference import Account, Bank, Entity

__all__ = ["Base", "Bank", "Entity", "Account"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add garda_ai_backend/schema/ tests/test_schema.py
git commit -m "feat: schema base + reference tables (banks, entities, accounts)"
```

---

### Task 4: Transaction + event tables

**Files:**
- Create: `garda_ai_backend/schema/transactions.py`
- Modify: `garda_ai_backend/schema/__init__.py`
- Test: `tests/test_schema.py` (add cases)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_schema.py`:
```python
def test_transaction_tables_registered():
    from garda_ai_backend.schema import Transaction, TransactionEvent
    tables = Base.metadata.tables
    txn_cols = {c.name for c in tables["transactions"].columns}
    assert {"id", "event_time", "from_account", "to_account",
            "amount_paid", "is_laundering"} <= txn_cols
    ev_cols = {c.name for c in tables["transaction_events"].columns}
    assert {"seq", "transaction_id", "surfaced_at",
            "fraud_score", "typology", "status"} <= ev_cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py::test_transaction_tables_registered -v`
Expected: FAIL — `ImportError: cannot import name 'Transaction'`.

- [ ] **Step 3: Write the models**

`garda_ai_backend/schema/transactions.py`:
```python
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    from_bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"))
    from_account: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    to_bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"))
    to_account: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_paid: Mapped[float] = mapped_column(Numeric)
    payment_currency: Mapped[str] = mapped_column(String)
    amount_received: Mapped[float] = mapped_column(Numeric)
    receiving_currency: Mapped[str] = mapped_column(String)
    payment_format: Mapped[str] = mapped_column(String)
    is_laundering: Mapped[bool] = mapped_column(Boolean, index=True)


class TransactionEvent(Base):
    __tablename__ = "transaction_events"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    surfaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fraud_score: Mapped[float] = mapped_column(Numeric)
    typology: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)  # approved | flagged | blocked
```

- [ ] **Step 4: Export the new models**

Update `garda_ai_backend/schema/__init__.py`:
```python
from garda_ai_backend.schema.base import Base
from garda_ai_backend.schema.reference import Account, Bank, Entity
from garda_ai_backend.schema.transactions import Transaction, TransactionEvent

__all__ = ["Base", "Bank", "Entity", "Account", "Transaction", "TransactionEvent"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (both schema tests).

- [ ] **Step 6: Commit**

```bash
git add garda_ai_backend/schema/transactions.py garda_ai_backend/schema/__init__.py tests/test_schema.py
git commit -m "feat: transactions + transaction_events tables"
```

---

### Task 5: Alerts, users, sim_state tables

**Files:**
- Create: `garda_ai_backend/schema/alerts.py`
- Create: `garda_ai_backend/schema/users.py`
- Create: `garda_ai_backend/schema/sim.py`
- Modify: `garda_ai_backend/schema/__init__.py`
- Test: `tests/test_schema.py` (add case)

- [ ] **Step 1: Add failing test**

Append to `tests/test_schema.py`:
```python
def test_ops_tables_registered():
    from garda_ai_backend.schema import Alert, User, SimState
    tables = Base.metadata.tables
    assert {"id", "event_seq", "severity", "typology"} <= {c.name for c in tables["alerts"].columns}
    assert {"id", "email", "password_hash", "role"} <= {c.name for c in tables["users"].columns}
    assert {"id", "sim_now", "speed", "running"} <= {c.name for c in tables["sim_state"].columns}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py::test_ops_tables_registered -v`
Expected: FAIL — `ImportError: cannot import name 'Alert'`.

- [ ] **Step 3: Write the models**

`garda_ai_backend/schema/alerts.py`:
```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_seq: Mapped[int] = mapped_column(ForeignKey("transaction_events.seq"), index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    typology: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`garda_ai_backend/schema/users.py`:
```python
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)  # analyst | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

`garda_ai_backend/schema/sim.py`:
```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class SimState(Base):
    __tablename__ = "sim_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sim_now: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    speed: Mapped[float] = mapped_column(Numeric, default=1.0)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 4: Export the new models**

Update `garda_ai_backend/schema/__init__.py`:
```python
from garda_ai_backend.schema.base import Base
from garda_ai_backend.schema.reference import Account, Bank, Entity
from garda_ai_backend.schema.transactions import Transaction, TransactionEvent
from garda_ai_backend.schema.alerts import Alert
from garda_ai_backend.schema.users import User
from garda_ai_backend.schema.sim import SimState

__all__ = [
    "Base", "Bank", "Entity", "Account", "Transaction",
    "TransactionEvent", "Alert", "User", "SimState",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (all schema tests).

- [ ] **Step 6: Commit**

```bash
git add garda_ai_backend/schema/ tests/test_schema.py
git commit -m "feat: alerts, users, sim_state tables"
```

---

### Task 6: Async DB engine + session

**Files:**
- Create: `garda_ai_backend/db.py`
- Test: `tests/conftest.py`, `tests/test_db.py`

- [ ] **Step 1: Write the testcontainers fixture**

`tests/conftest.py`:
```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from garda_ai_backend.schema import Base


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture
async def session(pg_url):
    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()
```

- [ ] **Step 2: Write the failing test**

`tests/test_db.py`:
```python
from sqlalchemy import text

from garda_ai_backend.db import build_engine


async def test_build_engine_connects(pg_url):
    engine = build_engine(pg_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await engine.dispose()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: garda_ai_backend.db`.

- [ ] **Step 4: Write the implementation**

`garda_ai_backend/db.py`:
```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from garda_ai_backend.config import get_settings


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=5)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _maker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = build_engine(get_settings().database_url)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _maker()() as session:
        yield session
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add garda_ai_backend/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: async engine + session factory with testcontainers fixture"
```

---

### Task 7: Alembic migrations (schema at init)

**Files:**
- Create: `migrations/env.py`
- Create: `alembic.ini`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Initialize Alembic**

Run: `uv run alembic init -t async migrations`
Then edit `alembic.ini` line `sqlalchemy.url =` to be empty (URL comes from env).

- [ ] **Step 2: Point env.py at our metadata**

Replace the metadata + URL section of `migrations/env.py` so it reads:
```python
from garda_ai_backend.config import get_settings
from garda_ai_backend.schema import Base

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url
```
And in both `run_migrations_offline()` and `run_migrations_online()`, use `get_url()` for the connection URL instead of `config.get_main_option("sqlalchemy.url")`.

- [ ] **Step 3: Generate the initial migration**

Run: `GARDA_DATABASE_URL=postgresql+asyncpg://garda:garda@localhost:5432/garda uv run alembic revision --autogenerate -m "initial schema"`
Expected: a file under `migrations/versions/` creating all 9 tables. (Requires a reachable Postgres; use a local docker `postgres:16` or skip autogenerate and hand-write if unavailable.)

- [ ] **Step 4: Write the failing test**

`tests/test_migrations.py`:
```python
from alembic.config import Config
from alembic.script import ScriptDirectory

from garda_ai_backend.schema import Base


def test_migration_covers_all_tables():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 1, "no migration generated"
    # every model table name should appear in the head migration source
    head_src = (script.get_revision(script.get_current_head()).module.__file__)
    text = open(head_src).read()
    for table in Base.metadata.tables:
        assert table in text, f"{table} missing from migration"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: PASS (fails first if Step 3 was skipped — generate the migration to make it pass).

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations/ tests/test_migrations.py
git commit -m "feat: alembic migrations create canonical schema at init"
```

---

### Task 8: Observability (structlog + Prometheus)

**Files:**
- Create: `garda_ai_backend/observability.py`
- Test: `tests/test_observability.py`

- [ ] **Step 1: Write the failing test**

`tests/test_observability.py`:
```python
from garda_ai_backend.observability import configure_logging, REGISTRY, REQUEST_COUNT


def test_logging_and_metrics_configured():
    configure_logging("INFO")
    REQUEST_COUNT.labels(method="GET", path="/healthz", status="200").inc()
    # metric is registered and increments
    value = REGISTRY.get_sample_value(
        "garda_http_requests_total",
        {"method": "GET", "path": "/healthz", "status": "200"},
    )
    assert value == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability.py -v`
Expected: FAIL — `ModuleNotFoundError: garda_ai_backend.observability`.

- [ ] **Step 3: Write the implementation**

`garda_ai_backend/observability.py`:
```python
import logging

import structlog
from prometheus_client import CollectorRegistry, Counter

REGISTRY = CollectorRegistry()
REQUEST_COUNT = Counter(
    "garda_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_observability.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_backend/observability.py tests/test_observability.py
git commit -m "feat: structlog JSON logging + prometheus request counter"
```

---

### Task 9: FastAPI app + health/readiness/metrics endpoints

**Files:**
- Create: `garda_ai_backend/main.py`
- Test: `tests/test_health.py`

- [ ] **Step 1: Write the failing test**

`tests/test_health.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from garda_ai_backend.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_metrics_exposed(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "garda_http_requests_total" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: garda_ai_backend.main`.

- [ ] **Step 3: Write the implementation**

`garda_ai_backend/main.py`:
```python
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from garda_ai_backend.config import get_settings
from garda_ai_backend.db import _maker
from garda_ai_backend.observability import REGISTRY, configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Garda AI Backend", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Response:
    try:
        async with _maker()() as session:
            await session.execute(text("SELECT 1"))
        return Response(content='{"status":"ready"}', media_type="application/json")
    except Exception:
        return Response(
            content='{"status":"not-ready"}', media_type="application/json", status_code=503
        )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS (both tests). `/healthz` and `/metrics` need no DB; `/readyz` is covered in Plan 2 integration.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add garda_ai_backend/main.py tests/test_health.py
git commit -m "feat: FastAPI app with health, readiness, metrics endpoints"
```

---

### Task 10: C4 Component + Code documentation (deliverable)

**Files:**
- Create: `garda-ai-backend/docs/c4/03-component.md`
- Create: `garda-ai-backend/docs/c4/04-code.md`

- [ ] **Step 1: Generate Code-level C4**

Use the c4-architecture plugin's `c4-code` agent against `garda_ai_backend/` to document modules (config, db, schema/*, observability, main), their functions/signatures and dependencies. Save to `docs/c4/04-code.md`.

- [ ] **Step 2: Generate Component-level C4**

Use the `c4-component` agent to synthesize the code docs into components (Config, Persistence/Schema, Observability, HTTP/App) with a Mermaid diagram. Save to `docs/c4/03-component.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/c4/
git commit -m "docs(c4): backend component + code documentation"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-22-backend-api-design.md`):
- §2 schema (all 9 tables + indexes) → Tasks 3–5, 7. ✅
- §1 stack/layering, config → Tasks 1–2, 6. ✅
- §8 observability (`/healthz`, `/readyz`, `/metrics`, structlog) → Tasks 8–9. ✅
- §10 C4 deliverable → Task 10. ✅
- **Deferred to Plan 2 (intentionally):** §3 auth, §4 view endpoints, §5 WS, §6 PII masking, §7 caching, OpenAPI type export. This plan is the runnable foundation only.

**Placeholder scan:** none — every code step contains complete code; Task 7 Step 3 notes the Postgres requirement for autogenerate explicitly.

**Type consistency:** model/table names (`banks`, `entities`, `accounts`, `transactions`, `transaction_events`, `alerts`, `users`, `sim_state`) and key columns (`seq`, `surfaced_at`, `fraud_score`, `typology`, `status`, `is_laundering`) match the backend spec §2 and are reused identically across tasks and exports. `build_engine`, `_maker`, `get_session`, `configure_logging`, `REGISTRY`, `REQUEST_COUNT` names are consistent across Tasks 6, 8, 9.
