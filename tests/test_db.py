from garda_ai_ingest.db import asyncpg_dsn


def test_strips_sqlalchemy_asyncpg_scheme():
    assert asyncpg_dsn("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_leaves_bare_dsn_untouched():
    assert asyncpg_dsn("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
