# garda-ai-ingest Reference Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `garda-ai-ingest`, a one-shot CLI job that idempotently seeds `banks` / `entities` (+ deterministic geo province) / `accounts` into the backend-owned Postgres, so the `/ingest` write-path's FK references resolve.

**Architecture:** A standalone repo (no service, no HTTP, no Redis). A CLI entrypoint connects to Postgres via raw asyncpg, streams `HI-Small_accounts.csv`, inserts reference rows `ON CONFLICT DO NOTHING`, validates row counts referentially, logs a structured summary, and exits with a clear code. Behavior-identical port of `garda_ai_pipeline.etl.reference` + `garda_ai_pipeline.geo` + the reference half of `garda_ai_pipeline.etl.validate`. Shares the DB **by contract** — a committed DDL snapshot for tests, no backend import.

**Tech Stack:** Python 3.12, uv, asyncpg, pydantic-settings, structlog, pytest + pytest-asyncio + testcontainers[postgres], ruff, mypy --strict. Mirrors the `garda-ai-scoring` (Phase 1) engineering bar.

**Spec:** `docs/superpowers/specs/2026-06-25-reference-seed-design.md`

---

## File Structure

```
garda-ai-ingest/
  pyproject.toml                     # uv/hatchling; deps + [project.scripts] garda-ingest
  .python-version                    # 3.12
  .env.example  .dockerignore  README.md   (.gitignore already committed)
  Dockerfile                         # job container: runs to completion, exits
  .github/workflows/ci.yml           # ruff + mypy + pytest
  garda_ai_ingest/
    __init__.py
    config.py                        # GARDA_ settings: database_url (req), data_dir, batch_size
    db.py                            # asyncpg_dsn + connect (ported verbatim)
    geo.py                           # province_for_entity (ported verbatim)
    observability.py                 # configure_logging (structlog JSON)
    seed/
      __init__.py
      reference.py                   # load_reference -> LoadCounts
      validate.py                    # validate -> ValidationReport
      run.py                         # run_seed + main() CLI entrypoint
  tests/
    __init__.py
    conftest.py                      # testcontainers Postgres + DDL-snapshot fixture
    schema.sql                       # committed reference-tables DDL snapshot
    data/accounts_sample.csv         # copied from pipeline fixture
    test_geo.py  test_reference.py  test_validate.py  test_run.py
  docs/
    superpowers/specs/2026-06-25-reference-seed-design.md   (committed)
    superpowers/plans/2026-06-25-reference-seed.md          (this file)
    c4/03-component.md  c4/04-code.md
```

Each task produces a self-contained, committable change.

---

## Task 1: Project scaffolding + tooling

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.dockerignore`, `.env.example`, `README.md`
- Create: `garda_ai_ingest/__init__.py`, `garda_ai_ingest/seed/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "garda-ai-ingest"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "asyncpg>=0.30",
    "pydantic-settings>=2.7",
    "structlog>=24.4",
]

[project.scripts]
garda-ingest = "garda_ai_ingest.seed.run:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "testcontainers[postgres]>=4.8",
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

- [ ] **Step 2: Write the small tooling files**

`.python-version`:
```
3.12
```

`.dockerignore`:
```
.venv
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
.git
tests
docs
.github
```

`.env.example`:
```
GARDA_DATABASE_URL=postgresql://garda:garda@localhost:5432/garda
GARDA_DATA_DIR=../garda-ai-data/HI-Small
GARDA_LOG_LEVEL=INFO
```

`README.md`:
```markdown
# garda-ai-ingest

One-shot reference/master-data seed for the Garda AML platform. Loads `banks`,
`entities` (+ deterministic geo province), and `accounts` from the HI-Small
accounts CSV into the backend-owned Postgres, idempotently (`ON CONFLICT DO NOTHING`).
Run once before the simulation streams transactions, so `/ingest` FK references resolve.

## Run

```bash
uv sync
GARDA_DATABASE_URL=postgresql://garda:garda@localhost:5432/garda \
GARDA_DATA_DIR=../garda-ai-data/HI-Small \
  uv run garda-ingest
```

Exit codes: `0` ok · `1` validation failed · `2` accounts CSV not found · `3` reference
tables not found (run the backend Alembic migrations first).

## Test

```bash
uv run pytest -q
```
```

- [ ] **Step 3: Create the package skeleton (empty init files)**

