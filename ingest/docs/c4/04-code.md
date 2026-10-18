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
