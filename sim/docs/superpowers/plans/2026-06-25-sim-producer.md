# garda-ai-sim Local Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `garda-ai-sim`, a local-only CLI producer that streams the HI-Small transactions CSV as batches to the backend `POST /api/v1/ingest`, pacing by the CSV's real inter-arrival gaps (compressed by `speed`, clamped by `max_gap_s`) and stamping `event_time = now`.

**Architecture:** A standalone repo (no DB, no Redis, no scorer). A streaming CSV reader assigns a stable ordinal `transaction_id`; a paced producer loop batches rows and POSTs them via a pooled, retrying httpx `IngestClient`; a CLI wires config → reader → producer with a clear exit-code taxonomy. The backend does all scoring/persist/publish.

**Tech Stack:** Python 3.12, uv, httpx, pydantic-settings, structlog, pytest + pytest-asyncio (httpx `MockTransport` — no DB), ruff, mypy --strict. Mirrors the Phase 1–3 engineering bar.

**Spec:** `docs/superpowers/specs/2026-06-25-sim-producer-design.md`

---

## File Structure

```
garda-ai-sim/
  pyproject.toml  .python-version  .env.example  .dockerignore  README.md   (.gitignore committed)
  Dockerfile                       # LOCAL-ONLY (compose convenience), non-root
  .github/workflows/ci.yml
  garda_ai_sim/
    __init__.py
    config.py                      # GARDA_ settings: ingest_url, ingest_token (req), pacing knobs
    observability.py               # configure_logging (structlog JSON)
    reader.py                      # stream_transactions -> SimTxn (ordinal id, csv_ts, fields)
    client.py                      # IngestClient (pooled httpx, bounded retry) + IngestError/Unavailable
    producer.py                    # Producer: paced batch loop -> SimStats
    run.py                         # main() CLI entrypoint (exit 0/1/2)
  tests/
    __init__.py
    conftest.py                    # (minimal — no DB)
    data/trans_sample_part1.csv  data/trans_sample_part2.csv
    test_config.py  test_reader.py  test_client.py  test_producer.py  test_run.py
  docs/
    superpowers/specs/2026-06-25-sim-producer-design.md   (committed)
    superpowers/plans/2026-06-25-sim-producer.md          (this file)
    c4/03-component.md  c4/04-code.md
```

---

## Task 1: Project scaffolding + tooling

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.dockerignore`, `.env.example`, `README.md`
- Create: `garda_ai_sim/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "garda-ai-sim"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28",
    "pydantic-settings>=2.7",
    "structlog>=24.4",
]

[project.scripts]
garda-sim = "garda_ai_sim.run:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
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
GARDA_INGEST_URL=http://localhost:8000/api/v1/ingest
GARDA_INGEST_TOKEN=change-me-to-the-backend-ingest-token
GARDA_DATA_DIR=../garda-ai-data/HI-Small
GARDA_SPEED=60.0
GARDA_BATCH_SIZE=100
GARDA_LOG_LEVEL=INFO
```

`README.md`:
```markdown
# garda-ai-sim

Local-only simulation producer for the Garda AML platform. Streams the HI-Small
transactions CSV as batches to the backend `POST /api/v1/ingest` (bearer ingest token),
pacing by the CSV's real inter-arrival gaps compressed by `speed` (capped by `max_gap_s`)
and stamping `event_time = now`. Owns pacing/speed/start-stop locally. **Never deployed.**

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
```

- [ ] **Step 3: Create the package skeleton**

Create empty `garda_ai_sim/__init__.py`, `tests/__init__.py`, and `tests/conftest.py` (empty — no DB fixtures needed).

- [ ] **Step 4: Resolve the lockfile**

Run: `uv sync`
Expected: creates `.venv` + `uv.lock`, no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: scaffold garda-ai-sim (pyproject, tooling, package skeleton)"
```

---

## Task 2: `config.py` — settings (fail-fast on ingest_token)

