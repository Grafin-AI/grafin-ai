from typing import NamedTuple

import asyncpg


class ValidationReport(NamedTuple):
    banks: int
    entities: int
    accounts: int
    entities_without_province: int
    orphan_account_refs: int
    ok: bool

    def as_dict(self) -> dict[str, int | bool]:
        return self._asdict()


async def validate(conn: asyncpg.Connection) -> ValidationReport:
    """Reference-only post-load checks: row counts + referential-integrity spot checks."""
    banks = int(await conn.fetchval("SELECT count(*) FROM banks") or 0)
    entities = int(await conn.fetchval("SELECT count(*) FROM entities") or 0)
    accounts = int(await conn.fetchval("SELECT count(*) FROM accounts") or 0)
    null_provinces = int(
        await conn.fetchval("SELECT count(*) FROM entities WHERE province IS NULL") or 0
    )
    orphan_accounts = int(
        await conn.fetchval(
            "SELECT count(*) FROM accounts a "
            "LEFT JOIN banks b ON b.id = a.bank_id "
            "LEFT JOIN entities e ON e.id = a.entity_id "
            "WHERE b.id IS NULL OR e.id IS NULL"
        )
        or 0
    )
    return ValidationReport(
        banks=banks,
        entities=entities,
        accounts=accounts,
        entities_without_province=null_provinces,
        orphan_account_refs=orphan_accounts,
        ok=(
            banks > 0
            and entities > 0
            and accounts > 0
            and null_provinces == 0
            and orphan_accounts == 0
        ),
    )
