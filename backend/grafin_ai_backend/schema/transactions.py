from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from grafin_ai_backend.schema.base import Base


class Transaction(Base):
    __tablename__ = "transactions"
    # Per-account 24h windows (transaction explanations): equality on the account,
    # range on event_time.
    __table_args__ = (
        Index("ix_transactions_from_account_event_time", "from_account", "event_time"),
        Index("ix_transactions_to_account_event_time", "to_account", "event_time"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    from_bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"))
    from_account: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    to_bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"))
    to_account: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric)
    payment_currency: Mapped[str] = mapped_column(String)
    amount_received: Mapped[Decimal] = mapped_column(Numeric)
    receiving_currency: Mapped[str] = mapped_column(String)
    payment_format: Mapped[str] = mapped_column(String)
    is_laundering: Mapped[bool] = mapped_column(Boolean, index=True)


class TransactionEvent(Base):
    __tablename__ = "transaction_events"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    surfaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Business time of the transaction (denormalized from transactions.event_time so the
    # read views stay single-table). surfaced_at stays = ingestion time, so
    # (surfaced_at - event_time) remains a usable detection-lag signal.
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fraud_score: Mapped[Decimal] = mapped_column(Numeric)
    typology: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)  # approved | flagged | blocked
