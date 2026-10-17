from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from garda_training.cli import main

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
