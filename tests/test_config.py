import pytest
from pydantic import ValidationError

from garda_ai_scoring.config import Settings


def test_settings_require_token(monkeypatch):
    monkeypatch.delenv("GARDA_SCORING_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        Settings()


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", "s3cret")
    s = Settings()
    assert s.scoring_token == "s3cret"
    assert s.scorer == "label_replay"
    assert s.seed == "garda"
    assert s.fn_rate == 0.05
    assert s.fp_rate == 0.04
