import datetime as dt
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import polars as pl
import pytest

from grafin_ai_dataset.errors import MappingError, RawInputError
from grafin_ai_dataset.mappings import Mappings
from grafin_ai_dataset.paths import DatasetPaths
from grafin_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from grafin_ai_dataset.transforms.transactions import (
    OFFSET_DAYS,
    check_vocabulary,
    format_output,
    localize_features,
)


def _idr(amount: str, rate: str) -> int:
    return int((Decimal(amount) * Decimal(rate)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def test_scan_reads_text_by_position(raw_paths: DatasetPaths) -> None:
    df = scan_raw_trans(raw_paths.raw_trans).collect()
    assert df.height == 12
    assert df.columns[0] == "raw_row"
    row = df.row(2, named=True)
    assert row["from_bank"] == "0010"  # kept verbatim as text
    assert row["to_account"] == "DUP"  # second "Account" column read by position


def test_localize_features(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans)
    out = localize_features(raw.drop("is_laundering"), maps).collect().sort("raw_row")
    r0 = out.row(0, named=True)
    assert r0["ts"] == dt.datetime(2025, 9, 5, 10, 0)
    assert (r0["from_bank"], r0["to_bank"]) == (10, 20)
    assert r0["amount_paid"] == _idr("100.00", "16445")
    assert out.row(1, named=True)["amount_paid"] == _idr("250.50", "19154.37")
    assert out.row(2, named=True)["from_bank"] == 10  # "0010" -> 10
    assert out.row(2, named=True)["amount_paid"] == _idr("1000.00", "110.87")
    assert out.row(3, named=True)["amount_paid"] == _idr("0.5", "1820849602")
    r5 = out.row(5, named=True)  # cross-currency: received USD, paid EUR
    assert r5["amount_received"] == _idr("75.00", "16445")
    assert r5["amount_paid"] == _idr("70.00", "19154.37")
    assert out["payment_format"].to_list() == [
        "BI-FAST", "RTGS", "SKNBI (Cek/BG)", "Aset Kripto", "Aset Kripto", "Kartu Kredit",
        "Setor/Tarik Tunai", "Setor/Tarik Tunai", "Pemindahbukuan", "BI-FAST", "BI-FAST",
        "Pemindahbukuan",
    ]


def test_localize_features_refuses_the_label(raw_paths: DatasetPaths, maps: Mappings) -> None:
    with pytest.raises(ValueError, match="label"):
        localize_features(scan_raw_trans(raw_paths.raw_trans), maps)


def test_offset_is_whole_weeks() -> None:
    start = dt.date(2022, 9, 1)
    shifted = start + dt.timedelta(days=OFFSET_DAYS)
    assert OFFSET_DAYS == 1099
    assert shifted == dt.date(2025, 9, 4)
    assert shifted.weekday() == start.weekday()


def test_format_output(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans)
    labels = raw.select("raw_row", pl.col("is_laundering").cast(pl.Int8))
    staged = (
        localize_features(raw.drop("is_laundering"), maps)
        .join(labels, on="raw_row")
        .collect()
        .sort("raw_row")
    )
    out = format_output(staged)
    assert tuple(out.columns) == OUT_HEADER
    amount = _idr("100.00", "16445")
    assert out.head(1).write_csv(include_header=False).strip() == (
        f"2025/09/05 10:00,10,A1,20,B1,{amount},IDR,{amount},IDR,BI-FAST,0"
    )


def test_check_vocabulary_ok(raw_paths: DatasetPaths, maps: Mappings) -> None:
    check_vocabulary(scan_raw_trans(raw_paths.raw_trans), maps)


def test_check_vocabulary_names_unknown_values(raw_paths: DatasetPaths, maps: Mappings) -> None:
    text = raw_paths.raw_trans.read_text().replace("Yen", "Doubloon").replace("Cheque", "Barter")
    raw_paths.raw_trans.write_text(text)
    with pytest.raises(MappingError, match="Doubloon") as exc:
        check_vocabulary(scan_raw_trans(raw_paths.raw_trans), maps)
    assert "Barter" in str(exc.value)


def test_missing_raw_file(tmp_path: Path) -> None:
    with pytest.raises(RawInputError):
        scan_raw_trans(tmp_path / "nope.csv")


def test_accounts_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "accounts.csv"
    path.write_text("Bank ID,Account Number\n1,A\n")
    with pytest.raises(RawInputError, match="Entity ID"):
        read_raw_accounts(path)
