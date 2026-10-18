import os

from garda_ai_ingest.seed.reference import load_reference
from garda_ai_ingest.seed.validate import validate


async def test_ok_after_good_load(db, data_dir):
    await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))
    report = await validate(db)
    assert report.ok is True
    assert report.banks == 2
    assert report.entities == 3
    assert report.accounts == 3
    assert report.entities_without_province == 0
    assert report.orphan_account_refs == 0


async def test_not_ok_on_empty_db(db):
    report = await validate(db)
    assert report.ok is False
    assert report.banks == 0
