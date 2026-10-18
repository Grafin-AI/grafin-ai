from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TxnInput:
    transaction_id: int
    from_account: str
    to_account: str
    amount: Decimal
    payment_format: str
    is_laundering: bool
    event_time: datetime


@dataclass(frozen=True)
class ScoringContext:
    """Cheap, precomputable signals available at scoring time (extensible)."""
    from_risk_category: str | None = None  # Low | Medium | High


@dataclass(frozen=True)
class ScoringResult:
    fraud_score: float          # 0..1
    typology: str | None        # e.g. Fan-Out | Smurfing | ... ; None when not suspicious
    status: str                 # approved | flagged | blocked


@runtime_checkable
class ScoringProvider(Protocol):
    async def score(self, txn: TxnInput, ctx: ScoringContext) -> ScoringResult: ...
