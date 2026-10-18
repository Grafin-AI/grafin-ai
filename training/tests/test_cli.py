from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import torch

from garda_training.cli import main
from garda_training.data.prepare import prepare_dataset

PAPER = str(Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml")


def test_cli_prepare_then_gnn_then_compare(
    fixture_paths: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = str(fixture_paths[0])
    cache = str(tmp_path / "cache")
    assert main(["prepare", "--data", raw, "--source", "raw", "--cache-dir", cache]) == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta["n_edges"] == 229 and meta["laundering"] == 13
    assert main(["prepare", "--data", raw, "--source", "raw", "--cache-dir", cache]) == 0  # cached

    code = main(
        [
            "gnn",
            "--data",
            raw,
            "--source",
            "raw",
            "--config",
            PAPER,
            "--epochs",
            "2",
            "--batch-size",
            "32",
            "--num-neighs",
            "10",
            "10",
            "--device",
            "cpu",
            "--run-id",
            "smoke",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--cache-dir",
            cache,
            "--no-mlflow",
        ]
    )
    assert code == 0
    run = tmp_path / "runs" / "smoke"
    for name in ("config.json", "env.json", "data.json", "metrics.json", "log.txt"):
        assert (run / name).is_file(), name
    data = json.loads((run / "data.json").read_text())
    assert sum(data["counts"].values()) == 229
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["protocol"] == "paper" and len(metrics["history"]) == 2

    capsys.readouterr()
    assert main(["compare", "--runs-dir", str(tmp_path / "runs")]) == 0
    out = capsys.readouterr().out
    assert "| smoke |" in out and "HI-Fixture_Trans" in out


def test_cli_exit_codes(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    common = [
        "--runs-dir",
        str(tmp_path / "runs"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--no-mlflow",
    ]
    missing = ["gnn", "--data", str(tmp_path / "nope.csv"), "--source", "raw", "--device", "cpu"]
    assert main(missing + common) == 2
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("[model]\nname='gin'\n")
    assert (
        main(
            [
                "gnn",
                "--data",
                str(fixture_paths[0]),
                "--source",
                "raw",
                "--config",
                str(bad_cfg),
                "--device",
                "cpu",
                *common,
            ]
        )
        == 3
    )
    assert (
        main(
            [
                "gnn",
                "--data",
                str(fixture_paths[0]),
                "--source",
                "bogus",
                "--device",
                "cpu",
                *common,
            ]
        )
        == 3
    )
    if not torch.cuda.is_available():
        assert (
            main(
                [
                    "gnn",
                    "--data",
                    str(fixture_paths[0]),
                    "--source",
                    "raw",
                    "--device",
                    "cuda",
                    *common,
                ]
            )
            == 5
        )


def test_cli_score_writes_every_val_and_test_row_once(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    runs, cache = str(tmp_path / "runs"), str(tmp_path / "cache")
    common = ["--runs-dir", runs, "--cache-dir", cache]
    assert main(["score", "--run", "nope", *common]) == 3
    train = [
        *("gnn", "--data", str(fixture_paths[0]), "--source", "raw", "--config", PAPER),
        *("--epochs", "2", "--batch-size", "32", "--num-neighs", "10", "10"),
        *("--device", "cpu", "--run-id", "s", "--no-mlflow", *common),
    ]
    assert main(train) == 0
    assert main(["score", "--run", "s", "--device", "cpu", "--batch-size", "16", *common]) == 0
    out = tmp_path / "runs" / "s" / "scores"
    frame = pl.read_parquet(out / "scores.parquet")
    assert frame.columns == [
        "transaction_id",
        "day",
        "split",
        "ts",
        "prob",
        "status",
        "is_laundering",
    ]
    assert frame.schema["transaction_id"] == pl.Int64 and frame.schema["prob"] == pl.Float32

    prepared = prepare_dataset(fixture_paths[0], "raw", tmp_path / "cache")
    data = json.loads((tmp_path / "runs" / "s" / "data.json").read_text())
    held_out = np.isin(prepared.day_idx, data["split"]["val_days"] + data["split"]["test_days"])
    assert frame.height == int(held_out.sum()) == data["counts"]["val"] + data["counts"]["test"]
    assert sorted(frame["transaction_id"].to_list()) == sorted(
        (prepared.row[held_out] + 1).tolist()
    )
    assert set(frame["status"].unique()) <= {"approved", "flagged", "blocked"}
    assert set(frame["split"].unique()) == {"val", "test"}

    thresholds = json.loads((out / "thresholds.json").read_text())
    assert thresholds["selected_on"] == "val" and thresholds["flag_recall_target"] == 0.9
    assert thresholds["flagged"] <= thresholds["blocked"]
    metrics = json.loads((out / "score_metrics.json").read_text())
    assert metrics["val"]["n"] + metrics["test"]["n"] == frame.height
    assert sum(metrics["val"]["status_counts"].values()) == metrics["val"]["n"]
    assert [d["day"] for d in metrics["per_day"]] == sorted(frame["day"].unique().to_list())


def test_cli_resume_can_extend_the_budget(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    common = [
        "--runs-dir",
        str(tmp_path / "runs"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--no-mlflow",
        "--device",
        "cpu",
    ]
    first = ["gnn", "--data", str(fixture_paths[0]), "--source", "raw", "--config", PAPER]
    first += ["--epochs", "1", "--batch-size", "32", "--num-neighs", "10", "10"]
    first += ["--patience", "1", "--run-id", "r", *common]
    assert main(first) == 0
    # the training budget may change on resume; the model and loaders may not
    assert main(["gnn", "--resume", "r", "--batch-size", "64", *common]) == 3
    assert main(["gnn", "--resume", "r", "--epochs", "2", "--patience", "0", *common]) == 0
    run = tmp_path / "runs" / "r"
    train = json.loads((run / "config.json").read_text())["gnn"]["train"]
    assert train["epochs"] == 2 and train["patience"] == 0
    assert len(json.loads((run / "metrics.json").read_text())["history"]) == 2