**Files:**
- Create: `garda_ai_sim/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pytest
from pydantic import ValidationError

from garda_ai_sim.config import Settings


def test_requires_ingest_token(monkeypatch):
    monkeypatch.delenv("GARDA_INGEST_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_empty_token(monkeypatch):
    monkeypatch.setenv("GARDA_INGEST_TOKEN", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_INGEST_TOKEN", "tok")
    s = Settings(_env_file=None)
    assert s.ingest_url.endswith("/api/v1/ingest")
    assert s.batch_size == 100
    assert s.speed == 60.0
    assert s.max_gap_s == 2.0
    assert s.limit is None
    assert s.dry_run is False
    assert s.log_level == "INFO"


def test_rejects_nonpositive_speed(monkeypatch):
    monkeypatch.setenv("GARDA_INGEST_TOKEN", "tok")
    monkeypatch.setenv("GARDA_SPEED", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_sim.config`

- [ ] **Step 3: Write minimal implementation**

```python
# garda_ai_sim/config.py
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GARDA_", env_file=".env", extra="ignore")

    ingest_url: str = "http://localhost:8000/api/v1/ingest"
    ingest_token: str = Field(min_length=1)  # required, non-empty
    data_dir: str = "../garda-ai-data/HI-Small"
    trans_files: list[str] = ["HI-Small_Trans_part1.csv", "HI-Small_Trans_part2.csv"]
    batch_size: int = Field(default=100, gt=0, le=1000)
    speed: float = Field(default=60.0, gt=0)
    max_gap_s: float = Field(default=2.0, ge=0)
    limit: int | None = None
    dry_run: bool = False
    request_timeout_s: float = 30.0
    retries: int = 3
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: fail-fast settings (ingest_token required, pacing knobs)"
```

---

## Task 3: `observability.py` — structlog config

**Files:**
- Create: `garda_ai_sim/observability.py`
- Test: none (config-only; exercised via the run tests)

- [ ] **Step 1: Write the implementation**

```python
# garda_ai_sim/observability.py
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

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "from garda_ai_sim.observability import configure_logging; configure_logging('INFO')"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: structlog JSON logging config"
```

---

## Task 4: `reader.py` — streaming CSV reader (ordinal id, csv_ts, fields)

**Files:**
- Create: `garda_ai_sim/reader.py`, `tests/data/trans_sample_part1.csv`, `tests/data/trans_sample_part2.csv`
- Test: `tests/test_reader.py`

- [ ] **Step 1: Write the sample CSV fixtures**

`tests/data/trans_sample_part1.csv`:
```
Timestamp,From Bank,Account,To Bank,To Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering
2025/09/01 00:00,10,8000EBD30,20,8000F4580,100.00,IDR,100.00,IDR,ACH,0
2025/09/01 00:00,20,8000F4580,10,8000F4670,250000.00,IDR,250000.00,IDR,Cheque,1
2025/09/01 00:02,10,8000F4670,10,8000EBD30,5000000.00,IDR,5000000.00,IDR,ACH,1
```

`tests/data/trans_sample_part2.csv` (its first row's timestamp 00:01 is BEFORE part1's last 00:02 — exercises the continuous-ordinal + negative-gap cases):
```
Timestamp,From Bank,Account,To Bank,To Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering
2025/09/01 00:01,10,8000EBD30,20,8000F4580,150000.00,IDR,150000.00,IDR,ACH,0
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_reader.py
import os
from datetime import UTC, datetime

from garda_ai_sim.reader import SimTxn, stream_transactions


def _paths():
    d = os.path.join(os.path.dirname(__file__), "data")
    return [os.path.join(d, "trans_sample_part1.csv"), os.path.join(d, "trans_sample_part2.csv")]


def test_streams_all_rows_with_continuous_ordinals():
    rows = list(stream_transactions(_paths()))
    assert [r.ordinal for r in rows] == [1, 2, 3, 4]  # continuous across the two parts
    assert all(isinstance(r, SimTxn) for r in rows)


def test_field_mapping():
    rows = list(stream_transactions(_paths()))
    r2 = rows[1]
    assert r2.fields["from_bank_id"] == "20"
    assert r2.fields["from_account"] == "8000F4580"
    assert r2.fields["to_bank_id"] == "10"
    assert r2.fields["amount_paid"] == "250000.00"
    assert r2.fields["payment_format"] == "Cheque"
    assert r2.fields["is_laundering"] is True
    assert rows[0].fields["is_laundering"] is False
    assert "event_time" not in r2.fields  # stamped by the producer, not the reader


def test_timestamps_parsed_utc():
    rows = list(stream_transactions(_paths()))
    assert rows[2].csv_ts == datetime(2025, 9, 1, 0, 2, tzinfo=UTC)
    assert rows[3].csv_ts == datetime(2025, 9, 1, 0, 1, tzinfo=UTC)  # part2, earlier than part1's last


def test_limit_respected():
    rows = list(stream_transactions(_paths(), limit=2))
    assert [r.ordinal for r in rows] == [1, 2]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_sim.reader`

