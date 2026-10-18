from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

RiskCategory = Literal["Low", "Medium", "High"]
Status = Literal["approved", "flagged", "blocked"]


class ScoreRequestItem(BaseModel):
    transaction_id: int
    from_account: str
    to_account: str
    amount: Decimal
    payment_format: str
    is_laundering: bool
    event_time: datetime
    from_risk_category: RiskCategory | None = None


class ScoreRequest(BaseModel):
    transactions: Annotated[list[ScoreRequestItem], Field(max_length=1000)]


class ScoreResultItem(BaseModel):
    transaction_id: int
    fraud_score: float
    typology: str | None
    status: Status


class ScoreResponse(BaseModel):
    results: list[ScoreResultItem]
