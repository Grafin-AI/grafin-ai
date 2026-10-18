# grafin-ai-sim — Local Simulation Producer (Phase 4)

**Date:** 2026-06-25
**Status:** Approved (brainstorming)
**Repo:** `grafin-ai-sim` (NEW)
**Anchor spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-25-platform-rearchitecture-design.md`
**Depends on:** the backend `POST /api/v1/ingest` HTTP contract (Phase 2) — by contract, not by code.

Phase 4 of the platform re-architecture. Extract the pipeline's replay/producer into a
**local-only CLI producer** that reads the HI-Small transactions CSV and streams **batches** to the
backend's `/api/v1/ingest` (bearer ingest token). It **owns pacing, speed, and start/stop locally**
— replacing the old DB-persisted `sim_state` accelerated clock. It is **never deployed** (a demo/dev
data source); it points at a local *or* a deployed backend via base-URL config.

The old replay worker read already-bulk-loaded transactions from the DB, scored them itself, wrote
events, and advanced a DB clock. In the new architecture the **backend** scores + persists +
publishes; the sim only **produces input**. So the sim sheds the DB, Redis, the scorer, and
`sim_state` entirely — it is a CSV reader + a paced HTTP client.

## Streaming model — "now-stamped, real cadence" (the chosen design)

- **`event_time = wall-clock now` at emission.** Every transaction is stamped with the current time
  when its batch is sent, so the dashboard's time-windowed views ("last hour", "today") fill up
  live and Phase 5 needs no display re-anchoring.
- **Pacing reproduces the CSV's real rhythm, compressed.** The wall delay between consecutive
  batches = (CSV-timestamp span the batch advances) ÷ `speed`, **clamped to `[0, max_gap_s]`**.
  This preserves bursts/quiet periods from the real data without long dead air. Negative gaps
  (the HI-Small CSV is not strictly time-ordered) clamp to 0.
- **`speed`** is a throughput multiplier (e.g. `60×` → one CSV hour plays in one wall minute, before
  the `max_gap_s` cap). **`max_gap_s`** caps any single inter-batch wait (default 2.0s) so a
  multi-hour quiet spell can't stall the demo.
- **play/pause/stop is local:** the process itself is the control — start it to play, `Ctrl-C` to
  stop (graceful). `--limit N` and `--dry-run` support quick demos/tests. There is **no** interactive
  control server and **no** `sim_state` (the admin Simulation UI is removed in Phase 5). This is the
  anchor spec's "owns the clock, speed, and play/pause locally (CLI flags / config)".

## Configuration — `grafin_ai_sim/config.py`

pydantic-settings, `env_prefix="GRAFIN_"`, `.env` supported, `extra="ignore"`:

- `ingest_url: str = "http://localhost:8000/api/v1/ingest"` — the backend ingest **endpoint** URL
  (full URL; repoint at a deployed backend via env).
- `ingest_token: str` — **required** (`min_length=1`), presented as `Authorization: Bearer`.
  Fail-fast: a misconfigured run crashes at startup rather than hammering the backend with 401s.
- `data_dir: str = "../grafin-ai-data/HI-Small"` — directory holding the Trans CSV parts.
- `trans_files: list[str] = ["HI-Small_Trans_part1.csv", "HI-Small_Trans_part2.csv"]` — read in
  order; the `transaction_id` ordinal is **continuous across parts** (so ids stay unique + stable).
- `batch_size: int = 100` — transactions per `/ingest` POST (`≤ 1000`, the ingest cap).
- `speed: float = 60.0` — pacing multiplier (`> 0`).
- `max_gap_s: float = 2.0` — clamp on any single inter-batch wait.
- `limit: int | None = None` — stop after N transactions (demos/tests).
- `dry_run: bool = False` — build + log batches but do **not** POST.
- `request_timeout_s: float = 30.0`, `retries: int = 3` — HTTP client resilience knobs.

## CSV reader — `grafin_ai_sim/reader.py`

Ported/adapted from the pipeline's `etl.transactions._rows` (same column contract: `Timestamp`
`%Y/%m/%d %H:%M` → UTC, `From Bank`/`Account`/`To Bank`/`To Account`, `Amount Paid`/`Amount
Received` as `Decimal`, `Payment Currency`/`Receiving Currency`, `Payment Format`, `Is Laundering`
== "1"). Streams (never materializes) so the ~2.5M-row parts cost negligible memory.

```
class SimTxn(NamedTuple):
    ordinal: int          # 1-based, continuous across parts -> the producer-provided transaction_id
    csv_ts: datetime      # the original CSV timestamp (used ONLY for pacing, never sent)
    fields: dict          # from_bank_id, from_account, to_bank_id, to_account, amount_paid,
                          # payment_currency, amount_received, receiving_currency, payment_format,
                          # is_laundering  (NO event_time — the producer stamps it at emission)

