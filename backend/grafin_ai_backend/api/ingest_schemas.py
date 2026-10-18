from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

RiskStatus = Literal["approved", "flagged", "blocked"]

Amount = Annotated[Decimal, Field(max_digits=20, decimal_places=4, ge=0)]


class IngestTxn(BaseModel):
    transaction_id: int
    from_bank_id: Annotated[str, Field(max_length=64)]
    from_account: Annotated[str, Field(max_length=64)]
    to_bank_id: Annotated[str, Field(max_length=64)]
    to_account: Annotated[str, Field(max_length=64)]
    amount_paid: Amount
    payment_currency: Annotated[str, Field(max_length=8)]
    amount_received: Amount
    receiving_currency: Annotated[str, Field(max_length=8)]
    payment_format: Annotated[str, Field(max_length=32)]
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
