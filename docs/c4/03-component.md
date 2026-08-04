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