def stream_transactions(paths: list[str], *, limit: int | None = None) -> Iterator[SimTxn]
```
`transaction_id = ordinal` — a stable, monotonic producer id (the CSV has no id column). Stable
across runs (same file order) ⇒ a retried batch is idempotent on the backend (Phase 2's
`ON CONFLICT DO NOTHING`). `amount_*` are serialized as strings so the backend's `Decimal` fields
parse exactly (no float rounding).

## Ingest client — `grafin_ai_sim/client.py`

A thin wrapper over a **pooled** httpx `AsyncClient`:
```
class IngestError(Exception): ...        # non-retryable (4xx: bad token / contract)
class IngestUnavailable(Exception): ...  # retries exhausted (transport / 5xx)

class IngestClient:
    async def send(self, txns: list[dict], *, correlation_id: str) -> IngestSummary
```
- `POST {ingest_url}` with `Authorization: Bearer {ingest_token}` and `X-Correlation-ID:
  {correlation_id}` (a per-batch uuid4, so sim→ingest→scoring traces end-to-end).
- Body `{"transactions": [...]}`; parses the response into `IngestSummary(ingested, duplicate)`
  by counting `results[].ingested`.
- **Resilience** (mirrors the backend's `ScoringClient`): timeout `request_timeout_s`; retry up to
  `retries` on `httpx.TransportError` **or** any 5xx, with exponential backoff
  (`sleep 0.5 * 2**attempt`); a **4xx is NOT retried** → raise `IngestError` immediately
  (401 bad token, 422 contract mismatch — retrying is pointless). Exhausted retries → raise
  `IngestUnavailable`.
- Reuses one `AsyncClient` created at startup and closed on shutdown (connection pooling; no
  per-request client).

## Producer — `grafin_ai_sim/producer.py`

The pacing loop. Dependency-injects `sleep` and `now` so pacing is deterministically testable:
```
@dataclass
class SimStats:
    batches: int; sent: int; ingested: int; duplicate: int

class Producer:
    def __init__(self, client, *, speed, max_gap_s, batch_size,
                 sleep=asyncio.sleep, now=lambda: datetime.now(UTC)): ...
    async def run(self, rows: Iterable[SimTxn], *, dry_run: bool = False) -> SimStats