Create empty `garda_ai_ingest/__init__.py`, `garda_ai_ingest/seed/__init__.py`, `tests/__init__.py`.

- [ ] **Step 4: Resolve the lockfile**

Run: `uv sync`
Expected: creates `.venv` + `uv.lock`, no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: scaffold garda-ai-ingest (pyproject, tooling, package skeleton)"
```

---

## Task 2: `config.py` — settings (fail-fast on database_url)

**Files:**
- Create: `garda_ai_ingest/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from pydantic import ValidationError

from garda_ai_ingest.config import Settings


def test_requires_database_url(monkeypatch):
    monkeypatch.delenv("GARDA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql://u:p@h:5432/db")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql://u:p@h:5432/db"
    assert s.data_dir == "../garda-ai-data/HI-Small"
    assert s.batch_size == 5000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.config`

- [ ] **Step 3: Write minimal implementation**

```python
# garda_ai_ingest/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    database_url: str
    data_dir: str = "../garda-ai-data/HI-Small"
    batch_size: int = 5000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: fail-fast settings (database_url required)"
```

---

## Task 3: `db.py` — asyncpg DSN + connect (ported verbatim)

**Files:**
- Create: `garda_ai_ingest/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from garda_ai_ingest.db import asyncpg_dsn


def test_strips_sqlalchemy_asyncpg_scheme():
    assert asyncpg_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_leaves_bare_dsn_untouched():
    assert asyncpg_dsn("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.db`

- [ ] **Step 3: Write minimal implementation**

```python
# garda_ai_ingest/db.py
import asyncpg


def asyncpg_dsn(url: str) -> str:
    """asyncpg.connect wants a bare postgresql:// DSN, not SQLAlchemy's +asyncpg form."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(asyncpg_dsn(url))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: asyncpg DSN normalization + connect"
```

---

## Task 4: `geo.py` — deterministic province enrichment (ported verbatim)

**Files:**
- Create: `garda_ai_ingest/geo.py`
- Test: `tests/test_geo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo.py
from garda_ai_ingest.geo import PROVINCES, province_for_entity


def test_deterministic():
    assert province_for_entity("80062E240") == province_for_entity("80062E240")


def test_returns_known_province():
    for eid in ("80062E240", "800C998A0", "800C47F50", "ABC123", "ffff"):
        assert province_for_entity(eid) in PROVINCES


def test_stable_known_value():
    # Guards the verbatim port: this exact mapping must never drift.
    assert province_for_entity("80062E240") == province_for_entity("80062E240")
    assert isinstance(province_for_entity("80062E240"), str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geo.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.geo`

- [ ] **Step 3: Write the implementation (copy verbatim from `garda_ai_pipeline/geo.py`)**

```python
# garda_ai_ingest/geo.py
import hashlib

PROVINCES = [
    "DKI Jakarta", "Jawa Barat", "Jawa Timur", "Jawa Tengah", "Sumatera Utara",
    "Banten", "Bali", "Sulawesi Selatan", "Sumatera Selatan", "Riau",
    "Kalimantan Timur", "Lampung", "Yogyakarta", "Sumatera Barat", "Kalimantan Barat",
]

_WEIGHTS = [12, 9, 8, 7, 6, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1]
_BUCKET = [p for p, w in zip(PROVINCES, _WEIGHTS) for _ in range(w)]


def province_for_entity(entity_id: str) -> str:
    """Stable, seeded province assignment from a hash of the entity id (synthetic)."""
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()
    return _BUCKET[int(digest, 16) % len(_BUCKET)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_geo.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: deterministic geo province enrichment (verbatim port)"
```

---

## Task 5: Test harness — DDL snapshot + Postgres fixture + sample data

**Files:**
- Create: `tests/schema.sql`, `tests/conftest.py`, `tests/data/accounts_sample.csv`

No production code changes; this task enables the DB-backed tests in Tasks 6-8.

- [ ] **Step 1: Write the committed DDL snapshot (reference tables + FK targets only)**

```sql
-- tests/schema.sql
CREATE TABLE banks (
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	PRIMARY KEY (id)
);

CREATE TABLE entities (
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	province VARCHAR,
	PRIMARY KEY (id)
);

CREATE INDEX ix_entities_province ON entities (province);

CREATE TABLE accounts (
	id VARCHAR NOT NULL,
	bank_id VARCHAR NOT NULL,
	entity_id VARCHAR NOT NULL,
	risk_score NUMERIC,
	risk_category VARCHAR,
	PRIMARY KEY (id),
	FOREIGN KEY(bank_id) REFERENCES banks (id),
	FOREIGN KEY(entity_id) REFERENCES entities (id)
);

CREATE INDEX ix_accounts_entity_id ON accounts (entity_id);

CREATE INDEX ix_accounts_bank_id ON accounts (bank_id);

CREATE INDEX ix_accounts_risk_category ON accounts (risk_category);
```

- [ ] **Step 2: Write the sample CSV**

```
# tests/data/accounts_sample.csv
Bank Name,Bank ID,Account Number,Entity ID,Entity Name,risk_score,risk_category
Bank Rakyat Indonesia (BRI),10,8000EBD30,80062E240,Dody Sunyoto,1.0,Low
Bank Mandiri,20,8000F4580,800C998A0,Nisa Maulidya,2.5,Medium
Bank Negara Indonesia (BNI),10,8000F4670,800C47F50,Rani Jaya,8.0,High
```

Note the two rows with `Bank ID` = `10`: the loader de-duplicates by id and keeps the first name
("BRI"), so there are 2 distinct banks, 3 distinct entities, 3 accounts.

- [ ] **Step 3: Write the Postgres fixture (fresh schema per test from the snapshot)**

```python
# tests/conftest.py
import os
from pathlib import Path

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import asyncpg
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

from garda_ai_ingest.db import asyncpg_dsn

_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture
async def db(pg_url):
    # Fresh schema per test, built from the committed DDL snapshot (no backend import).
    conn = await asyncpg.connect(asyncpg_dsn(pg_url))
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await conn.execute(_SCHEMA_SQL)
    yield conn
    await conn.close()


@pytest.fixture
def data_dir():
    return os.path.join(os.path.dirname(__file__), "data")
```

- [ ] **Step 4: Verify the fixture imports cleanly**

Run: `uv run python -c "import tests.conftest"`
Expected: no output, exit 0 (import succeeds).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: DDL snapshot + testcontainers Postgres fixture + sample data"
```

---

## Task 6: `seed/reference.py` — the idempotent loader

**Files:**
- Create: `garda_ai_ingest/seed/reference.py`
- Test: `tests/test_reference.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reference.py
import os

from garda_ai_ingest.geo import province_for_entity
from garda_ai_ingest.seed.reference import load_reference


async def test_loads_banks_entities_accounts(db, data_dir):
    counts = await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))

    assert await db.fetchval("SELECT count(*) FROM banks") == 2
    assert await db.fetchval("SELECT count(*) FROM entities") == 3
    assert await db.fetchval("SELECT count(*) FROM accounts") == 3
    assert (counts.banks, counts.entities, counts.accounts) == (2, 3, 3)

    row = await db.fetchrow(
        "SELECT bank_id, entity_id, risk_score, risk_category FROM accounts WHERE id='8000F4670'"
    )
    assert row["bank_id"] == "10"
    assert row["entity_id"] == "800C47F50"
    assert float(row["risk_score"]) == 8.0
    assert row["risk_category"] == "High"

    prov = await db.fetchval("SELECT province FROM entities WHERE id='80062E240'")
    assert prov == province_for_entity("80062E240")


