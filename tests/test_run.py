import pytest

from garda_ai_ingest.db import asyncpg_dsn
from garda_ai_ingest.seed.run import run_seed


async def test_run_seed_ok(db, pg_url, data_dir, monkeypatch):
    # run_seed opens its own connection; point it at the container and the seeded schema
    # already created by the `db` fixture on the same database.
    report = await run_seed(data_dir, asyncpg_dsn(pg_url), batch_size=5000)
    assert report.ok is True
    assert report.accounts == 3


async def test_run_seed_idempotent(db, pg_url, data_dir):
    dsn = asyncpg_dsn(pg_url)
    await run_seed(data_dir, dsn, batch_size=5000)
    report = await run_seed(data_dir, dsn, batch_size=5000)
    assert report.ok is True
    assert report.accounts == 3


async def test_missing_csv_exits_2(db, pg_url, tmp_path):
    with pytest.raises(SystemExit) as exc:
        await run_seed(str(tmp_path), asyncpg_dsn(pg_url), batch_size=5000)
    assert exc.value.code == 2
