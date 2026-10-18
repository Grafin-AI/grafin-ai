from types import SimpleNamespace

import asyncpg
import pytest

from garda_ai_ingest.db import asyncpg_dsn
from garda_ai_ingest.seed import run as run_mod
from garda_ai_ingest.seed.run import run_seed
from garda_ai_ingest.seed.validate import ValidationReport


async def test_run_seed_ok(db, pg_url, data_dir):
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


async def test_missing_csv_exits_2(pg_url, tmp_path):
    # run_seed exits at the CSV existence check before it ever connects; pg_url only supplies
    # a valid DSN string.
    with pytest.raises(SystemExit) as exc:
        await run_seed(str(tmp_path), asyncpg_dsn(pg_url), batch_size=5000)
    assert exc.value.code == 2


async def test_undefined_table_exits_3(pg_url, data_dir):
    # No `db` fixture: the reference tables must be ABSENT so load hits UndefinedTableError.
    dsn = asyncpg_dsn(pg_url)
    conn = await asyncpg.connect(dsn)
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await conn.close()
    with pytest.raises(SystemExit) as exc:
        await run_seed(data_dir, dsn, batch_size=5000)
    assert exc.value.code == 3


def test_main_exits_1_on_not_ok(monkeypatch):
    report = ValidationReport(
        banks=0, entities=0, accounts=0,
        entities_without_province=0, orphan_account_refs=0, ok=False,
    )

    async def fake_run(*a, **k):
        return report

    monkeypatch.setattr(
        run_mod, "get_settings",
        lambda: SimpleNamespace(data_dir="x", database_url="y", batch_size=1, log_level="INFO"),
    )
    monkeypatch.setattr(run_mod, "run_seed", fake_run)
    with pytest.raises(SystemExit) as exc:
        run_mod.main()
    assert exc.value.code == 1
