import csv
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple


class SimTxn(NamedTuple):
    ordinal: int                    # 1-based, continuous across parts -> the transaction_id
    csv_ts: datetime                # original CSV timestamp; paces sending AND is sent as event_time
    fields: dict[str, object]       # ingest fields minus event_time (producer stamps that)


def _row_fields(r: dict[str, str]) -> dict[str, object]:
    return {
        "from_bank_id": r["From Bank"],
        "from_account": r["Account"],
        "to_bank_id": r["To Bank"],
        "to_account": r["To Account"],
        "amount_paid": str(Decimal(r["Amount Paid"])),        # string -> exact Decimal on the backend
        "payment_currency": r["Payment Currency"],
        "amount_received": str(Decimal(r["Amount Received"])),
        "receiving_currency": r["Receiving Currency"],
        "payment_format": r["Payment Format"],
        "is_laundering": r["Is Laundering"] == "1",
    }


def stream_transactions(
    paths: list[str], *, limit: int | None = None, skip: int = 0
) -> Iterator[SimTxn]:
    """Stream transactions from the Trans CSV parts, assigning a stable 1-based ordinal id
    continuous across parts. Streamed (never materialized) so the multi-million-row parts
    cost negligible memory.

    ``skip`` advances past the first N rows without sending them; ordinals keep counting
    from 1 regardless, so ``transaction_id`` stays the row's true CSV position. That is what
    lets a run resume mid-dataset (the backend dedups by transaction_id) and what makes a
    pre-populated history and a later live run line up instead of overlapping.

    ``limit`` caps the number of rows YIELDED (not the ordinal reached), so it means the same
    thing with or without ``skip``.
    """
    ordinal = 0
    yielded = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ordinal += 1
                if ordinal <= skip:
                    continue  # advance the ordinal, but do no parsing work
                if limit is not None and yielded >= limit:
                    return
                yielded += 1
                ts = datetime.strptime(r["Timestamp"], "%Y/%m/%d %H:%M").replace(tzinfo=UTC)
                yield SimTxn(ordinal=ordinal, csv_ts=ts, fields=_row_fields(r))