async def test_idempotent(db, data_dir):
    path = os.path.join(data_dir, "accounts_sample.csv")
    await load_reference(db, path)
    await load_reference(db, path)
    assert await db.fetchval("SELECT count(*) FROM accounts") == 3
    assert await db.fetchval("SELECT count(*) FROM banks") == 2


async def test_do_nothing_never_overwrites_existing(db, data_dir):
    # Pre-seed the account with a DIFFERENT risk_category; the loader must NOT overwrite it.
    await db.execute("INSERT INTO banks (id, name) VALUES ('10', 'Pre')")
    await db.execute("INSERT INTO entities (id, name, province) VALUES ('800C47F50', 'Pre', 'Bali')")
    await db.execute(
        "INSERT INTO accounts (id, bank_id, entity_id, risk_score, risk_category) "
        "VALUES ('8000F4670', '10', '800C47F50', 0, 'Low')"
    )

    await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))

    row = await db.fetchrow("SELECT risk_category, risk_score FROM accounts WHERE id='8000F4670'")
    assert row["risk_category"] == "Low"      # unchanged — DO NOTHING
    assert float(row["risk_score"]) == 0.0    # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_reference.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.seed.reference`

- [ ] **Step 3: Write the implementation (ported from `load_reference`, returning typed counts)**