- [ ] **Step 4: Write the implementation**

```python
# garda_ai_sim/reader.py
import csv
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple


class SimTxn(NamedTuple):
    ordinal: int                    # 1-based, continuous across parts -> the transaction_id
    csv_ts: datetime                # original CSV timestamp; used ONLY for pacing, never sent
    fields: dict[str, object]       # ingest fields minus event_time (producer stamps that)


def _row_fields(r: dict[str, str]) -> dict[str, object]:
    return {
        "from_bank_id": r["From Bank"],
        "from_account": r["Account"],
        "to_bank_id": r["To Bank"],
        "to_account": r["To Account"],
        "amount_paid": str(Decimal(r["Amount Paid"])),        # string -> exact Decimal on the backend
        "payment_currency": r["Payment Currency"],
        "amount_received": str(Decimal(r["Amount Received"])),
        "receiving_currency": r["Receiving Currency"],
        "payment_format": r["Payment Format"],
        "is_laundering": r["Is Laundering"] == "1",
    }


def stream_transactions(paths: list[str], *, limit: int | None = None) -> Iterator[SimTxn]:
    """Stream transactions from the Trans CSV parts, assigning a stable 1-based ordinal id
    continuous across parts. Streamed (never materialized) so the multi-million-row parts
    cost negligible memory."""
    ordinal = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if limit is not None and ordinal >= limit:
                    return
                ordinal += 1
                ts = datetime.strptime(r["Timestamp"], "%Y/%m/%d %H:%M").replace(tzinfo=UTC)
                yield SimTxn(ordinal=ordinal, csv_ts=ts, fields=_row_fields(r))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_reader.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: streaming CSV reader (continuous ordinal id, pacing timestamp, ingest fields)"
```

---

## Task 5: `client.py` — pooled, retrying ingest client

**Files:**
- Create: `garda_ai_sim/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client.py
import httpx
import pytest

from garda_ai_sim.client import IngestClient, IngestError, IngestSummary, IngestUnavailable


async def test_maps_response_and_sends_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["cid"] = request.headers.get("X-Correlation-ID")
        return httpx.Response(200, json={"results": [{"ingested": True}, {"ingested": False}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x/api/v1/ingest", "tok")
        summary = await client.send([{"transaction_id": 1}], correlation_id="cid-1")

    assert summary == IngestSummary(ingested=1, duplicate=1)
    assert seen["auth"] == "Bearer tok"
    assert seen["cid"] == "cid-1"


async def test_4xx_raises_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x", "tok", retries=3)
        with pytest.raises(IngestError):
            await client.send([], correlation_id="cid")
    assert calls == 1  # 4xx is not retried


async def test_5xx_retries_then_unavailable(monkeypatch):
    import garda_ai_sim.client as client_mod

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", no_sleep)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        client = IngestClient(c, "http://x", "tok", retries=2)
        with pytest.raises(IngestUnavailable):
            await client.send([], correlation_id="cid")
    assert calls == 3  # initial + 2 retries
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_sim.client`

- [ ] **Step 3: Write the implementation (mirrors the backend `ScoringClient` resilience pattern)**

