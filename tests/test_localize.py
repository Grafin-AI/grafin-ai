from pathlib import Path

import polars as pl
import pytest

from garda_ai_dataset.errors import DiskSpaceError, RawInputError
from garda_ai_dataset.localize import localize_frames, run_localize
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths, dataset_paths
from garda_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from tests.fixture_data import EXPECTED_TID, LEGACY_ACCOUNTS, RAW_ROWS, write_raw

OUTPUTS = ("out_trans", "out_accounts", "out_entities", "out_patterns", "out_typologies")


def _run(paths: DatasetPaths, maps: Mappings, legacy: Path | None = None) -> dict[str, object]:
    return run_localize(paths, maps, legacy, min_free_bytes=0)


def test_outputs_and_manifest(raw_paths: DatasetPaths, maps: Mappings) -> None:
    manifest = _run(raw_paths, maps)
    for attr in OUTPUTS:
        assert getattr(raw_paths, attr).exists(), attr
    assert raw_paths.manifest.exists()
    assert not raw_paths.tmp_dir.exists()
    assert manifest["counts"] == {
        "transactions": 12, "laundering": 4, "accounts": 9, "entities": 7, "banks": 4,
        "days": 3, "first_day": "2025-09-04", "last_day": "2025-09-06",
    }
    assert manifest["typology"] == {
        "attempts": 2, "pattern_rows": 3, "matched_rows": 3, "unmatched_pattern_rows": 0,
        "laundering_coverage": 0.75,
    }
    assert manifest["risk_source"] == "none"


def test_trans_is_sorted_and_labels_follow_rows(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    out = pl.read_csv(raw_paths.out_trans, infer_schema=False)
    assert tuple(out.columns) == OUT_HEADER
    raw_by_tid = {tid: raw_row for raw_row, tid in EXPECTED_TID.items()}
    raw_labels = [row.rsplit(",", 1)[1] for row in RAW_ROWS]
    assert out["Is Laundering"].to_list() == [raw_labels[raw_by_tid[t]] for t in range(1, 13)]
    assert out["Timestamp"].to_list() == sorted(out["Timestamp"].to_list())
    assert out["Timestamp"][0] == "2025/09/04 00:20"
    assert out["Account"].to_list()[3:5] == ["B1", "A3"]  # 09:30 tie broken by raw_row
    assert set(out["Receiving Currency"].to_list()) == {"IDR"}


def test_typologies(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    assert pl.read_csv(raw_paths.out_typologies).rows() == [
        (2, 1, "FAN-OUT"), (3, 1, "FAN-OUT"), (9, 2, "CYCLE"), (11, None, "UNATTRIBUTED")
    ]


def test_patterns_reuse_trans_lines(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    trans_lines = raw_paths.out_trans.read_text().splitlines()[1:]
    pattern_rows = [line for line in raw_paths.out_patterns.read_text().splitlines()
                    if line.startswith("2025")]
    assert pattern_rows == [trans_lines[1], trans_lines[2], trans_lines[8]]  # tids 2, 3, 9


def test_accounts_entities_and_legacy(raw_paths: DatasetPaths, maps: Mappings,
                                      tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.csv"
    legacy.write_text(LEGACY_ACCOUNTS)
    manifest = _run(raw_paths, maps, legacy)
    assert manifest["risk_source"] == "legacy-carryover"
    accounts = pl.read_csv(raw_paths.out_accounts, infer_schema=False)
    by_account = {r["Account Number"] + "@" + r["Bank ID"]: r
                  for r in accounts.iter_rows(named=True)}
    assert by_account["C1@126"]["Bank Name"] == "Indodax"
    assert by_account["A1@10"]["Bank Name"] == "Bank Rakyat Indonesia"
    assert by_account["A1@10"]["risk_category"] == "Low"
    entities = pl.read_csv(raw_paths.out_entities, infer_schema=False)
    assert entities.height == 7
    e1 = entities.filter(pl.col("Entity ID") == "E1").row(0, named=True)
    assert e1["Registration Date"] < "2025-09-04"
    assert by_account["A1@10"]["Entity Name"] == e1["Entity Name"]


def test_deterministic(tmp_path: Path, maps: Mappings) -> None:
    a = write_raw(tmp_path / "a")
    b = write_raw(tmp_path / "b")
    _run(a, maps)
    _run(b, maps)
    for attr in OUTPUTS:
        assert getattr(a, attr).read_bytes() == getattr(b, attr).read_bytes(), attr


def test_streaming_matches_in_memory(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    frames = localize_frames(
        scan_raw_trans(raw_paths.raw_trans).collect(),
        read_raw_accounts(raw_paths.raw_accounts),
        maps,
    )
    assert frames["trans"].write_csv() == raw_paths.out_trans.read_text()
    assert frames["entities"].write_csv() == raw_paths.out_entities.read_text()
    assert frames["accounts"].write_csv() == raw_paths.out_accounts.read_text()


def test_inverting_labels_changes_only_labels(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans).collect()
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    inverted = raw.with_columns(
        (1 - pl.col("is_laundering").cast(pl.Int8)).cast(pl.String).alias("is_laundering")
    )
    normal = localize_frames(raw, accounts, maps)
    flipped = localize_frames(inverted, accounts, maps)
    assert normal["trans"].drop("Is Laundering").equals(flipped["trans"].drop("Is Laundering"))
    assert not normal["trans"]["Is Laundering"].equals(flipped["trans"]["Is Laundering"])
    assert normal["entities"].equals(flipped["entities"])
    assert normal["accounts"].equals(flipped["accounts"])


def test_disk_space_guard(raw_paths: DatasetPaths, maps: Mappings) -> None:
    with pytest.raises(DiskSpaceError):
        run_localize(raw_paths, maps, None, min_free_bytes=10**18)


def test_missing_raw_input(tmp_path: Path, maps: Mappings) -> None:
    with pytest.raises(RawInputError):
        run_localize(dataset_paths(tmp_path, "small"), maps, None, min_free_bytes=0)
