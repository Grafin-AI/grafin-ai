from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from garda_training.cli import main
from garda_training.train.export import rescale
from garda_training.train.score import Thresholds, statuses
from garda_training.train.typology import TYPOLOGIES

PAPER = str(Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml")


def _th(blocked: float, flagged: float) -> Thresholds:
    return Thresholds(blocked, flagged, 0.9)


def test_rescale_band_mapping() -> None:
    th = _th(0.8, 0.2)
    prob = np.array([0.0, 0.1, 0.2, 0.5, 0.8, 0.9, 1.0], dtype=np.float32)
    got = rescale(prob, th)
    assert got.tolist() == pytest.approx([0.0, 0.2, 0.4, 0.55, 0.7, 0.85, 1.0], abs=1e-4)


def test_rescale_monotone_and_bands_match_status() -> None:
    th = _th(0.63, 0.07)
    prob = np.sort(np.random.default_rng(0).random(5000).astype(np.float32))
    prob = np.concatenate([prob, np.array([0.07, 0.63, 0.0, 1.0], dtype=np.float32)])
    prob.sort()
    score = rescale(prob, th)
    assert np.all(np.diff(score) >= 0)
    assert score.min() >= 0.0 and score.max() <= 1.0
    assert np.array_equal(score, np.round(score, 4))
    st = statuses(prob, th)
    assert np.all(score[st == "approved"] < 0.4)
    assert np.all((score[st == "flagged"] >= 0.4) & (score[st == "flagged"] < 0.7))
    assert np.all(score[st == "blocked"] >= 0.7)


def test_rescale_rounding_stays_in_band() -> None:
    th = _th(0.5, 0.25)
    prob = np.array([0.2499999, 0.4999999], dtype=np.float64)
    assert rescale(prob, th).tolist() == [0.3999, 0.6999]


def test_rescale_edge_cases() -> None:
    same = _th(0.5, 0.5)  # empty flagged band
    assert rescale(np.array([0.25, 0.5, 0.75]), same).tolist() == pytest.approx([0.2, 0.7, 0.85])
    top = _th(1.0, 0.5)  # blocked only at prob == 1
    assert rescale(np.array([0.75, 1.0]), top).tolist() == pytest.approx([0.55, 1.0])
    zero = _th(0.0, 0.0)  # everything blocked
    assert rescale(np.array([0.0, 0.5, 1.0]), zero).tolist() == pytest.approx([0.7, 0.85, 1.0])


def test_cli_export_scores_end_to_end(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    runs, cache = str(tmp_path / "runs"), str(tmp_path / "cache")
    common = ["--runs-dir", runs, "--cache-dir", cache]
    assert main(["export-scores", "--run", "nope", "--runs-dir", runs]) == 3
    train = [
        *("gnn", "--data", str(fixture_paths[0]), "--source", "raw", "--config", PAPER),
        *("--epochs", "1", "--batch-size", "32", "--num-neighs", "10", "10"),
        *("--device", "cpu", "--run-id", "e", "--no-mlflow", *common),
    ]
    assert main(train) == 0
    assert main(["export-scores", "--run", "e", *common]) == 3  # not scored yet
    assert main(["score", "--run", "e", "--device", "cpu", *common]) == 0
    assert main(["export-scores", "--run", "e", *common]) == 0

    out = tmp_path / "runs" / "e" / "scores"
    parquet = pl.read_parquet(out / "scores.parquet").sort("transaction_id")
    with (out / "scores.csv").open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    assert header == ["transaction_id", "fraud_score", "prob", "status", "typology"]
    assert len(rows) == parquet.height
    data = json.loads((tmp_path / "runs" / "e" / "data.json").read_text())
    assert len(rows) == data["counts"]["val"] + data["counts"]["test"]
    ids = [int(r[0]) for r in rows]
    assert ids == sorted(ids) == parquet["transaction_id"].to_list()
    assert [r[3] for r in rows] == parquet["status"].to_list()
    for r in rows:
        assert 0.0 <= float(r[1]) <= 1.0
        assert (r[4] == "") if r[3] == "approved" else (r[4] in TYPOLOGIES)
    probs = np.array([float(r[2]) for r in rows])
    assert np.allclose(probs, parquet["prob"].to_numpy(), atol=1e-6)

    meta = json.loads((out / "export_meta.json").read_text())
    config = json.loads((tmp_path / "runs" / "e" / "config.json").read_text())
    assert meta["run_id"] == "e" and meta["splits"] == ["val", "test"]
    assert meta["n_rows"] == len(rows)
    assert meta["dataset_sha256"] == config["data"]["sha256"]
    assert meta["thresholds"]["selected_on"] == "val"
    assert [b["fraud_score"] for b in meta["rescale_breakpoints"]] == [0.0, 0.4, 0.7, 1.0]
    assert sum(meta["typology_counts"].values()) == sum(1 for r in rows if r[3] != "approved")

    assert main(["export-scores", "--run", "e", *common, "--splits", "test"]) == 0
    with (out / "scores.csv").open(newline="") as fh:
        n_test = sum(1 for _ in fh) - 1
    assert n_test == data["counts"]["test"] == parquet.filter(pl.col("split") == "test").height