```python
# garda_ai_sim/client.py
import asyncio
from typing import NamedTuple

import httpx


class IngestSummary(NamedTuple):
    ingested: int
    duplicate: int


class IngestError(Exception):
    """The backend rejected the batch (4xx: bad token / contract). Not retryable."""


class IngestUnavailable(Exception):
    """The backend was unreachable / returned 5xx after retries."""


class IngestClient:
    """Thin client for the backend POST /api/v1/ingest. Retries transient failures."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        token: str,
        *,
        retries: int = 3,
        timeout_s: float = 30.0,
    ) -> None:
        self._client = client
        self._url = url
        self._token = token
        self._retries = retries
        self._timeout = timeout_s

    async def send(
        self, txns: list[dict[str, object]], *, correlation_id: str
    ) -> IngestSummary:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-Correlation-ID": correlation_id,
        }
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.post(
                    self._url,
                    json={"transactions": txns},
                    headers=headers,
                    timeout=self._timeout,
                )
            except httpx.TransportError as exc:  # connect/read timeouts, connection errors
                last_exc = exc
            else:
                if resp.status_code < 400:
                    try:
                        results = list(resp.json()["results"])
                    except (ValueError, KeyError, TypeError) as exc:
                        raise IngestUnavailable("ingest returned a malformed response") from exc
                    ingested = sum(1 for r in results if r.get("ingested"))
                    return IngestSummary(ingested=ingested, duplicate=len(results) - ingested)
                if resp.status_code < 500:
                    # A 4xx is a contract/auth problem — not transient; do not retry.
                    raise IngestError(f"ingest rejected batch: HTTP {resp.status_code}")
                last_exc = httpx.HTTPStatusError(
                    "ingest 5xx", request=resp.request, response=resp
                )
            if attempt < self._retries:
                await asyncio.sleep(0.5 * (2**attempt))  # 0.5s, 1s, 2s backoff
        raise IngestUnavailable("ingest unavailable after retries") from last_exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: pooled retrying ingest client (4xx fail-fast, 5xx/transport retry)"
```

---

## Task 6: `producer.py` — paced batch loop

**Files:**
- Create: `garda_ai_sim/producer.py`
- Test: `tests/test_producer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_producer.py
from datetime import UTC, datetime

from garda_ai_sim.client import IngestSummary
from garda_ai_sim.producer import Producer, SimStats
from garda_ai_sim.reader import SimTxn


class StubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict], str]] = []

    async def send(self, txns: list[dict], *, correlation_id: str) -> IngestSummary:
        self.calls.append((txns, correlation_id))
        return IngestSummary(ingested=len(txns), duplicate=0)


def _txn(ordinal: int, minute: int) -> SimTxn:
    return SimTxn(
        ordinal=ordinal,
        csv_ts=datetime(2025, 9, 1, 0, minute, tzinfo=UTC),
        fields={"from_bank_id": "10", "is_laundering": False},
    )


async def test_pacing_batching_and_stamping():
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    fixed = datetime(2026, 8, 4, 10, 0, tzinfo=UTC)
    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=1,
        sleep=fake_sleep, now=lambda: fixed, new_correlation_id=lambda: "cid",
    )
    # gaps between csv_ts: b1->b2 = 1min (60s/60 = 1.0s); b2->b3 = 5min (300/60 = 5.0 -> clamp 2.0);
    # b3->b4 = 0min (0.0 -> no sleep)
    rows = [_txn(1, 0), _txn(2, 1), _txn(3, 6), _txn(4, 6)]
    stats = await producer.run(rows)

    assert stats == SimStats(batches=4, sent=4, ingested=4, duplicate=0)
    assert delays == [1.0, 2.0]           # first batch no wait; 0.0 gaps not slept; 5min clamped to 2.0
    first_payload = client.calls[0][0][0]
    assert first_payload["transaction_id"] == 1
    assert first_payload["event_time"] == fixed.isoformat()   # stamped from now
    assert first_payload["from_bank_id"] == "10"


async def test_dry_run_posts_nothing():
    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=10,
        sleep=_noop_sleep, now=lambda: datetime(2026, 8, 4, tzinfo=UTC),
        new_correlation_id=lambda: "cid",
    )
    stats = await producer.run([_txn(1, 0), _txn(2, 0)], dry_run=True)
    assert client.calls == []
    assert stats.sent == 2
    assert stats.batches == 1


async def _noop_sleep(_d: float) -> None:
    return None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_producer.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_sim.producer`

- [ ] **Step 3: Write the implementation**

