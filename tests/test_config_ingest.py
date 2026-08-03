import pytest
from pydantic import ValidationError

from garda_ai_backend.config import Settings

_BASE = {
    "database_url": "postgresql+asyncpg://u:p@localhost/db",
    "scoring_url": "http://scoring:8000",
    "scoring_token": "s",
    "ingest_token": "i",
}


@pytest.fixture(autouse=True)
def _clear_ingest_env(monkeypatch):
    # conftest injects GARDA_* into os.environ (setdefault) so the app can boot
    # in the full suite. For THIS module we must observe an absent environment
    # so the "required field raises" assertions are meaningful — the values here
    # come exclusively from the kwargs passed to Settings(**...).
    for key in ("GARDA_SCORING_URL", "GARDA_SCORING_TOKEN", "GARDA_INGEST_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_ingest_settings_defaults():
    s = Settings(**_BASE)
    assert s.scoring_url == "http://scoring:8000"
    assert s.scoring_token == "s"
    assert s.ingest_token == "i"
    assert s.scoring_timeout_s == 5.0
    assert s.scoring_retries == 2


@pytest.mark.parametrize("missing", ["scoring_url", "scoring_token", "ingest_token"])
def test_ingest_settings_required(missing):
    data = {k: v for k, v in _BASE.items() if k != missing}
    with pytest.raises(ValidationError):
        Settings(**data)
