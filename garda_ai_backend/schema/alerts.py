from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_seq: Mapped[int] = mapped_column(ForeignKey("transaction_events.seq"), index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    typology: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_by: Mapped[int | None] = mapped_column(BigInteger)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
