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
    assert s.scores_path is None


def test_settings_precomputed(monkeypatch, tmp_path):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", "s3cret")
    monkeypatch.setenv("GARDA_SCORER", "precomputed")
    monkeypatch.setenv("GARDA_SCORES_PATH", str(tmp_path / "scores.csv"))
    s = Settings()
    assert s.scorer == "precomputed"
    assert s.scores_path == tmp_path / "scores.csv"


def test_settings_reject_unknown_scorer(monkeypatch):
    monkeypatch.setenv("GARDA_SCORING_TOKEN", "s3cret")
    monkeypatch.setenv("GARDA_SCORER", "nope")
    with pytest.raises(ValidationError):
        Settings()
