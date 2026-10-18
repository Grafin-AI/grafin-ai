from types import SimpleNamespace

import pytest

from grafin_ai_sim import run as run_mod
from grafin_ai_sim.client import IngestUnavailable

_HEADER = (
    "Timestamp,From Bank,Account,To Bank,To Account,Amount Received,"
    "Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering\n"
)
_ROW = "2025/09/01 00:00,10,A,20,B,1.00,IDR,1.00,IDR,ACH,0\n"


def _settings(**over):
    base = dict(
        ingest_url="http://x/api/v1/ingest", ingest_token="tok",
        data_dir="X", trans_files=["p1.csv"],
        batch_size=10, speed=60.0, max_gap_s=2.0, skip=0, limit=None, dry_run=False,
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
