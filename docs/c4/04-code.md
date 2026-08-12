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
- `Producer(client, *, speed, max_gap_s, batch_size, sleep=…, new_correlation_id=…)`;
  `run(rows, *, dry_run=False) -> SimStats` — each row is sent with its own `csv_ts` as
  `event_time`.

## `run.py`
- `run_sim(settings) -> None` — resolve paths (missing → `SystemExit(2)`); stream → produce;
  `IngestError`/`IngestUnavailable` → `SystemExit(1)`; else log `sim.done`.
- `main() -> None` — CLI entrypoint; graceful `KeyboardInterrupt`.

## `observability.py`
- `configure_logging(level="INFO") -> None` — structlog JSON.
