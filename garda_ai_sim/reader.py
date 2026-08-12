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


def stream_transactions(paths: list[str], *, limit: int | None = None) -> Iterator[SimTxn]:
    """Stream transactions from the Trans CSV parts, assigning a stable 1-based ordinal id
    continuous across parts. Streamed (never materialized) so the multi-million-row parts
    cost negligible memory."""
    ordinal = 0
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if limit is not None and ordinal >= limit:
                    return
                ordinal += 1
                ts = datetime.strptime(r["Timestamp"], "%Y/%m/%d %H:%M").replace(tzinfo=UTC)
                yield SimTxn(ordinal=ordinal, csv_ts=ts, fields=_row_fields(r))
