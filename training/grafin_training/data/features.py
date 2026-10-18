"""Paper edge features, categorical codebooks and train-only normalisation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BASE_FEATURES = ("Timestamp", "Amount Received", "Received Currency", "Payment Format")


@dataclass(frozen=True)
class Codebooks:
    currency: dict[str, int]
    payment_format: dict[str, int]

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"currency": self.currency, "payment_format": self.payment_format}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Codebooks:
        return cls(dict(raw["currency"]), dict(raw["payment_format"]))


def build_codebooks(frame: pl.DataFrame) -> Codebooks:
    """Codes in first-appearance order over input rows, as upstream assigns them
    (per row: receiving currency, then payment currency; payment format)."""
    by_row = frame.sort("row")
    cur = pl.concat(
        [
            by_row.select("row", pl.lit(0).alias("side"), pl.col("receiving_currency").alias("v")),
            by_row.select("row", pl.lit(1).alias("side"), pl.col("payment_currency").alias("v")),
        ]
    ).sort(["row", "side"])
    currencies = cur.get_column("v").unique(maintain_order=True).to_list()
    formats = by_row.get_column("payment_format").unique(maintain_order=True).to_list()
    return Codebooks(
        {c: i for i, c in enumerate(currencies)}, {f: i for i, f in enumerate(formats)}
    )


def paper_base_features(frame: pl.DataFrame, codebooks: Codebooks) -> FloatArray:
    """[E, 4] in frame order: seconds since the first transaction, amount received,
    receiving-currency code, payment-format code (upstream edge_features)."""
    ts = frame.get_column("ts").to_numpy().astype(np.float64)
    amount = frame.get_column("amount_received").to_numpy().astype(np.float64)
    cur = frame.get_column("receiving_currency").replace_strict(
        codebooks.currency, return_dtype=pl.Int64
    )
    fmt = frame.get_column("payment_format").replace_strict(
        codebooks.payment_format, return_dtype=pl.Int64
    )
    return np.column_stack(
        [
            ts - ts.min(),
            amount,
            cur.to_numpy().astype(np.float64),
            fmt.to_numpy().astype(np.float64),
        ]
    )


@dataclass(frozen=True)
class NormStats:
    mean: FloatArray
    std: FloatArray

    def to_dict(self) -> dict[str, list[float]]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}


def fit_norm(x: FloatArray, rows: IntArray) -> NormStats:
    """Column mean / unbiased std over `rows` only (upstream z_norm; zero std → 1).
    Fix vs upstream: fitted on training rows and applied to every split."""
    sub = x[rows]
    mean = sub.mean(axis=0)
    std = sub.std(axis=0, ddof=1)
    return NormStats(mean, np.where(std == 0, 1.0, std))


def apply_norm(x: FloatArray, stats: NormStats) -> npt.NDArray[np.float32]:
    return ((x - stats.mean) / stats.std).astype(np.float32)