```python
# garda_ai_sim/producer.py
import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog

from garda_ai_sim.client import IngestSummary
from garda_ai_sim.reader import SimTxn

log = structlog.get_logger()


@dataclass
class SimStats:
    batches: int = 0
    sent: int = 0
    ingested: int = 0
    duplicate: int = 0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


class _Sendable(Protocol):
    """Structural type for the ingest client the producer needs (just ``send``)."""

    async def send(
        self, txns: list[dict[str, object]], *, correlation_id: str
    ) -> IngestSummary: ...


class Producer:
    def __init__(
        self,
        client: _Sendable,
        *,
        speed: float,
        max_gap_s: float,
        batch_size: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] | None = None,
        new_correlation_id: Callable[[], str] | None = None,
    ) -> None:
        self._client = client
        self._speed = speed
        self._max_gap_s = max_gap_s
        self._batch_size = batch_size
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(UTC))
        self._new_cid = new_correlation_id or (lambda: str(uuid.uuid4()))

    async def run(self, rows: Iterable[SimTxn], *, dry_run: bool = False) -> SimStats:
        stats = SimStats()
        prev_last_ts: datetime | None = None
        batch: list[SimTxn] = []

        async def flush() -> None:
            nonlocal prev_last_ts, batch
            if not batch:
                return
            if prev_last_ts is not None:
                delay = _clamp(
                    (batch[0].csv_ts - prev_last_ts).total_seconds() / self._speed,
                    0.0,
                    self._max_gap_s,
                )
                if delay > 0:
                    await self._sleep(delay)
            stamp = self._now().isoformat()
            payloads: list[dict[str, object]] = [
                {**t.fields, "transaction_id": t.ordinal, "event_time": stamp} for t in batch
            ]
            if dry_run:
                log.info("sim.batch.dry_run", size=len(payloads), first_id=batch[0].ordinal)
            else:
                summary = await self._client.send(payloads, correlation_id=self._new_cid())
                stats.ingested += summary.ingested
                stats.duplicate += summary.duplicate
            stats.batches += 1
            stats.sent += len(payloads)
            prev_last_ts = batch[-1].csv_ts
            log.info(
                "sim.batch",
                batches=stats.batches, sent=stats.sent,
                ingested=stats.ingested, duplicate=stats.duplicate,
            )
            batch = []

        for txn in rows:
            batch.append(txn)
            if len(batch) >= self._batch_size:
                await flush()
        await flush()
        return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_producer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: paced batch producer (CSV-cadence pacing, now-stamped event_time)"
```

---

## Task 7: `run.py` — CLI orchestration + exit codes

**Files:**
- Create: `garda_ai_sim/run.py`
- Test: `tests/test_run.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_run.py
from types import SimpleNamespace

import pytest

from garda_ai_sim import run as run_mod
from garda_ai_sim.client import IngestUnavailable

_HEADER = (
    "Timestamp,From Bank,Account,To Bank,To Account,Amount Received,"
    "Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering\n"
)
_ROW = "2025/09/01 00:00,10,A,20,B,1.00,IDR,1.00,IDR,ACH,0\n"


def _settings(**over):
    base = dict(
        ingest_url="http://x/api/v1/ingest", ingest_token="tok",
        data_dir="X", trans_files=["p1.csv"],
        batch_size=10, speed=60.0, max_gap_s=2.0, limit=None, dry_run=False,
        request_timeout_s=30.0, retries=3, log_level="INFO",
    )
    base.update(over)
    return SimpleNamespace(**base)


async def test_missing_csv_exits_2():
    with pytest.raises(SystemExit) as exc:
        await run_mod.run_sim(_settings(data_dir="/nonexistent", trans_files=["nope.csv"]))
    assert exc.value.code == 2


async def test_ingest_unavailable_exits_1(monkeypatch, tmp_path):
    (tmp_path / "p1.csv").write_text(_HEADER + _ROW)

    async def boom(self, rows, *, dry_run=False):
        raise IngestUnavailable("backend down")

    monkeypatch.setattr(run_mod.Producer, "run", boom)
    with pytest.raises(SystemExit) as exc:
        await run_mod.run_sim(_settings(data_dir=str(tmp_path), trans_files=["p1.csv"]))
    assert exc.value.code == 1


async def test_happy_dry_run(tmp_path):
    (tmp_path / "p1.csv").write_text(_HEADER + _ROW + _ROW)
    # dry_run => no HTTP; returns normally (no SystemExit)
    await run_mod.run_sim(_settings(data_dir=str(tmp_path), trans_files=["p1.csv"], dry_run=True))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: garda_ai_sim.run`

- [ ] **Step 3: Write the implementation**

