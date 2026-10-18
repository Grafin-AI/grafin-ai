import json

import polars as pl
import pytest

import grafin_ai_dataset.validate as validate_mod
from grafin_ai_dataset.hashing import sha256_file
from grafin_ai_dataset.localize import run_localize
from grafin_ai_dataset.mappings import Mappings
from grafin_ai_dataset.paths import DatasetPaths
from grafin_ai_dataset.validate import Check, ValidationReport, validate_dataset

ALL_CHECKS = {
    "header", "row_count", "node_merge", "labels", "graph_keys", "fx", "time", "order",
    "channels", "label_independence", "patterns", "entities", "manifest",
}


@pytest.fixture
def built(raw_paths: DatasetPaths, maps: Mappings) -> DatasetPaths:
    run_localize(raw_paths, maps, None, min_free_bytes=0)
    return raw_paths


def _check(report: ValidationReport, name: str) -> Check:
    return next(c for c in report.checks if c.name == name)


def _edit_trans(paths: DatasetPaths, row: int, column: str, value: str) -> None:
    """Overwrite one field of data row ``row`` (1-based == transaction_id)."""
    lines = paths.out_trans.read_text().splitlines()
    header = lines[0].split(",")
    fields = lines[row].split(",")
    fields[header.index(column)] = value
    lines[row] = ",".join(fields)
    paths.out_trans.write_text("\n".join(lines) + "\n")


def test_fresh_build_passes(built: DatasetPaths, maps: Mappings) -> None:
    report = validate_dataset(built, maps)
    assert report.ok, report.render()
    assert {c.name for c in report.checks} == ALL_CHECKS
    assert any("Pemindahbukuan" in line for line in report.distribution)
    assert not built.tmp_dir.exists()


@pytest.mark.parametrize(
    ("column", "value", "check"),
    [
        ("Is Laundering", "1", "labels"),
        ("Account", "ZZ", "graph_keys"),
        ("Amount Paid", "1", "fx"),
        ("Receiving Currency", "USD", "fx"),
        ("Timestamp", "2025/09/04 00:21", "time"),
        ("Payment Format", "RTGS", "channels"),
    ],
)
def test_corrupted_value_is_caught(built: DatasetPaths, maps: Mappings, column: str,
                                   value: str, check: str) -> None:
    _edit_trans(built, 1, column, value)
    report = validate_dataset(built, maps)
    assert not _check(report, check).ok
    assert not _check(report, "manifest").ok  # the output hash changed too


def test_dropped_row_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_trans.read_text().splitlines()
    built.out_trans.write_text("\n".join(lines[:-1]) + "\n")
    assert not _check(validate_dataset(built, maps), "row_count").ok


def test_swapped_rows_are_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_trans.read_text().splitlines()
    lines[2], lines[3] = lines[3], lines[2]  # tids 2 and 3: 08:00 and 08:05
    built.out_trans.write_text("\n".join(lines) + "\n")
    assert not _check(validate_dataset(built, maps), "order").ok


def test_swap_across_day_boundary_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_trans.read_text().splitlines()
    lines[5], lines[6] = lines[6], lines[5]  # tid 5 (09/04 09:30) and tid 6 (09/05 10:00)
    built.out_trans.write_text("\n".join(lines) + "\n")
    manifest = json.loads(built.manifest.read_text())
    manifest["outputs"][built.out_trans.name] = sha256_file(built.out_trans)
    built.manifest.write_text(json.dumps(manifest))
    report = validate_dataset(built, maps)
    assert not _check(report, "order").ok
    assert _check(report, "manifest").ok


def test_typologies_tamper_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_typologies.read_text().splitlines()
    built.out_typologies.write_text("\n".join(lines[:-1]) + "\n")
    assert not _check(validate_dataset(built, maps), "patterns").ok


def test_pattern_line_tamper_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    text = built.out_patterns.read_text().replace("2025/09/04 08:00", "2025/09/04 08:01")
    built.out_patterns.write_text(text)
    assert not _check(validate_dataset(built, maps), "patterns").ok


def test_unknown_institution_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    built.out_accounts.write_text(built.out_accounts.read_text().replace("Indodax", "Bank Palsu"))
    assert not _check(validate_dataset(built, maps), "entities").ok


def test_late_registration_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    ents = pl.read_csv(built.out_entities, infer_schema=False).with_columns(
        pl.when(pl.col("Entity ID") == "E1").then(pl.lit("2030-01-01"))
        .otherwise(pl.col("Registration Date")).alias("Registration Date")
    )
    ents.write_csv(built.out_entities)
    assert not _check(validate_dataset(built, maps), "entities").ok


def test_manifest_tamper_fails_only_manifest(built: DatasetPaths, maps: Mappings) -> None:
    manifest = json.loads(built.manifest.read_text())
    manifest["mappings"]["fx_rates.csv"] = "0" * 64
    built.manifest.write_text(json.dumps(manifest))
    assert validate_dataset(built, maps).failed() == ["manifest"]


def test_label_leak_is_caught(built: DatasetPaths, maps: Mappings,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    real = validate_mod.localize_frames

    def leaky(raw: pl.DataFrame, accounts: pl.DataFrame, m: Mappings) -> dict[str, pl.DataFrame]:
        frames = real(raw, accounts, m)
        frames["trans"] = frames["trans"].with_columns(
            pl.when(pl.col("Is Laundering") == 1).then(pl.lit("LEAK"))
            .otherwise(pl.col("Payment Format")).alias("Payment Format")
        )
        return frames

    monkeypatch.setattr(validate_mod, "localize_frames", leaky)
    assert not _check(validate_dataset(built, maps), "label_independence").ok


def test_node_merge_is_caught(raw_paths: DatasetPaths, maps: Mappings) -> None:
    # A1 now appears under both "010" and "0010": two IBM nodes would merge into one.
    text = raw_paths.raw_trans.read_text().replace(
        "2022/09/01 09:30,0010,A3", "2022/09/01 09:30,0010,A1"
    )
    raw_paths.raw_trans.write_text(text)
    run_localize(raw_paths, maps, None, min_free_bytes=0)
    assert not _check(validate_dataset(raw_paths, maps), "node_merge").ok
