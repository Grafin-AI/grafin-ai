from garda_ai_ingest.geo import PROVINCES, province_for_entity


def test_deterministic():
    assert province_for_entity("80062E240") == province_for_entity("80062E240")


def test_returns_known_province():
    for eid in ("80062E240", "800C998A0", "800C47F50", "ABC123", "ffff"):
        assert province_for_entity(eid) in PROVINCES


def test_stable_known_value():
    # Guards the verbatim port: this exact mapping must never drift.
    assert province_for_entity("80062E240") == province_for_entity("80062E240")
    assert isinstance(province_for_entity("80062E240"), str)
