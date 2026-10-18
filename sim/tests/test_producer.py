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

    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=1,
        sleep=fake_sleep, new_correlation_id=lambda: "cid",
    )
    # gaps between csv_ts: b1->b2 = 1min (60s/60 = 1.0s); b2->b3 = 5min (300/60 = 5.0 -> clamp 2.0);
    # b3->b4 = 0min (0.0 -> no sleep)
    rows = [_txn(1, 0), _txn(2, 1), _txn(3, 6), _txn(4, 6)]
    stats = await producer.run(rows)

    assert stats == SimStats(batches=4, sent=4, ingested=4, duplicate=0)
    assert delays == [1.0, 2.0]           # first batch no wait; 0.0 gaps not slept; 5min clamped to 2.0
    first_payload = client.calls[0][0][0]
    assert first_payload["transaction_id"] == 1
    assert first_payload["event_time"] == "2025-09-01T00:00:00+00:00"   # the row's own CSV time
    assert first_payload["from_bank_id"] == "10"


async def test_dry_run_posts_nothing():
    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=10,
        sleep=_noop_sleep, new_correlation_id=lambda: "cid",
    )
    stats = await producer.run([_txn(1, 0), _txn(2, 0)], dry_run=True)
    assert client.calls == []
    assert stats.sent == 2
    assert stats.batches == 1


async def test_event_time_is_per_row_csv_timestamp():
    """event_time must be each row's own CSV timestamp — not the wall clock, and not a
    single stamp shared across the batch. The dashboard plots the dataset's timeline."""
    client = StubClient()
    producer = Producer(
        client, speed=60.0, max_gap_s=2.0, batch_size=10,
        sleep=_noop_sleep, new_correlation_id=lambda: "cid",
    )
    await producer.run([_txn(1, 0), _txn(2, 5)])

    sent = client.calls[0][0]          # (txns, correlation_id) of the first call
    assert sent[0]["event_time"] == "2025-09-01T00:00:00+00:00"
    assert sent[1]["event_time"] == "2025-09-01T00:05:00+00:00"


async def _noop_sleep(_d: float) -> None:
    return None