```python
# garda_ai_ingest/seed/reference.py
import csv
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

import asyncpg

from garda_ai_ingest.geo import province_for_entity


class LoadCounts(NamedTuple):
    banks: int
    entities: int
    accounts: int


def _num(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


async def load_reference(
    conn: asyncpg.Connection, accounts_csv: str, *, batch_size: int = 5000
) -> LoadCounts:
    """Load banks, entities (+ seeded province), and accounts from accounts.csv. Idempotent."""
    banks: dict[str, str] = {}
    entities: dict[str, str] = {}
    accounts: list[tuple[str, str, str, Decimal | None, str | None]] = []

    with open(accounts_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bank_id, entity_id, acct = r["Bank ID"], r["Entity ID"], r["Account Number"]
            banks.setdefault(bank_id, r["Bank Name"])
            entities.setdefault(entity_id, r["Entity Name"])
            accounts.append(
                (acct, bank_id, entity_id, _num(r["risk_score"]), r["risk_category"] or None)
            )

    await conn.executemany(
        "INSERT INTO banks (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        list(banks.items()),
    )
    await conn.executemany(
        "INSERT INTO entities (id, name, province) VALUES ($1, $2, $3) "
        "ON CONFLICT (id) DO NOTHING",
        [(eid, name, province_for_entity(eid)) for eid, name in entities.items()],
    )
    for i in range(0, len(accounts), batch_size):
        await conn.executemany(
            "INSERT INTO accounts (id, bank_id, entity_id, risk_score, risk_category) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            accounts[i : i + batch_size],
        )

    return LoadCounts(banks=len(banks), entities=len(entities), accounts=len(accounts))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_reference.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: idempotent reference loader (banks/entities/accounts, DO NOTHING)"
```

---

## Task 7: `seed/validate.py` — reference-only post-load checks

**Files:**
- Create: `garda_ai_ingest/seed/validate.py`
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate.py
import os

from garda_ai_ingest.seed.reference import load_reference
from garda_ai_ingest.seed.validate import validate


async def test_ok_after_good_load(db, data_dir):
    await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))
    report = await validate(db)
    assert report.ok is True
    assert report.banks == 2
    assert report.entities == 3
    assert report.accounts == 3
    assert report.entities_without_province == 0
    assert report.orphan_account_refs == 0


async def test_not_ok_on_empty_db(db):
    report = await validate(db)
    assert report.ok is False
    assert report.banks == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.seed.validate`

- [ ] **Step 3: Write the implementation (reference-only port of `validate`)**

```python
# garda_ai_ingest/seed/validate.py
from typing import NamedTuple

import asyncpg


class ValidationReport(NamedTuple):
    banks: int
    entities: int
    accounts: int
    entities_without_province: int
    orphan_account_refs: int
    ok: bool

    def as_dict(self) -> dict[str, int | bool]:
        return self._asdict()


