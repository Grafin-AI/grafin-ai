"""Evidence for a transaction explanation, computed from the DB.

Point-in-time correct: every aggregate only sees rows with event_time in
[t.event_time - 24h, t.event_time], so nothing that happened after the transaction
can leak into its explanation. Never reads ``transactions.is_laundering`` (the
ground-truth label): explanations must be derivable from what the system knew.

Index use: the per-account windows hit (from_account, event_time) and
(to_account, event_time) composite indexes; the flagged counts join
transaction_events on its transaction_id index.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from grafin_ai_backend.schema import Account, Entity, Transaction, TransactionEvent

WINDOW = timedelta(hours=24)
FLAGGED_STATUSES = ("flagged", "blocked")
MIN_TX_FOR_MEDIAN = 3

Evidence = dict[str, Any]


def _round(value: Any, ndigits: int = 2) -> float:
    return round(float(value), ndigits)


async def _base_row(session: AsyncSession, transaction_id: int) -> Any:
    from_acc, to_acc = aliased(Account), aliased(Account)
    from_ent, to_ent = aliased(Entity), aliased(Entity)
    stmt = (
        select(
            Transaction.id, Transaction.event_time, Transaction.amount_paid,
            Transaction.payment_currency, Transaction.payment_format,
            Transaction.from_bank_id, Transaction.to_bank_id,
            Transaction.from_account, Transaction.to_account,
            TransactionEvent.fraud_score, TransactionEvent.status, TransactionEvent.typology,
            from_acc.risk_category.label("sender_risk_category"),
            to_acc.risk_category.label("receiver_risk_category"),
            from_acc.entity_id.label("sender_entity_id"),
            to_acc.entity_id.label("receiver_entity_id"),
            from_ent.province.label("sender_province"),
            to_ent.province.label("receiver_province"),
        )
        .select_from(Transaction)
        .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
        .outerjoin(from_acc, from_acc.id == Transaction.from_account)
        .outerjoin(to_acc, to_acc.id == Transaction.to_account)
        .outerjoin(from_ent, from_ent.id == from_acc.entity_id)
        .outerjoin(to_ent, to_ent.id == to_acc.entity_id)
        .where(Transaction.id == transaction_id)
    )
    return (await session.execute(stmt)).first()


def _flagged_count(account: str, start: Any, end: Any, exclude_id: int) -> Select:
    """Other flagged/blocked events in the window where ``account`` is either party.

    The transaction being explained is excluded so its own status does not count as
    'prior flagged activity' of its parties.
    """
    return (
        select(func.count())
        .select_from(Transaction)
        .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
        .where(
            or_(Transaction.from_account == account, Transaction.to_account == account),
            Transaction.event_time.between(start, end),
            TransactionEvent.status.in_(FLAGGED_STATUSES),
            Transaction.id != exclude_id,
        )
    )


async def compute_evidence(session: AsyncSession, transaction_id: int) -> Evidence | None:
    """Return the evidence dict, or None if the transaction (or its event) is unknown."""
    r = await _base_row(session, transaction_id)
    if r is None:
        return None
    end = r.event_time
    start = end - WINDOW
    in_window = Transaction.event_time.between(start, end)

    out = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Transaction.amount_paid), 0),
                func.count(func.distinct(Transaction.to_account)),
                func.percentile_cont(0.5).within_group(Transaction.amount_paid),
            ).where(Transaction.from_account == r.from_account, in_window)
        )
    ).one()
    inc = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(Transaction.amount_paid), 0),
                func.count(func.distinct(Transaction.from_account)),
            ).where(Transaction.to_account == r.to_account, in_window)
        )
    ).one()
    sender_flagged = await session.scalar(
        _flagged_count(r.from_account, start, end, r.id)
    )
    receiver_flagged = await session.scalar(
        _flagged_count(r.to_account, start, end, r.id)
    )

    out_count, out_amount, out_distinct, out_median = out
    amount = float(r.amount_paid)
    ratio = (
        _round(amount / float(out_median))
        if out_count >= MIN_TX_FOR_MEDIAN and out_median and float(out_median) > 0
        else None
    )
    hour = r.event_time.hour  # dataset timestamps are stored as UTC wall-clock
    same_entity = (
        r.sender_entity_id is not None and r.sender_entity_id == r.receiver_entity_id
    )
    return {
        "fraud_score": _round(r.fraud_score, 4),
        "status": r.status,
        "typology": r.typology,
        "amount": _round(amount),
        "currency": r.payment_currency,
        "channel": r.payment_format,
        "hour_of_day": hour,
        "is_night": 0 <= hour <= 5,
        "cross_bank": r.from_bank_id != r.to_bank_id,
        "self_transfer": r.from_account == r.to_account or same_entity,
        "sender_out_count_24h": int(out_count),
        "sender_out_amount_24h": _round(out_amount),
        "sender_distinct_receivers_24h": int(out_distinct),
        "receiver_in_count_24h": int(inc[0]),
        "receiver_in_amount_24h": _round(inc[1]),
        "receiver_distinct_senders_24h": int(inc[2]),
        "sender_flagged_24h": int(sender_flagged or 0),
        "receiver_flagged_24h": int(receiver_flagged or 0),
        "amount_vs_sender_median": ratio,
        "sender_risk_category": r.sender_risk_category,
        "receiver_risk_category": r.receiver_risk_category,
        "sender_province": r.sender_province,
        "receiver_province": r.receiver_province,
    }
