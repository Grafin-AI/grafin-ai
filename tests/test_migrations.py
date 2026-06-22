from alembic.config import Config
from alembic.script import ScriptDirectory

from garda_ai_backend.schema import Base


def test_migration_covers_all_tables():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head is not None, "no migration generated"
    head_src = script.get_revision(head).module.__file__
    text = open(head_src).read()
    for table in Base.metadata.tables:
        assert table in text, f"{table} missing from migration"
