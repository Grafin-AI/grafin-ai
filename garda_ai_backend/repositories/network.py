"""Two-hop transaction neighbourhood of a transaction's parties, for the network graph.

Point-in-time like the explanation evidence: only edges with event_time in
[t - 24h, t]. Each hop query hits the (from_account, event_time) /
(to_account, event_time) composite indexes and is bounded by FETCH_LIMIT so a hub
account cannot blow up the request; the response is then capped to NODE_CAP nodes and
EDGE_CAP edges, keeping the focal edge and edges touching the focal accounts first.
"""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.schema import Account, Bank, Transaction, TransactionEvent

WINDOW = timedelta(hours=24)
NODE_CAP = 60
EDGE_CAP = 150
FETCH_LIMIT = 2000
FLAGGED_STATUSES = ("flagged", "blocked")


def _edge(r: Any, focal_id: int) -> dict[str, Any]:
    return {
        "id": r.id, "source": r.from_account, "target": r.to_account,
        "amount": float(r.amount_paid), "currency": r.payment_currency,
        "event_time": r.event_time.isoformat(), "status": r.status,
        "fraud_score": float(r.fraud_score), "focal": r.id == focal_id,
    }


class NetworkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _edges_stmt() -> Select:
        return (
            select(
                Transaction.id, Transaction.from_account, Transaction.to_account,
                Transaction.amount_paid, Transaction.payment_currency, Transaction.event_time,
                TransactionEvent.status, TransactionEvent.fraud_score,
            )
            .select_from(Transaction)
            .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
        )

    async def _touching(
        self, accounts: Iterable[str], start: Any, end: Any
    ) -> list[Any]:
        accts = list(set(accounts))
        if not accts:
            return []
        stmt = (
            self._edges_stmt()
            .where(Transaction.event_time.between(start, end))
            .where(or_(Transaction.from_account.in_(accts), Transaction.to_account.in_(accts)))
            .order_by(TransactionEvent.fraud_score.desc(), Transaction.id)
            .limit(FETCH_LIMIT)
        )
        return list((await self._session.execute(stmt)).all())

    async def neighbourhood(self, transaction_id: int) -> dict[str, Any] | None:
        focal = (
            await self._session.execute(
                self._edges_stmt().where(Transaction.id == transaction_id)
            )
        ).first()
        if focal is None:
            return None
        end = focal.event_time
        start = end - WINDOW
        focal_accts = {focal.from_account, focal.to_account}

        hop1 = await self._touching(focal_accts, start, end)
        hop1_accts = {a for r in hop1 for a in (r.from_account, r.to_account)} - focal_accts
        hop2 = await self._touching(hop1_accts, start, end)

        by_id: dict[int, Any] = {focal.id: focal}
        for r in (*hop1, *hop2):
            by_id.setdefault(r.id, r)

        def priority(r: Any) -> tuple[int, float, int]:
            if r.id == focal.id:
                rank = 0
            elif r.from_account in focal_accts or r.to_account in focal_accts:
                rank = 1
            else:
                rank = 2
            return (rank, -float(r.fraud_score), r.id)

        nodes: list[str] = list(dict.fromkeys([focal.from_account, focal.to_account]))
        node_set = set(nodes)
        edges: list[Any] = []
        truncated = False
        for r in sorted(by_id.values(), key=priority):
            if len(edges) >= EDGE_CAP:
                truncated = True
                break
            new = [a for a in dict.fromkeys((r.from_account, r.to_account)) if a not in node_set]
            if len(node_set) + len(new) > NODE_CAP:
                truncated = True
                continue
            nodes.extend(new)
            node_set.update(new)
            edges.append(r)
        if len(hop1) >= FETCH_LIMIT or len(hop2) >= FETCH_LIMIT:
            truncated = True

        info = await self._node_info(nodes, start, end)
        roles = {focal.to_account: "receiver", focal.from_account: "sender"}
        return {
            "transaction_id": focal.id,
            "nodes": [
                {
                    "id": a, "bank": info.get(a, {}).get("bank") or "",
                    "role": roles.get(a, "other"),
                    "flagged_count": info.get(a, {}).get("flagged", 0),
                }
                for a in nodes
            ],
            "edges": [_edge(r, focal.id) for r in edges],
            "truncated": truncated,
        }

    async def _node_info(
        self, accounts: list[str], start: Any, end: Any
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {a: {"bank": None, "flagged": 0} for a in accounts}
        banks = await self._session.execute(
            select(Account.id, Account.bank_id, Bank.name)
            .outerjoin(Bank, Bank.id == Account.bank_id)
            .where(Account.id.in_(accounts))
        )
        for acc_id, bank_id, bank_name in banks.all():
            out[acc_id]["bank"] = bank_name or bank_id
        flagged = (
            select(Transaction.id, Transaction.from_account, Transaction.to_account)
            .join(TransactionEvent, TransactionEvent.transaction_id == Transaction.id)
            .where(
                Transaction.event_time.between(start, end),
                TransactionEvent.status.in_(FLAGGED_STATUSES),
                or_(Transaction.from_account.in_(accounts), Transaction.to_account.in_(accounts)),
            )
            .subquery()
        )
        parties = union_all(
            select(flagged.c.id, flagged.c.from_account.label("acc")),
            select(flagged.c.id, flagged.c.to_account.label("acc")),
        ).subquery()
        counts = await self._session.execute(
            select(parties.c.acc, func.count(func.distinct(parties.c.id)))
            .where(parties.c.acc.in_(accounts))
            .group_by(parties.c.acc)
        )
        for acc, n in counts.all():
            out[acc]["flagged"] = int(n)
        return out
