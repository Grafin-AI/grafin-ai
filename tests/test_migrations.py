from alembic.config import Config
from alembic.script import ScriptDirectory

from garda_ai_backend.schema import Base


def test_migration_covers_all_tables():
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    assert head is not None, "no migration generated"
    # Aggregate across the whole revision chain: tables may be created in an
    # earlier migration and later ones only alter/drop (e.g. dropping sim_state).
    text = "".join(
        open(rev.module.__file__).read() for rev in script.walk_revisions()
    )
    for table in Base.metadata.tables:
        assert table in text, f"{table} missing from migration"
