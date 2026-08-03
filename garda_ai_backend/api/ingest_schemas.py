from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

RiskStatus = Literal["approved", "flagged", "blocked"]


class IngestTxn(BaseModel):
    transaction_id: int
    from_bank_id: str
    from_account: str
    to_bank_id: str
    to_account: str
    amount_paid: Decimal
    payment_currency: str
    amount_received: Decimal
    receiving_currency: str
    payment_format: str
    is_laundering: bool
    event_time: datetime


class IngestRequest(BaseModel):
    transactions: Annotated[list[IngestTxn], Field(max_length=1000)]


class IngestResultItem(BaseModel):
    transaction_id: int
    seq: int | None
    status: RiskStatus | None
    ingested: bool


class IngestResponse(BaseModel):
    results: list[IngestResultItem]
