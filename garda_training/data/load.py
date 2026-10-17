"""Read raw Kaggle or localized (HI-*-ID) transaction CSVs into one canonical Polars frame.

Both formats share 11 positional columns; only the header text and value vocabularies differ.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import polars as pl

from garda_training.errors import ConfigError, DatasetError

Source = Literal["raw", "id"]
SOURCES: tuple[Source, ...] = ("raw", "id")
POSITIONAL = (
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
TS_FORMAT = "%Y/%m/%d %H:%M"


def as_source(value: str) -> Source:
    if value == "raw":
        return "raw"
    if value == "id":
        return "id"
    raise ConfigError(f"--source must be one of {SOURCES}, got {value!r}")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def expected_sha256(path: Path, source: Source) -> str:
    """ID data: garda-ai-dataset MANIFEST.json "outputs". Raw data: SHA256SUMS from the fetch step."""
    if source == "id":
        manifest = path.parent / "MANIFEST.json"
        if not manifest.is_file():
            raise DatasetError(f"missing {manifest}")
        try:
            outputs = json.loads(manifest.read_text(encoding="utf-8"))["outputs"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise DatasetError(f"{manifest}: no readable 'outputs' section") from exc
        if path.name not in outputs:
            raise DatasetError(f"{manifest} has no entry for {path.name}")
        return str(outputs[path.name])
    sums = path.parent / "SHA256SUMS"
    if not sums.is_file():
        raise DatasetError(f"missing {sums}")
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == path.name:
            return parts[0]
    raise DatasetError(f"{sums} has no entry for {path.name}")


def verify_dataset(path: Path, source: Source) -> str:
    """Return the file's sha256 after checking it against the dataset's manifest."""
    if not path.is_file():
        raise DatasetError(f"dataset not found: {path}")
    expected = expected_sha256(path, source)
    actual = sha256_file(path)
    if actual != expected:
        raise DatasetError(f"{path.name}: sha256 {actual} does not match expected {expected}")
    return actual


def read_transactions(path: Path) -> pl.DataFrame:
    """Canonical frame sorted by (ts, row).

    Columns: row (input order, 0-based), ts (epoch seconds, naive UTC), from_bank/to_bank (Int64,
    zero padding removed), from_account/to_account, amount_received/amount_paid (Float64),
    receiving_currency/payment_currency/payment_format (String), is_laundering (Int8).
    """
    schema = {name: pl.String for name in POSITIONAL}
    try:
        frame = pl.read_csv(path, has_header=False, skip_rows=1, schema=schema)
        frame = (
            frame.with_row_index("row")
            .with_columns(
                pl.col("timestamp")
                .str.strptime(pl.Datetime("us"), TS_FORMAT)
                .dt.epoch("s")
                .alias("ts"),
                pl.col("from_bank").cast(pl.Int64),
                pl.col("to_bank").cast(pl.Int64),
                pl.col("amount_received").cast(pl.Float64),
                pl.col("amount_paid").cast(pl.Float64),
                pl.col("is_laundering").cast(pl.Int8),
            )
            .drop("timestamp")
        )
    except (pl.exceptions.PolarsError, OSError) as exc:
        raise DatasetError(f"cannot read {path}: {exc}") from exc
    if frame.height == 0:
        raise DatasetError(f"{path} has no transactions")
    return frame.sort(["ts", "row"])
