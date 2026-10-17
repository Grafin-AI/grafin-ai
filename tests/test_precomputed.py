import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from garda_ai_scoring.scoring import ScoringProvider
from garda_ai_scoring.scoring.factory import get_scorer
from garda_ai_scoring.scoring.precomputed import PrecomputedScorer
from garda_ai_scoring.scoring.types import ScoringContext, ScoringResult, TxnInput

SCORES = Path(__file__).parent / "data" / "scores.csv"
GNN = "Anomali Jaringan (GNN)"
CTX = ScoringContext()


def _txn(tid: int, is_laundering: bool = False) -> TxnInput:
    return TxnInput(
        transaction_id=tid,
        from_account="0009abc",
        to_account="0011def",
        amount=Decimal("15000.00"),
        payment_format="ACH",
        is_laundering=is_laundering,
        event_time=datetime(2025, 9, 12, tzinfo=UTC),
    )


@pytest.fixture(scope="module")
def scorer() -> PrecomputedScorer:
    return PrecomputedScorer(SCORES)


async def test_known_ids_return_their_values(scorer: PrecomputedScorer) -> None:
    assert len(scorer) == 3
    assert await scorer.score(_txn(42), CTX) == ScoringResult(0.8512, GNN, "blocked")
    assert await scorer.score(_txn(99), CTX) == ScoringResult(0.5, GNN, "flagged")
    assert await scorer.score(_txn(7), CTX) == ScoringResult(0.0123, None, "approved")


async def test_unknown_id_is_approved_zero(caplog: pytest.LogCaptureFixture) -> None:
    s = PrecomputedScorer(SCORES)
    with caplog.at_level(logging.WARNING):
        for tid in range(1000, 3001):
            assert await s.score(_txn(tid), CTX) == ScoringResult(0.0, None, "approved")
    assert s.misses == 2001
    assert len([r for r in caplog.records if "no score" in r.message]) == 3  # 1st, 1001st, 2001st


async def test_is_laundering_is_ignored(scorer: PrecomputedScorer) -> None:
    for tid in (7, 42, 99, 12345):
        assert await scorer.score(_txn(tid, True), CTX) == await scorer.score(_txn(tid), CTX)


async def test_unsorted_csv(tmp_path: Path) -> None:
    p = tmp_path / "s.csv"
    p.write_text(
        "transaction_id,fraud_score,prob,status,typology\n"
        "9,0.9,0.9,blocked,X\n3,0.1,0.1,approved,\n5,0.5,0.5,flagged,Y\n"
    )
    s = PrecomputedScorer(p)
    assert [(await s.score(_txn(t), CTX)).fraud_score for t in (3, 5, 9)] == [0.1, 0.5, 0.9]
    assert (await s.score(_txn(5), CTX)).typology == "Y"


def test_bad_files_raise(tmp_path: Path) -> None:
    p = tmp_path / "s.csv"
    p.write_text("id,score\n1,0.5\n")
    with pytest.raises(ValueError, match="expected header"):
        PrecomputedScorer(p)
    p.write_text("transaction_id,fraud_score,prob,status,typology\n1,0.5,0.5,maybe,\n")
    with pytest.raises(ValueError, match=r"s\.csv:2: bad status"):
        PrecomputedScorer(p)


def test_factory_selects_precomputed(tmp_path: Path) -> None:
    s = get_scorer("precomputed", scores_path=SCORES)
    assert isinstance(s, PrecomputedScorer) and isinstance(s, ScoringProvider)
    with pytest.raises(ValueError, match="GARDA_SCORES_PATH"):
        get_scorer("precomputed")
    with pytest.raises(ValueError, match="GARDA_SCORES_PATH"):
        get_scorer("precomputed", scores_path=tmp_path / "missing.csv")


@pytest.fixture
def precomputed_client(token, monkeypatch):
    from garda_ai_scoring.api.routes import _provider
    from garda_ai_scoring.config import get_settings

    monkeypatch.setenv("GARDA_SCORING_TOKEN", token)
    monkeypatch.setenv("GARDA_SCORER", "precomputed")
    monkeypatch.setenv("GARDA_SCORES_PATH", str(SCORES))
    get_settings.cache_clear()
    _provider.cache_clear()
    from garda_ai_scoring.api.app import app

    with TestClient(app) as c:  # runs the lifespan: scorer built at startup
        yield c
    get_settings.cache_clear()
    _provider.cache_clear()


def test_route_uses_precomputed_scores(precomputed_client, auth):
    base = {
        "from_account": "0009abc",
        "to_account": "0011def",
        "amount": "15000.00",
        "payment_format": "ACH",
        "event_time": "2025-09-12T09:00:00Z",
    }
    body = {
        "transactions": [
            {**base, "transaction_id": 42, "is_laundering": False},
            {**base, "transaction_id": 7, "is_laundering": True},
            {**base, "transaction_id": 555, "is_laundering": True},
        ]
    }
    r = precomputed_client.post("/v1/score", json=body, headers=auth)
    assert r.status_code == 200
    assert r.json()["results"] == [
        {"transaction_id": 42, "fraud_score": 0.8512, "typology": GNN, "status": "blocked"},
        {"transaction_id": 7, "fraud_score": 0.0123, "typology": None, "status": "approved"},
        {"transaction_id": 555, "fraud_score": 0.0, "typology": None, "status": "approved"},
    ]
    assert precomputed_client.post("/v1/score", json=body).status_code == 401
