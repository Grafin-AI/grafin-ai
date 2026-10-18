from grafin_ai_dataset.geo import PROVINCES, province_for_entity


def test_matches_grafin_ai_ingest_known_values() -> None:
    # Values produced by grafin-ai-ingest/grafin_ai_ingest/geo.py on 2026-10-16.
    assert province_for_entity("80062E240") == "DKI Jakarta"
    assert province_for_entity("800C998A0") == "Jawa Tengah"
    assert province_for_entity("800C47F50") == "Jawa Tengah"
    assert province_for_entity("800FE9980") == "Sumatera Utara"


def test_fifteen_provinces() -> None:
    assert len(PROVINCES) == 15
