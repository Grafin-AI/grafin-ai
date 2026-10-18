"""Row-level transforms: time shift, bank ids, FX to IDR, channel names (spec 6.2)."""

import polars as pl

from grafin_ai_dataset.errors import MappingError
from grafin_ai_dataset.mappings import Mappings
from grafin_ai_dataset.raw import OUT_HEADER

OFFSET_DAYS = 1099  # 157 whole weeks: 2022-09-01 (Thu) -> 2025-09-04 (Thu)
TS_FORMAT = "%Y/%m/%d %H:%M"


def parse_ts(column: str, *, strict: bool = True) -> pl.Expr:
    return pl.col(column).str.to_datetime(TS_FORMAT, strict=strict)


def to_idr(amount_column: str, currency_column: str, fx: dict[str, float]) -> pl.Expr:
    """Amount times the fixed rate of its own currency, rounded to whole rupiah."""
    rate = pl.col(currency_column).replace_strict(fx, return_dtype=pl.Float64)
    return (pl.col(amount_column).cast(pl.Float64) * rate).round(0).cast(pl.Int64)


def localize_features(raw: pl.LazyFrame, maps: Mappings) -> pl.LazyFrame:
    """Raw text rows (WITHOUT the label) -> localized, typed rows keyed by raw_row."""
    if "is_laundering" in raw.collect_schema().names():
        raise ValueError("transforms must not receive the label column (spec 6.1)")
    return raw.select(
        "raw_row",
        (parse_ts("timestamp") + pl.duration(days=OFFSET_DAYS)).alias("ts"),
        pl.col("from_bank").cast(pl.Int64),
        "from_account",
        pl.col("to_bank").cast(pl.Int64),
        "to_account",
        to_idr("amount_received", "receiving_currency", maps.fx).alias("amount_received"),
        to_idr("amount_paid", "payment_currency", maps.fx).alias("amount_paid"),
        pl.col("payment_format").replace_strict(maps.channels, return_dtype=pl.String),
    )


def format_output(df: pl.DataFrame) -> pl.DataFrame:
    """Localized rows (with is_laundering) -> the 11 output columns, exactly as written."""
    out = df.select(
        pl.col("ts").dt.strftime(TS_FORMAT),
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_received",
        pl.lit("IDR").alias("receiving_currency"),
        "amount_paid",
        pl.lit("IDR").alias("payment_currency"),
        "payment_format",
        "is_laundering",
    )
    return out.rename(dict(zip(out.columns, OUT_HEADER, strict=True)))


def check_vocabulary(raw: pl.LazyFrame, maps: Mappings) -> None:
    """Fail early, naming every currency or payment format the mapping tables don't cover."""
    received, paid, formats = pl.collect_all(
        [
            raw.select(pl.col("receiving_currency").unique()),
            raw.select(pl.col("payment_currency").unique()),
            raw.select(pl.col("payment_format").unique()),
        ]
    )
    currencies = set(received.to_series().to_list()) | set(paid.to_series().to_list())
    missing_fx = sorted(str(c) for c in currencies if c not in maps.fx)
    missing_channels = sorted(
        str(f) for f in formats.to_series().to_list() if f not in maps.channels
    )
    if missing_fx or missing_channels:
        raise MappingError(
            "raw data has values missing from the mapping tables: "
            f"currencies {missing_fx} (add rows to mappings/fx_rates.csv), "
            f"payment formats {missing_channels} (add rows to mappings/channels.csv)"
        )
