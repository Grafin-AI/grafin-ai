from grafin_ai_scoring.scoring.deterministic import TYPOLOGIES, status_for, unit_hash


def test_unit_hash_in_range_and_stable():
    a = unit_hash("k1")
    assert 0.0 <= a < 1.0
    assert unit_hash("k1") == a
    assert unit_hash("k2") != a


def test_status_thresholds():
    assert status_for(0.95) == "blocked"
    assert status_for(0.80) == "blocked"
    assert status_for(0.60) == "flagged"
    assert status_for(0.50) == "flagged"
    assert status_for(0.10) == "approved"


def test_typologies_nonempty():
    assert "Fan-Out" in TYPOLOGIES and "Smurfing" in TYPOLOGIES
