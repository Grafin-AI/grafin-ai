import pytest
from pydantic import ValidationError

from garda_ai_ingest.config import Settings


def test_requires_database_url(monkeypatch):
    monkeypatch.delenv("GARDA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_DATABASE_URL", "postgresql://u:p@h:5432/db")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql://u:p@h:5432/db"
    assert s.data_dir == "../garda-ai-data/HI-Small"
    assert s.batch_size == 5000
