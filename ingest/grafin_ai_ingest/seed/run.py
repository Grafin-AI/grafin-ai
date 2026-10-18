"""One-shot reference-data seed.

Loads banks/entities(+province)/accounts into the backend-owned Postgres, idempotently
(``ON CONFLICT DO NOTHING``). Run once before the sim streams transactions so FK references
resolve. Assumes the schema is already migrated (the backend owns migrations).

Invoke: ``uv run grafin-ingest`` or ``uv run python -m grafin_ai_ingest.seed.run``.

Exit codes: 0 ok · 1 validation failed · 2 accounts CSV not found · 3 reference tables not found.
"""

import asyncio
import os
import time

import asyncpg
import structlog

from grafin_ai_ingest.config import get_settings
from grafin_ai_ingest.db import connect
from grafin_ai_ingest.observability import configure_logging
from grafin_ai_ingest.seed.reference import load_reference
from grafin_ai_ingest.seed.validate import ValidationReport, validate

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
    settings = get_settings()
    configure_logging(settings.log_level)
    report = asyncio.run(
        run_seed(settings.data_dir, settings.database_url, batch_size=settings.batch_size)
    )
    if not report.ok:
        log.error("seed.failed", **report.as_dict())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