```python
# garda_ai_sim/run.py
"""Local simulation producer entrypoint.

Streams the HI-Small transactions CSV as batches to the backend POST /api/v1/ingest, paced by the
CSV's real inter-arrival gaps (compressed by ``speed``, clamped by ``max_gap_s``) and stamped with
``event_time = now``. Local-only; never deployed.

Invoke: ``uv run garda-sim`` or ``uv run python -m garda_ai_sim.run``.

Exit codes: 0 ok / interrupted · 1 backend rejected or unreachable · 2 Trans CSV not found.
"""

import asyncio
import os
import time

import httpx
import structlog

from garda_ai_sim.client import IngestClient, IngestError, IngestUnavailable
from garda_ai_sim.config import Settings, get_settings
from garda_ai_sim.observability import configure_logging
from garda_ai_sim.producer import Producer
from garda_ai_sim.reader import stream_transactions

log = structlog.get_logger()


def _resolve_paths(data_dir: str, trans_files: list[str]) -> list[str]:
    return [
        os.path.join(data_dir, f)
        for f in trans_files
        if os.path.exists(os.path.join(data_dir, f))
    ]


async def run_sim(settings: Settings) -> None:
    paths = _resolve_paths(settings.data_dir, settings.trans_files)
    if not paths:
        log.error("sim.error", reason="no Trans CSV found", data_dir=settings.data_dir)
        raise SystemExit(2)

    started = time.perf_counter()
    async with httpx.AsyncClient() as http:
        client = IngestClient(
            http, settings.ingest_url, settings.ingest_token,
            retries=settings.retries, timeout_s=settings.request_timeout_s,
        )
        producer = Producer(
            client, speed=settings.speed, max_gap_s=settings.max_gap_s,
            batch_size=settings.batch_size,
        )
        rows = stream_transactions(paths, limit=settings.limit)
        try:
            stats = await producer.run(rows, dry_run=settings.dry_run)
        except (IngestError, IngestUnavailable) as exc:
            log.error("sim.error", reason=str(exc))
            raise SystemExit(1) from exc

    duration_s = round(time.perf_counter() - started, 3)
    log.info(
        "sim.done",
        batches=stats.batches, sent=stats.sent,
        ingested=stats.ingested, duplicate=stats.duplicate, duration_s=duration_s,
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        asyncio.run(run_sim(settings))
    except KeyboardInterrupt:  # graceful local stop; per-batch logs are the partial record
        log.info("sim.interrupted")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full suite + lint + type-check**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy garda_ai_sim`
Expected: all pass; mypy clean under `--strict`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: CLI orchestrator with exit-code taxonomy (0/1/2) + graceful Ctrl-C"
```

---

## Task 8: Dockerfile, CI, C4 docs

**Files:**
- Create: `Dockerfile`, `.github/workflows/ci.yml`, `docs/c4/03-component.md`, `docs/c4/04-code.md`

- [ ] **Step 1: Write the Dockerfile (LOCAL-ONLY, non-root)**

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garda_ai_sim ./garda_ai_sim
RUN uv sync --frozen --no-dev
# LOCAL-ONLY (docker compose convenience). Needs GARDA_INGEST_TOKEN + GARDA_INGEST_URL and the
# Trans CSVs mounted (set GARDA_DATA_DIR). NEVER deployed to production.
RUN useradd --system --uid 1001 garda
USER garda
CMD ["uv", "run", "--no-sync", "garda-sim"]
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
        run: uv run mypy garda_ai_sim
      - name: Test
        env:
          GARDA_INGEST_TOKEN: ci-token
        run: uv run pytest -q
```

- [ ] **Step 3: Write `docs/c4/03-component.md`**

