"""Readers for IBM-format files. Everything is read as text, and Trans columns by position."""

from pathlib import Path

import polars as pl

from grafin_ai_dataset.errors import RawInputError

TRANS_COLS = (
    "timestamp",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "receiving_currency",
    "amount_paid",
    "payment_currency",
    "payment_format",
    "is_laundering",
)
# IBM's header names BOTH account columns "Account". We read by position and write
# "To Account" for the second, which is what grafin-ai-sim reads.
OUT_HEADER = (
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "To Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
)
ACCOUNT_COLS = ("Bank Name", "Bank ID", "Account Number", "Entity ID", "Entity Name")


def _require(path: Path) -> None:
    if not path.exists():
        raise RawInputError(f"input missing: {path} (run `grafin-dataset fetch` first)")


def scan_trans_csv(path: Path) -> pl.LazyFrame:
    """Any IBM-layout Trans CSV (raw or localized) as 11 text columns named TRANS_COLS."""
    _require(path)
    schema = pl.Schema({c: pl.String for c in TRANS_COLS})
    return pl.scan_csv(path, has_header=False, skip_rows=1, schema=schema)


def scan_raw_trans(path: Path) -> pl.LazyFrame:
    """The raw Trans file plus ``raw_row``: the 0-based position in the original file."""
    return scan_trans_csv(path).with_row_index("raw_row")


def read_raw_accounts(path: Path) -> pl.DataFrame:
    _require(path)
    df = pl.read_csv(path, infer_schema=False)
    missing = [c for c in ACCOUNT_COLS if c not in df.columns]
    if missing:
        raise RawInputError(f"{path.name}: missing columns {missing}")
    return df.select(ACCOUNT_COLS)
