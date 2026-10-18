from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
import pytest

from garda_training.data.load import read_transactions, verify_dataset
from garda_training.errors import DatasetError


def test_read_raw_and_id_give_the_same_transactions(fixture_paths: tuple[Path, Path]) -> None:
    raw, idp = (read_transactions(p) for p in fixture_paths)
    assert raw.height == idp.height == 229
    assert raw.get_column("ts").is_sorted() and idp.get_column("ts").is_sorted()
    assert raw.schema["from_bank"] == pl.Int64 and raw.get_column("from_bank").min() == 10
    cols = ["from_bank", "from_account", "to_bank", "to_account", "is_laundering"]
    assert raw.select(cols).equals(idp.select(cols))  # same order after sorting by time
    assert idp.get_column("receiving_currency").unique().to_list() == ["IDR"]
    assert int(raw.get_column("is_laundering").sum()) == 13


def test_verify_dataset(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    raw, idp = fixture_paths
    assert len(verify_dataset(raw, "raw")) == 64
    assert len(verify_dataset(idp, "id")) == 64
    tampered = tmp_path / "id"
    shutil.copytree(idp.parent, tampered)
    with (tampered / idp.name).open("a") as fh:
        fh.write("2025/09/09 23:59,10,X,10,Y,1,IDR,1,IDR,BI-FAST,0\n")
    with pytest.raises(DatasetError, match="does not match"):
        verify_dataset(tampered / idp.name, "id")
    (tampered / "MANIFEST.json").write_text(json.dumps({"outputs": {}}))
    with pytest.raises(DatasetError, match="no entry"):
        verify_dataset(tampered / idp.name, "id")
    with pytest.raises(DatasetError, match="not found"):
        verify_dataset(tmp_path / "missing.csv", "raw")
