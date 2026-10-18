import re

import pytest

from grafin_ai_backend.services.explain import knowledge as kb


def test_entries_shape_and_no_article_citations():
    assert 10 <= len(kb.ENTRIES) <= 14
    ids = [e["id"] for e in kb.ENTRIES]
    assert len(ids) == len(set(ids))
    for e in kb.ENTRIES:
        assert e["title"] and e["text"] and e["tags"]
        # Paraphrased summaries only: no "Pasal 12" / "ayat (1)" style citations.
        assert not re.search(r"\b(pasal|ayat)\b", e["text"], re.IGNORECASE), e["id"]


def test_retrieve_includes_general_entries_and_caps():
    codes = [
        "high_model_score", "typology_detected", "high_fan_in", "high_fan_out",
        "high_velocity", "unusual_amount", "cross_bank", "flagged_counterparty",
    ]
    got = [e["id"] for e in kb.retrieve(codes, "Fan-In")]
    assert len(got) == kb.MAX_REFERENCES
    assert set(kb.GENERAL_IDS) <= set(got)
    assert got[0] == "tipologi-fan-in"  # typology match has priority


def test_retrieve_no_factors_only_general():
    got = [e["id"] for e in kb.retrieve([], None)]
    assert got == list(kb.GENERAL_IDS)


def test_retrieve_extra_ids_pinned():
    got = [e["id"] for e in kb.retrieve(["high_fan_out"], "Smurfing", [kb.REPORTING_ID])]
    assert kb.REPORTING_ID in got and "tipologi-fan-out" in got
    assert len(got) <= kb.MAX_REFERENCES


@pytest.mark.parametrize("typ,tag", [
    ("Fan-In", "fan_in"), ("Fan-Out", "fan_out"), ("Smurfing", "fan_out"),
    ("Cycle", "cycle"), ("Gather-Scatter", "gather_scatter"), ("Mule Account", "fan_in"),
    ("Layering", "layering"), ("Trade-Based", "network"), (None, None),
])
def test_typology_tag(typ, tag):
    assert kb.typology_tag(typ) == tag


@pytest.mark.parametrize("typ,codes,expected", [
    ("Fan-In", ["high_fan_in", "high_fan_out"], "GA-FANIN"),
    (None, ["high_fan_in", "high_fan_out"], "GA-GATHER"),
    ("Cycle", [], "GA-CYCLE"),
    (None, ["high_velocity"], "GA-VELOCITY"),
    (None, ["unusual_amount"], "GA-AMOUNT"),
    ("Trade-Based", ["typology_detected"], "GA-NETWORK"),
    (None, ["cross_bank"], "GA-NORMAL"),
    (None, [], "GA-NORMAL"),
])
def test_deterministic_reason_code(typ, codes, expected):
    assert kb.deterministic_reason_code(typ, codes) == expected


def test_confidence_from_score():
    assert kb.confidence_from_score(0.85) == "Tinggi"
    assert kb.confidence_from_score(0.6) == "Sedang"
    assert kb.confidence_from_score(0.59) == "Rendah"


def test_normalizers():
    assert kb.normalize_reason_code(" ga-fanin ") == "GA-FANIN"
    assert kb.normalize_reason_code("GA-BOGUS") is None
    assert kb.normalize_reason_code(3) is None
    assert kb.normalize_confidence("tinggi") == "Tinggi"
    assert kb.normalize_confidence("high") is None


def test_filter_references():
    allowed = kb.retrieve(["high_fan_in"], "Fan-In")
    out = kb.filter_references(
        ["tipologi-fan-in", "bogus", "tipologi-fan-in", {"id": "uu-tppu-umum"},
         "faktor-nominal"],  # faktor-nominal exists but was not provided -> dropped
        allowed,
    )
    assert out == [
        {"id": "tipologi-fan-in", "title": kb.BY_ID["tipologi-fan-in"]["title"]},
        {"id": "uu-tppu-umum", "title": kb.BY_ID["uu-tppu-umum"]["title"]},
    ]
    assert kb.filter_references(["bogus"], allowed) is None
    assert kb.filter_references("tipologi-fan-in", allowed) is None
