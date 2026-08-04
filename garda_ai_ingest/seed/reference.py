import csv
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

import asyncpg

from garda_ai_ingest.geo import province_for_entity


class LoadCounts(NamedTuple):
    banks: int
    entities: int
    accounts: int


def _num(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


async def load_reference(
    conn: asyncpg.Connection, accounts_csv: str, *, batch_size: int = 5000
) -> LoadCounts:
    """Load banks, entities (+ seeded province), and accounts from accounts.csv. Idempotent."""
    banks: dict[str, str] = {}
    entities: dict[str, str] = {}
    accounts: list[tuple[str, str, str, Decimal | None, str | None]] = []

    with open(accounts_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bank_id, entity_id, acct = r["Bank ID"], r["Entity ID"], r["Account Number"]
            banks.setdefault(bank_id, r["Bank Name"])
            entities.setdefault(entity_id, r["Entity Name"])
            accounts.append(
                (acct, bank_id, entity_id, _num(r["risk_score"]), r["risk_category"] or None)
            )

    await conn.executemany(
        "INSERT INTO banks (id, name) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        list(banks.items()),
    )
    await conn.executemany(
        "INSERT INTO entities (id, name, province) VALUES ($1, $2, $3) "
        "ON CONFLICT (id) DO NOTHING",
        [(eid, name, province_for_entity(eid)) for eid, name in entities.items()],
    )
    for i in range(0, len(accounts), batch_size):
        await conn.executemany(
            "INSERT INTO accounts (id, bank_id, entity_id, risk_score, risk_category) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
            accounts[i : i + batch_size],
        )

    return LoadCounts(banks=len(banks), entities=len(entities), accounts=len(accounts))
