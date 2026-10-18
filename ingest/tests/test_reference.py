import os

from grafin_ai_ingest.geo import province_for_entity
from grafin_ai_ingest.seed.reference import load_reference


async def test_loads_banks_entities_accounts(db, data_dir):
    counts = await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))

    assert await db.fetchval("SELECT count(*) FROM banks") == 2
    assert await db.fetchval("SELECT count(*) FROM entities") == 3
    assert await db.fetchval("SELECT count(*) FROM accounts") == 3
    assert (counts.banks, counts.entities, counts.accounts) == (2, 3, 3)

    row = await db.fetchrow(
        "SELECT bank_id, entity_id, risk_score, risk_category FROM accounts WHERE id='8000F4670'"
    )
    assert row["bank_id"] == "10"
    assert row["entity_id"] == "800C47F50"
    assert float(row["risk_score"]) == 8.0
    assert row["risk_category"] == "High"

    prov = await db.fetchval("SELECT province FROM entities WHERE id='80062E240'")
    assert prov == province_for_entity("80062E240")


async def test_idempotent(db, data_dir):
    path = os.path.join(data_dir, "accounts_sample.csv")
    await load_reference(db, path)
    await load_reference(db, path)
    assert await db.fetchval("SELECT count(*) FROM accounts") == 3
    assert await db.fetchval("SELECT count(*) FROM banks") == 2


async def test_do_nothing_never_overwrites_existing(db, data_dir):
    # Pre-seed the account with a DIFFERENT risk_category; the loader must NOT overwrite it.
    await db.execute("INSERT INTO banks (id, name) VALUES ('10', 'Pre')")
    await db.execute("INSERT INTO entities (id, name, province) VALUES ('800C47F50', 'Pre', 'Bali')")
    await db.execute(
        "INSERT INTO accounts (id, bank_id, entity_id, risk_score, risk_category) "
        "VALUES ('8000F4670', '10', '800C47F50', 0, 'Low')"
    )

    await load_reference(db, os.path.join(data_dir, "accounts_sample.csv"))

    row = await db.fetchrow("SELECT risk_category, risk_score FROM accounts WHERE id='8000F4670'")
    assert row["risk_category"] == "Low"      # unchanged — DO NOTHING
    assert float(row["risk_score"]) == 0.0    # unchanged
