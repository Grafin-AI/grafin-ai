import pytest

from grafin_ai_scoring.scoring import ScoringProvider
from grafin_ai_scoring.scoring.factory import get_scorer
from grafin_ai_scoring.scoring.label_replay import LabelReplayScorer


def test_get_label_replay():
    s = get_scorer("label_replay")
    assert isinstance(s, LabelReplayScorer)
    assert isinstance(s, ScoringProvider)


def test_unknown_scorer_raises():
    with pytest.raises(ValueError, match="unknown scorer"):
        get_scorer("nope")


def test_ml_not_yet_available():
    with pytest.raises(ValueError, match="not yet"):
        get_scorer("ml")
