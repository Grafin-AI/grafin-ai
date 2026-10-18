from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from grafin_ai_backend.schema.base import Base


class StoredExplanation(Base):
    """A persisted LLM explanation (rules fallbacks are never stored, so a retry stays
    possible). One row per transaction; inserted ON CONFLICT DO NOTHING so concurrent
    'generate' clicks converge on the first row."""

    __tablename__ = "transaction_explanations"
    transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transactions.id"), primary_key=True, autoincrement=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String)
    pattern_matching: Mapped[str] = mapped_column(Text, nullable=False)
    behavior_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    network_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[str] = mapped_column(String, nullable=False)
    references: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    risk_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    str_draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    generated_by: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    str_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
