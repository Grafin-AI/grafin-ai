from garda_ai_backend.schema import Base, Bank, Entity, Account


def test_reference_tables_registered():
    tables = Base.metadata.tables
    assert "banks" in tables
    assert "entities" in tables
    assert "accounts" in tables
    cols = {c.name for c in tables["accounts"].columns}
    assert {"id", "bank_id", "entity_id", "risk_score", "risk_category"} <= cols
    assert "province" in {c.name for c in tables["entities"].columns}
