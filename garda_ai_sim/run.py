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