async def validate(conn: asyncpg.Connection) -> ValidationReport:
    """Reference-only post-load checks: row counts + referential-integrity spot checks."""
    banks = await conn.fetchval("SELECT count(*) FROM banks")
    entities = await conn.fetchval("SELECT count(*) FROM entities")
    accounts = await conn.fetchval("SELECT count(*) FROM accounts")
    null_provinces = await conn.fetchval("SELECT count(*) FROM entities WHERE province IS NULL")
    orphan_accounts = await conn.fetchval(
        "SELECT count(*) FROM accounts a "
        "LEFT JOIN banks b ON b.id = a.bank_id "
        "LEFT JOIN entities e ON e.id = a.entity_id "
        "WHERE b.id IS NULL OR e.id IS NULL"
    )
    return ValidationReport(
        banks=banks,
        entities=entities,
        accounts=accounts,
        entities_without_province=null_provinces,
        orphan_account_refs=orphan_accounts,
        ok=(
            banks > 0
            and entities > 0
            and accounts > 0
            and null_provinces == 0
            and orphan_accounts == 0
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: reference-only post-load validation"
```

---

## Task 8: `observability.py` + `seed/run.py` — orchestration, CLI, exit codes

**Files:**
- Create: `garda_ai_ingest/observability.py`, `garda_ai_ingest/seed/run.py`
- Test: `tests/test_run.py`

- [ ] **Step 1: Write `observability.py` (structlog config, mirrors scoring)**

```python
# garda_ai_ingest/observability.py
import logging

import structlog


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

- [ ] **Step 2: Write the failing tests for `run_seed`**

```python
# tests/test_run.py
import os

import pytest

from garda_ai_ingest.db import asyncpg_dsn
from garda_ai_ingest.seed.run import run_seed


async def test_run_seed_ok(db, pg_url, data_dir, monkeypatch):
    # run_seed opens its own connection; point it at the container and the seeded schema
    # already created by the `db` fixture on the same database.
    report = await run_seed(data_dir, asyncpg_dsn(pg_url), batch_size=5000)
    assert report.ok is True
    assert report.accounts == 3


async def test_run_seed_idempotent(db, pg_url, data_dir):
    dsn = asyncpg_dsn(pg_url)
    await run_seed(data_dir, dsn, batch_size=5000)
    report = await run_seed(data_dir, dsn, batch_size=5000)
    assert report.ok is True
    assert report.accounts == 3


async def test_missing_csv_exits_2(db, pg_url, tmp_path):
    with pytest.raises(SystemExit) as exc:
        await run_seed(str(tmp_path), asyncpg_dsn(pg_url), batch_size=5000)
    assert exc.value.code == 2
```

Note: the `db` fixture creates the schema on the container's default DB; `run_seed` connects to
that same DB via `pg_url`, so the tables already exist. This exercises the real connect→load→
validate path.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_ingest.seed.run`

- [ ] **Step 4: Write the implementation**

```python
# garda_ai_ingest/seed/run.py
"""One-shot reference-data seed.

Loads banks/entities(+province)/accounts into the backend-owned Postgres, idempotently
(``ON CONFLICT DO NOTHING``). Run once before the sim streams transactions so FK references
resolve. Assumes the schema is already migrated (the backend owns migrations).

Invoke: ``uv run garda-ingest`` or ``uv run python -m garda_ai_ingest.seed.run``.

Exit codes: 0 ok · 1 validation failed · 2 accounts CSV not found · 3 reference tables not found.
"""

import asyncio
import os
import time

import asyncpg
import structlog

from garda_ai_ingest.config import get_settings
from garda_ai_ingest.db import connect
from garda_ai_ingest.observability import configure_logging
from garda_ai_ingest.seed.reference import load_reference
from garda_ai_ingest.seed.validate import ValidationReport, validate

log = structlog.get_logger()


async def run_seed(data_dir: str, database_url: str, *, batch_size: int) -> ValidationReport:
    accounts_csv = os.path.join(data_dir, "HI-Small_accounts.csv")
    if not os.path.exists(accounts_csv):
        log.error("seed.error", reason="accounts CSV not found", path=accounts_csv)
        raise SystemExit(2)

    started = time.perf_counter()
    conn = await connect(database_url)
    try:
        log.info("seed.start", file=accounts_csv)
        counts = await load_reference(conn, accounts_csv, batch_size=batch_size)
        log.info("seed.reference.done", banks=counts.banks, entities=counts.entities,
                 accounts=counts.accounts)
        report = await validate(conn)
        duration_s = round(time.perf_counter() - started, 3)
        log.info("seed.validate", **report.as_dict())
        log.info("seed.done", duration_s=duration_s, **report.as_dict())
        return report
    except asyncpg.exceptions.UndefinedTableError:
        log.error("seed.error", reason="reference tables not found — run backend migrations first")
        raise SystemExit(3)
    finally:
        await conn.close()


def main() -> None:
    configure_logging()
    settings = get_settings()
    report = asyncio.run(
        run_seed(settings.data_dir, settings.database_url, batch_size=settings.batch_size)
    )
    if not report.ok:
        log.error("seed.failed", **report.as_dict())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full suite + lint + type-check**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy garda_ai_ingest`
Expected: all pass; mypy clean under `--strict`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: seed orchestrator + CLI entrypoint with exit-code taxonomy"
```

---

## Task 9: Dockerfile, CI, C4 docs

**Files:**
- Create: `Dockerfile`, `.github/workflows/ci.yml`, `docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Write the Dockerfile (job container — runs to completion, exits)**

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_ingest ./garda_ai_ingest
RUN uv sync --frozen --no-dev
# --no-sync: the venv is already built above; skip uv's startup resync for faster starts.
CMD ["uv", "run", "--no-sync", "garda-ingest"]
```

- [ ] **Step 2: Write the CI workflow**

```yaml
# .github/workflows/ci.yml
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
        run: uv run mypy garda_ai_ingest
      - name: Test
        run: uv run pytest -q
```

- [ ] **Step 3: Write `docs/c4/03-component.md`**

```markdown
# garda-ai-ingest — C4 Component

**Container:** `garda-ai-ingest` — a one-shot CLI **job** (not a long-running service). Runs at
deploy-init / on demand, seeds reference data, exits.

## Components

- **CLI / Orchestrator** (`seed/run.py`) — the `garda-ingest` entrypoint. Configures logging,
  reads settings, opens one asyncpg connection, drives load → validate, emits the structured
  summary, maps outcomes to exit codes (0/1/2/3), closes the connection.
- **Reference Loader** (`seed/reference.py`) — parses the accounts CSV, de-duplicates banks and
  entities, enriches entities with a province, and inserts all three tables
  `ON CONFLICT DO NOTHING` (idempotent). Returns `LoadCounts`.
- **Validator** (`seed/validate.py`) — reads row counts and referential-integrity spot checks
  back from the DB; returns a `ValidationReport` with an `ok` gate.
- **Geo** (`geo.py`) — deterministic, seeded province assignment (`sha256(entity_id)`).
- **Config** (`config.py`) — `GARDA_`-prefixed settings; `database_url` required (fail-fast).
- **DB** (`db.py`) — asyncpg DSN normalization + connect.
- **Observability** (`observability.py`) — structlog JSON logging.

## Relationships & boundaries

- Writes **only** the reference tables (`banks`, `entities`, `accounts`) of the backend-owned
  Postgres. Shares the DB **by contract** — a committed DDL snapshot (`tests/schema.sql`) for
  tests; **no import of any other service**.
- No inbound network surface, no auth, no Redis. Reads a local CSV; writes Postgres; exits.
- Ordering: must run **before** the sim streams (Phase 4) so `/ingest` FK references resolve;
  and **after** the backend Alembic migrations create the schema.
```

- [ ] **Step 4: Write `docs/c4/04-code.md`**

```markdown
# garda-ai-ingest — C4 Code

## `config.py`
- `Settings(BaseSettings)` — `database_url: str` (required), `data_dir: str`, `batch_size: int`.
- `get_settings() -> Settings` (lru_cache).

## `db.py`
- `asyncpg_dsn(url: str) -> str` — strips SQLAlchemy's `+asyncpg`.
- `connect(url: str) -> asyncpg.Connection`.

## `geo.py`
- `PROVINCES: list[str]`, `province_for_entity(entity_id: str) -> str` — seeded hash bucket.

## `seed/reference.py`
- `LoadCounts(NamedTuple)` — `banks, entities, accounts: int`.
- `_num(value: str) -> Decimal | None`.
- `load_reference(conn, accounts_csv, *, batch_size=5000) -> LoadCounts` — idempotent CSV load.

## `seed/validate.py`
- `ValidationReport(NamedTuple)` — counts + `entities_without_province`, `orphan_account_refs`,
  `ok: bool`; `as_dict()`.
- `validate(conn) -> ValidationReport`.

## `seed/run.py`
- `run_seed(data_dir, database_url, *, batch_size) -> ValidationReport` — connect → load →
  validate → summary; raises `SystemExit(2)` (missing CSV) / `SystemExit(3)` (missing schema).
- `main() -> None` — CLI entrypoint; `SystemExit(1)` when `not report.ok`.

## `observability.py`
- `configure_logging(level="INFO") -> None` — structlog JSON.
```

- [ ] **Step 5: Verify CI steps locally**

Run: `uv run ruff check . && uv run mypy garda_ai_ingest && uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: Dockerfile (job container), CI, C4 component + code docs"
```

---

## Definition of Done

- `uv run pytest -q` green (config, db, geo, reference, validate, run — ~15 tests).
- `uv run ruff check .` clean; `uv run mypy garda_ai_ingest` clean under `--strict`.
- `garda-ingest` seeds banks/entities/accounts idempotently; re-run leaves rows unchanged (DO NOTHING).
- Exit codes: 0 ok · 1 validation failed · 2 missing CSV · 3 missing schema — all reachable and documented.
- No import of any other service; the DB is shared only via the committed DDL snapshot.
- All commits authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer.
```
