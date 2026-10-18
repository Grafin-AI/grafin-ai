import pytest
from pydantic import ValidationError

from grafin_ai_sim.config import Settings


def test_requires_ingest_token(monkeypatch):
    monkeypatch.delenv("GRAFIN_INGEST_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_empty_token(monkeypatch):
    monkeypatch.setenv("GRAFIN_INGEST_TOKEN", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.setenv("GRAFIN_INGEST_TOKEN", "tok")
    s = Settings(_env_file=None)
    assert s.ingest_url.endswith("/api/v1/ingest")
    assert s.batch_size == 100
    assert s.speed == 60.0
    assert s.max_gap_s == 2.0
    assert s.limit is None
    assert s.dry_run is False
    assert s.log_level == "INFO"


def test_rejects_nonpositive_speed(monkeypatch):
    monkeypatch.setenv("GRAFIN_INGEST_TOKEN", "tok")
    monkeypatch.setenv("GRAFIN_SPEED", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_invalid_log_level(monkeypatch):
    monkeypatch.setenv("GRAFIN_INGEST_TOKEN", "tok")
    monkeypatch.setenv("GRAFIN_LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
