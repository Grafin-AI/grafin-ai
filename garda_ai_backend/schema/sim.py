from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, false, text
from sqlalchemy.orm import Mapped, mapped_column

from garda_ai_backend.schema.base import Base


class SimState(Base):
    __tablename__ = "sim_state"
    __table_args__ = (CheckConstraint("id = 1", name="sim_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sim_now: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    speed: Mapped[Decimal] = mapped_column(Numeric, default=1.0, server_default=text("1.0"))
    running: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
