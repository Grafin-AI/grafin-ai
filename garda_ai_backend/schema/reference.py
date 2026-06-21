from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from garda_ai_backend.schema.base import Base


class Bank(Base):
    __tablename__ = "banks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    province: Mapped[str | None] = mapped_column(String, index=True)  # seeded enrichment


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    bank_id: Mapped[str] = mapped_column(ForeignKey("banks.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    risk_score: Mapped[Decimal | None] = mapped_column(Numeric)
    risk_category: Mapped[str | None] = mapped_column(String, index=True)

    bank: Mapped["Bank"] = relationship()
    entity: Mapped["Entity"] = relationship()
