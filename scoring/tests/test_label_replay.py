from datetime import UTC, datetime
from decimal import Decimal

import pytest

from garda_ai_scoring.scoring.label_replay import LabelReplayScorer
from garda_ai_scoring.scoring.types import ScoringContext, TxnInput


def _txn(tid: int, laundering: bool) -> TxnInput:
    return TxnInput(
        transaction_id=tid, from_account=f"A{tid}", to_account=f"B{tid}",
        amount=Decimal(1000000), payment_format="ACH", is_laundering=laundering,
        event_time=datetime(2025, 9, 1, tzinfo=UTC),
    )


@pytest.fixture
def scorer():
    return LabelReplayScorer(seed="test")


async def test_deterministic(scorer):
    a = await scorer.score(_txn(1, True), ScoringContext())
    b = await scorer.score(_txn(1, True), ScoringContext())
    assert a == b


async def test_score_in_unit_range(scorer):
    r = await scorer.score(_txn(7, True), ScoringContext())
    assert 0.0 <= r.fraud_score <= 1.0


async def test_laundering_mostly_high_and_typed(scorer):
    results = [await scorer.score(_txn(i, True), ScoringContext()) for i in range(200)]
    risky = [r for r in results if r.status in ("flagged", "blocked")]
    assert len(risky) >= 180
    assert all(r.typology is not None for r in risky)


async def test_legit_mostly_low_and_untyped(scorer):
    results = [await scorer.score(_txn(i, False), ScoringContext()) for i in range(200)]
    approved = [r for r in results if r.status == "approved"]
    assert len(approved) >= 180
    assert all(r.typology is None for r in approved)


async def test_has_some_false_positives_and_negatives(scorer):
    laundering = [await scorer.score(_txn(i, True), ScoringContext()) for i in range(500)]
    legit = [await scorer.score(_txn(i, False), ScoringContext()) for i in range(500)]
    false_negatives = [r for r in laundering if r.status == "approved"]
    false_positives = [r for r in legit if r.status in ("flagged", "blocked")]
    assert 1 <= len(false_negatives) <= 80
    assert 1 <= len(false_positives) <= 80


async def test_high_risk_category_nudges_up(scorer):
    base = await scorer.score(_txn(3, False), ScoringContext())
    high = await scorer.score(_txn(3, False), ScoringContext(from_risk_category="High"))
    assert high.fraud_score >= base.fraud_score
