from datetime import UTC, datetime
from decimal import Decimal

from garda_ai_scoring.scoring.types import (
    ScoringContext,
    ScoringProvider,
    ScoringResult,
    TxnInput,
)


def test_txn_input_fields():
    t = TxnInput(
        transaction_id=1, from_account="A1", to_account="A2", amount=Decimal(100),
        payment_format="ACH", is_laundering=True, event_time=datetime(2025, 9, 1, tzinfo=UTC),
    )
    assert t.transaction_id == 1
    assert t.is_laundering is True


def test_result_and_context():
    r = ScoringResult(fraud_score=0.9, typology="Fan-Out", status="blocked")
    assert r.status == "blocked"
    assert ScoringContext().from_risk_category is None


def test_provider_is_structural_protocol():
    class Fake:
        async def score(self, txn, ctx):
            return ScoringResult(fraud_score=0.0, typology=None, status="approved")

    provider: ScoringProvider = Fake()
    assert provider is not None
