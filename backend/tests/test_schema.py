from grafin_ai_backend.schema import Base, Bank, Entity, Account


def test_reference_tables_registered():
    tables = Base.metadata.tables
    assert "banks" in tables
    assert "entities" in tables
    assert "accounts" in tables
    cols = {c.name for c in tables["accounts"].columns}
    assert {"id", "bank_id", "entity_id", "risk_score", "risk_category"} <= cols
    assert "province" in {c.name for c in tables["entities"].columns}


def test_transaction_tables_registered():
    from grafin_ai_backend.schema import Transaction, TransactionEvent
    tables = Base.metadata.tables
    txn_cols = {c.name for c in tables["transactions"].columns}
    assert {"id", "event_time", "from_account", "to_account",
            "amount_paid", "is_laundering"} <= txn_cols
    ev_cols = {c.name for c in tables["transaction_events"].columns}
    assert {"seq", "transaction_id", "surfaced_at", "event_time",
            "fraud_score", "typology", "status"} <= ev_cols


def test_ops_tables_registered():
    from grafin_ai_backend.schema import Alert, User
    tables = Base.metadata.tables
    assert {"id", "event_seq", "severity", "typology"} <= {c.name for c in tables["alerts"].columns}
    assert {"id", "email", "password_hash", "role"} <= {c.name for c in tables["users"].columns}
