from datetime import datetime

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from garda_ai_backend.schema import Bank, Transaction, TransactionEvent

TOP_BANKS = 12
OTHERS = "Lainnya"


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def typology_distribution(self, now: datetime) -> list[dict]:
        stmt = (
            select(
                TransactionEvent.typology.label("typology"),
                func.count().label("count"),
                func.coalesce(func.sum(Transaction.amount_paid), 0).label("amount"),
            )
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.event_time <= now)
            .where(TransactionEvent.typology.is_not(None))
            .group_by(TransactionEvent.typology)
            .order_by(func.count().desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            {"typology": r.typology, "count": int(r.count), "total_amount": float(r.amount)}
            for r in rows
        ]

    async def confusion_counts(self, now: datetime) -> dict:
        # "blocked" = the F1-optimal threshold, the same definition as the model's reported F1;
        # "flagged" is a high-recall review queue and would understate precision.
        predicted = TransactionEvent.status == "blocked"
        actual = Transaction.is_laundering.is_(True)
        tp = func.sum(case((predicted & actual, 1), else_=0))
        fp = func.sum(case((predicted & ~actual, 1), else_=0))
        fn = func.sum(case((~predicted & actual, 1), else_=0))
        stmt = (
            select(func.coalesce(tp, 0), func.coalesce(fp, 0), func.coalesce(fn, 0))
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .where(TransactionEvent.event_time <= now)
        )
        tp_v, fp_v, fn_v = (await self._session.execute(stmt)).one()
        return {"tp": int(tp_v), "fp": int(fp_v), "fn": int(fn_v)}

    async def institutions(self, now: datetime) -> dict:
        """Per sending institution (grouped by bank NAME: the localized data maps many source
        bank codes to one Indonesian bank): volume, flagged, blocked for the top TOP_BANKS by
        volume (the rest folded into "Lainnya"), plus flagged/blocked flows between groups."""
        src_bank, dst_bank = aliased(Bank), aliased(Bank)
        src_name = func.coalesce(src_bank.name, Transaction.from_bank_id)
        dst_name = func.coalesce(dst_bank.name, Transaction.to_bank_id)
        flagged = func.sum(case((TransactionEvent.status == "flagged", 1), else_=0))
        blocked = func.sum(case((TransactionEvent.status == "blocked", 1), else_=0))
        base = (
            select()
            .select_from(TransactionEvent)
            .join(Transaction, Transaction.id == TransactionEvent.transaction_id)
            .outerjoin(src_bank, src_bank.id == Transaction.from_bank_id)
            .outerjoin(dst_bank, dst_bank.id == Transaction.to_bank_id)
            .where(TransactionEvent.event_time <= now)
        )
        top_rows = (
            await self._session.execute(
                base.add_columns(
                    src_name.label("bank"),
                    func.count().label("n"),
                    func.coalesce(flagged, 0).label("flagged"),
                    func.coalesce(blocked, 0).label("blocked"),
                )
                .group_by(src_name)
                .order_by(func.count().desc(), src_name)
                .limit(TOP_BANKS)
            )
        ).all()
        total = (
            await self._session.execute(
                base.add_columns(
                    func.count(), func.coalesce(flagged, 0), func.coalesce(blocked, 0)
                )
            )
        ).one()
        top_names = [r.bank for r in top_rows]

        def _inst(bank: str, n: int, f: int, b: int) -> dict:
            return {
                "bank": bank, "transactions": n, "flagged": f, "blocked": b,
                "flagged_rate": ((f + b) / n) if n else 0.0,
            }

        institutions = [
            _inst(r.bank, int(r.n), int(r.flagged), int(r.blocked)) for r in top_rows
        ]
        rest = [int(total[0]), int(total[1]), int(total[2])]
        for r in top_rows:
            rest = [rest[0] - int(r.n), rest[1] - int(r.flagged), rest[2] - int(r.blocked)]
        if rest[0] > 0:
            institutions.append(_inst(OTHERS, *rest))

        # Names first (inner subquery), then fold non-top names into "Lainnya" (outer
        # subquery), then group on the outer columns: grouping by the CASE expression itself
        # would bind the IN-list twice and Postgres would not see the two as identical.
        raw = (
            base.add_columns(
                src_name.label("src"), dst_name.label("dst"),
                Transaction.amount_paid.label("amount"),
            )
            .where(TransactionEvent.status.in_(("flagged", "blocked")))
            .subquery()
        )

        def _group(col):  # type: ignore[no-untyped-def]
            return case((col.in_(top_names), col), else_=literal(OTHERS)) if top_names else (
                literal(OTHERS)
            )

        grouped = select(
            _group(raw.c.src).label("src"), _group(raw.c.dst).label("dst"), raw.c.amount
        ).subquery()
        flow_rows = (
            await self._session.execute(
                select(
                    grouped.c.src, grouped.c.dst, func.count().label("n"),
                    func.coalesce(func.sum(grouped.c.amount), 0).label("amount"),
                )
                .group_by(grouped.c.src, grouped.c.dst)
                .order_by(func.count().desc(), grouped.c.src, grouped.c.dst)
            )
        ).all()
        flows = [
            {
                "from_bank": r.src, "to_bank": r.dst,
                "flagged_count": int(r.n), "amount": float(r.amount),
            }
            for r in flow_rows
        ]
        return {"institutions": institutions, "flows": flows}