```
Algorithm (batch by count, delay by the CSV span the batch advanced):
1. Accumulate `SimTxn`s into a batch until `batch_size`.
2. Before sending (except the first batch), wait
   `delay = clamp((batch.first.csv_ts - prev_batch_last_csv_ts) / speed, 0, max_gap_s)` via the
   injected `sleep`.
3. Stamp each txn: `payload = {**t.fields, "transaction_id": t.ordinal,
   "event_time": now().isoformat()}`; POST the batch (or, `dry_run`, just log it).
4. Accumulate stats; `log.info("sim.batch", ...)` with running throughput. Remember
   `prev_batch_last_csv_ts = batch.last.csv_ts`.
5. Flush the final partial batch. Return `SimStats`.

`speed` must be `> 0` (validated in config). The whole run is bounded by `limit` if set.

## Orchestration + CLI — `grafin_ai_sim/run.py`

Console entrypoint (`grafin-sim` + `python -m grafin_ai_sim.run`):
- `configure_logging(settings.log_level)`; resolve the Trans paths under `data_dir`.
- **Missing CSV** (no part files exist) → clear `sim.error` log + `SystemExit(2)`.
- Build the pooled `AsyncClient` (with `request_timeout_s`), the `IngestClient`, and the `Producer`;
  run over `stream_transactions(paths, limit=...)`; log a `sim.done` summary (batches, sent,
  ingested, duplicate, duration_s); always `aclose()` the client in a `finally`.
- **`IngestError` / `IngestUnavailable`** (backend rejects or is unreachable after retries) →
  clear `sim.error` log + `SystemExit(1)` (fail loud — a local operator must know the backend is
  down, not silently drop data).
- Graceful `KeyboardInterrupt` (Ctrl-C) → log a partial summary and exit 0.

Exit codes: `0` ok / interrupted · `1` backend rejected or unreachable · `2` Trans CSV not found.

## Observability — `grafin_ai_sim/observability.py`

Structured logging only (a local CLI tool, no metrics server — same rationale as the ingest job):
`configure_logging(level)` mirroring the scoring/ingest structlog JSON config. Per-batch throughput
logs + a final run summary. A per-batch correlation id ties the sim into the backend's
correlation-aware ingest/scoring logs.

## Testing

`pytest` + `pytest-asyncio` (auto mode). **No DB, no testcontainers** — the sim has no datastore;
the backend is mocked at the HTTP layer.

- `test_reader.py` — `stream_transactions` over a small sample CSV: correct field mapping,
  `is_laundering` bool, `Decimal` amounts, 1-based ordinals **continuous across two parts**,
  `limit` respected, timestamps parsed to UTC.
- `test_client.py` — httpx `MockTransport`: a 200 maps the response to `IngestSummary`
  (ingested/duplicate counts); the `Authorization: Bearer` + `X-Correlation-ID` headers are sent;
  a 503 retries `retries` times then raises `IngestUnavailable`; a 401/422 raises `IngestError`
  **without** retrying (assert the call count).
- `test_producer.py` — inject a fake `sleep` (records the delays) and a fixed `now`: assert the
  pacing math (a known set of `csv_ts` gaps + `speed` + `max_gap_s` → the expected clamped delays,
  negative gaps → 0, huge gaps → `max_gap_s`); batches are the right size; `event_time` is stamped
  from `now`; `transaction_id` equals the ordinal; `dry_run=True` performs **no** POST; `SimStats`
  totals are correct.
- `test_run.py` — missing CSV path → `SystemExit(2)`; an `IngestUnavailable` from a stub client →
  `SystemExit(1)`; a happy path over a tiny CSV with a stub client returns an ok summary.

`tests/data/trans_sample_part1.csv` / `_part2.csv` — small fixtures (a handful of rows with known
timestamps/gaps, including an out-of-order row to exercise the negative-gap clamp), derived from the
pipeline's `trans_sample.csv`.

## Engineering standards (plugin conformance)

Same bar as Phases 1–3 (`backend-development`, `python-development`, `observability-monitoring`):
- **python-development:** uv, `ruff` (line-length 100), `mypy --strict` + pydantic plugin, 3.12,
  `pytest-asyncio`. Typed boundaries (`SimTxn`, `IngestSummary`, `SimStats`) — no bare dicts across
  seams except the JSON payload built for the wire.
- **python-resilience:** a single pooled `AsyncClient`; per-batch timeout + bounded retries +
  backoff; typed `IngestError` (fail-fast, 4xx) vs `IngestUnavailable` (retryable-exhausted, → exit 1).
- **python-error-handling:** fail-fast config; a clear exit-code taxonomy (0/1/2); no swallowed
  errors; graceful Ctrl-C.
- **observability-monitoring:** structured throughput + summary logs; a correlation id propagated
  to the backend. (Local CLI → logs, not a metrics server.)
- **security (backend-security-coder):** the ingest token is read **only** from settings and is
  **never logged**; no injection surface (payloads are JSON via httpx, not string-built); the tool
  takes no untrusted network input.

## Packaging / ops

- `pyproject.toml` (hatchling, uv) mirroring the scoring/ingest bar: deps `httpx`,
  `pydantic-settings`, `structlog`; dev `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
  `[project.scripts] grafin-sim = "grafin_ai_sim.run:main"`.
- `Dockerfile` — **for local `docker compose` convenience only** (Phase 6 compose runs it against
  the local backend); clearly marked local-only, non-root, runs `grafin-sim` to completion.
- `.github/workflows/ci.yml` — ruff + mypy + pytest (mirrors scoring/ingest). `README.md`,
  `.env.example`, `.gitignore`, `.dockerignore`, `.python-version`.
- `docs/c4/{03-component,04-code}.md`.

## Build order

Subagent-driven, `python-pro`/`fastapi-pro` implementer + `code-reviewer` and `security-auditor`
review gates (the HTTP client + token handling + resilience warrant a security/quality pass, per
the pattern that caught real issues in Phases 1–2).

## Out of scope (YAGNI / later phases)

- **Removing `sim_state`/`/sim` from the backend and the Simulation page from the frontend** —
  Phase 5. This phase only *adds* the new producer; the old replay worker still exists until Phase 5.
- **Interactive control (live speed/pause API, TUI)** — the local process *is* the control
  (run / Ctrl-C / config). A control surface would reintroduce the `sim_state` coupling we're removing.
- **A message queue between sim and backend** — direct HTTP `/ingest` batches (anchor decision).
- **Retry/resume from a checkpoint** — a re-run restarts from the top; idempotent ids mean already-
  ingested transactions are no-ops on the backend, so a restart is safe without checkpointing.
- **Reference/account seeding** — that is `grafin-ai-ingest` (Phase 3); the sim assumes accounts are
  seeded (HI-Small has 0 orphan account/bank refs, verified) and the backend 400s on any unknown ref.