```markdown
# garda-ai-sim — C4 Component

**Container:** `garda-ai-sim` — a **local-only** CLI producer (never deployed). Reads the HI-Small
Trans CSV and streams scored-input batches to the backend `POST /api/v1/ingest`.

## Components

- **CLI / Orchestrator** (`run.py`) — the `garda-sim` entrypoint. Configures logging, resolves the
  Trans CSV paths, builds the pooled httpx client + `IngestClient` + `Producer`, runs the stream,
  logs the run summary, maps outcomes to exit codes (0/1/2), handles Ctrl-C.
- **Reader** (`reader.py`) — streams the Trans CSV parts into `SimTxn`s, assigning a stable 1-based
  `transaction_id` ordinal (continuous across parts) and parsing the pacing timestamp. Never
  materializes the file.
- **Producer** (`producer.py`) — the paced batch loop: groups rows into batches, waits
  `clamp(csv_gap / speed, 0, max_gap_s)` between batches, stamps `event_time = now`, POSTs via the
  client, accumulates `SimStats`. Injectable `sleep`/`now`/`correlation-id` for deterministic tests.
- **IngestClient** (`client.py`) — pooled httpx wrapper for `POST /api/v1/ingest`; bearer token +
  per-batch correlation id; bounded retry with backoff (4xx → `IngestError` fail-fast; transport/5xx
  → retry → `IngestUnavailable`).
- **Config** (`config.py`) — `GARDA_` settings; `ingest_token` required (fail-fast); pacing knobs.
- **Observability** (`observability.py`) — structlog JSON logging.

## Relationships & boundaries

- Talks to the backend **only** over the `/api/v1/ingest` HTTP contract (shared by contract, not by
  code — **no import of any other service**). No DB, no Redis, no scorer.
- The backend does all scoring / persistence / publishing; the sim only produces input.
- Runs **after** the reference seed (`garda-ai-ingest`, Phase 3) so account/bank FKs resolve; the
  backend 400s on any unknown reference.
- Owns pacing/speed/start-stop locally — this is where the old replay worker's controls now live
  (no `sim_state`, no `/sim/*`).
```

- [ ] **Step 4: Write `docs/c4/04-code.md`**

```markdown
# garda-ai-sim — C4 Code

## `config.py`
- `Settings(BaseSettings)` — `ingest_url`, `ingest_token` (required, min_length 1), `data_dir`,
  `trans_files`, `batch_size` (0<n≤1000), `speed` (>0), `max_gap_s` (≥0), `limit`, `dry_run`,
  `request_timeout_s`, `retries`, `log_level`.
- `get_settings() -> Settings` (lru_cache).

## `reader.py`
- `SimTxn(NamedTuple)` — `ordinal: int`, `csv_ts: datetime`, `fields: dict[str, object]`.
- `stream_transactions(paths, *, limit=None) -> Iterator[SimTxn]` — continuous ordinal id,
  UTC timestamps, ingest fields minus `event_time`.

## `client.py`
- `IngestSummary(NamedTuple)` — `ingested, duplicate: int`.
- `IngestError` / `IngestUnavailable`.
- `IngestClient(client, url, token, *, retries=3, timeout_s=30.0)`;
  `send(txns, *, correlation_id) -> IngestSummary`.

## `producer.py`
- `SimStats(dataclass)` — `batches, sent, ingested, duplicate`.
- `Producer(client, *, speed, max_gap_s, batch_size, sleep=…, now=…, new_correlation_id=…)`;
  `run(rows, *, dry_run=False) -> SimStats`.

## `run.py`
- `run_sim(settings) -> None` — resolve paths (missing → `SystemExit(2)`); stream → produce;
  `IngestError`/`IngestUnavailable` → `SystemExit(1)`; else log `sim.done`.
- `main() -> None` — CLI entrypoint; graceful `KeyboardInterrupt`.

## `observability.py`
- `configure_logging(level="INFO") -> None` — structlog JSON.
```

- [ ] **Step 5: Verify CI steps locally**

Run: `uv run ruff check . && uv run mypy garda_ai_sim && uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: Dockerfile (local-only), CI, C4 component + code docs"
```

---

## Definition of Done

- `uv run pytest -q` green (config, reader, client, producer, run — ~16 tests).
- `uv run ruff check .` clean; `uv run mypy garda_ai_sim` clean under `--strict`.
- `garda-sim` streams the Trans CSV as paced batches to `/api/v1/ingest`; `event_time = now`;
  `transaction_id` = stable ordinal; pacing = `clamp(csv_gap / speed, 0, max_gap_s)`.
- Exit codes: 0 ok / interrupted · 1 backend rejected/unreachable · 2 missing CSV — all reachable.
- No import of any other service; the backend is reached only via the `/api/v1/ingest` HTTP contract.
- All commits authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer.
```
