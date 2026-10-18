import pytest
from pydantic import ValidationError

from grafin_ai_ingest.config import Settings


def test_requires_database_url(monkeypatch):
    monkeypatch.delenv("GRAFIN_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("GRAFIN_DATABASE_URL", "postgresql://u:p@h:5432/db")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql://u:p@h:5432/db"
    assert s.data_dir == "../grafin-ai-data/HI-Small"
    assert s.batch_size == 5000
    assert s.log_level == "INFO"


def test_log_level_from_env(monkeypatch):
    monkeypatch.setenv("GRAFIN_DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("GRAFIN_LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"
