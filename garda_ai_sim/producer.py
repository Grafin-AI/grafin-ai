import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
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
        new_correlation_id: Callable[[], str] | None = None,
    ) -> None:
        self._client = client
        self._speed = speed
        self._max_gap_s = max_gap_s
        self._batch_size = batch_size
        self._sleep = sleep
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
            payloads: list[dict[str, object]] = [
                {**t.fields, "transaction_id": t.ordinal, "event_time": t.csv_ts.isoformat()}
                for t in batch
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
