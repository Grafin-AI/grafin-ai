from datetime import UTC, datetime

import pytest

from garda_ai_backend.api import deps


@pytest.mark.asyncio
async def test_data_clock_returns_latest_event_time(session, seeded_dataset):
    """'Now' on the dataset timeline is the newest ingested event_time (11:00 in the fixture)."""
    assert await deps.get_data_now(session) == datetime(2025, 9, 1, 11, tzinfo=UTC)


@pytest.mark.asyncio
async def test_data_clock_falls_back_to_wall_clock_when_empty(session):
    """An empty database must not error — fall back to wall-clock now()."""
    before = datetime.now(UTC)
    value = await deps.get_data_now(session)
    assert value >= before
