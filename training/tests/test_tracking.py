from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from grafin_training.errors import ConfigError
from grafin_training.tracking import (
    RunDir,
    Tracker,
    environment_info,
    flatten,
    log_run_to_mlflow,
    make_run_id,
)


def test_run_id_and_run_dir(tmp_path: Path) -> None:
    rid = make_run_id("HI-Small_Trans", "paper", 2, datetime(2026, 10, 17, 3, 4, 5, tzinfo=UTC))
    assert rid == "20261017-030405-HI-Small_Trans-paper-s2"
    run = RunDir.create(tmp_path, rid)
    run.write_json("x.json", {"a": 1})
    assert run.read_json("x.json") == {"a": 1}
    with pytest.raises(ConfigError, match="already exists"):
        RunDir.create(tmp_path, rid)
    with pytest.raises(ConfigError, match="no run to resume"):
        RunDir.open(tmp_path, "missing")


def test_flatten_and_env() -> None:
    assert flatten({"a": {"b": 1, "c": {"d": 2}}, "e": 3}) == {"a.b": 1, "a.c.d": 2, "e": 3}
    env = environment_info(torch.device("cpu"))
    assert {"git_sha", "git_dirty", "torch", "torch_geometric", "device"} <= set(env)


def test_tracker_logs_to_sqlite_and_never_raises(tmp_path: Path) -> None:
    uri = f"sqlite:///{tmp_path / 'mlruns' / 'mlflow.db'}"
    tracker = Tracker(uri, "run-a", {"gnn": {"lr": 0.1}}, {"protocol": "paper"})
    tracker.log_metrics({"f1_val": 0.5}, step=0)
    tracker.finish("FINISHED")
    assert (tmp_path / "mlruns" / "mlflow.db").is_file()
    broken = Tracker("notascheme://nowhere", "run-b", {}, {})  # must not raise
    broken.log_metrics({"x": 1.0})
    broken.finish("FINISHED")


def _fake_run(root: Path) -> Path:
    run = RunDir.create(root, "fake-run")
    run.write_json(
        "config.json", {"seed": 2, "data": {"source": "id"}, "gnn": {"train": {"lr": 0.1}}}
    )
    run.write_json("env.json", {"git_sha": "abc123"})
    run.write_json("data.json", {"meta": {"dataset": "HI-Small_Trans", "n_nodes": 10}})
    history = [
        {"epoch": 0, "loss": 0.5, "val_f1": 0.2, "test_f1": None},
        {"epoch": 1, "loss": 0.3, "val_f1": 0.4, "test_f1": 0.35},
    ]
    run.write_json("metrics.json", {"best_epoch": 1, "best_val_f1": 0.4, "history": history})
    (run.path / "scores").mkdir()
    thresholds = {"flagged": 0.12, "blocked": 0.58, "selected_on": "val"}
    (run.path / "scores" / "thresholds.json").write_text(json.dumps(thresholds))
    split = {"f1": 0.67, "pr_auc": 0.62, "roc_auc": 0.98, "status_counts": {"blocked": 3}}
    (run.path / "scores" / "score_metrics.json").write_text(
        json.dumps({"val": split, "test": split, "thresholds": thresholds})
    )
    (run.path / "scores" / "export_meta.json").write_text(
        json.dumps({"n_rows": 9, "typology_counts": {"Siklus Dana (Cycle)": 4}})
    )
    (run.path / "scores" / "scores.csv").write_text("big,file\n")
    return run.path


def test_log_run_to_mlflow(tmp_path: Path) -> None:
    import mlflow

    run_dir = _fake_run(tmp_path / "runs")
    store = tmp_path / "mlruns"
    uri = f"sqlite:///{store / 'mlflow.db'}"  # MLflow 3.x refuses the file store
    log_run_to_mlflow(run_dir, uri, experiment="test-exp")
    first = log_run_to_mlflow(run_dir, uri, experiment="test-exp")  # idempotent: replaces

    mlflow.set_tracking_uri(uri)
    runs = mlflow.search_runs(experiment_names=["test-exp"], output_format="list")
    assert [r.info.run_id for r in runs] == [first]
    run = runs[0]
    assert run.info.run_name == "fake-run"
    assert run.data.params["gnn.train.lr"] == "0.1"
    assert run.data.params["threshold.flagged"] == "0.12"
    assert run.data.metrics["final_test_f1"] == pytest.approx(0.67)
    assert run.data.metrics["final_val_status_blocked"] == 3
    assert run.data.metrics["typology_siklus_dana_cycle"] == 4
    assert run.data.tags["model"] == "Multi-GNN PNA"
    assert run.data.tags["git_commit"] == "abc123"
    assert run.data.tags["dataset"] == "HI-Small_Trans (id)"
    history = mlflow.MlflowClient().get_metric_history(first, "val_f1")
    assert [(m.step, m.value) for m in history] == [(0, 0.2), (1, 0.4)]
    assert len(mlflow.MlflowClient().get_metric_history(first, "test_f1")) == 1
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(first)}
    assert {"config.json", "metrics.json", "scores", "typology_counts.json"} <= artifacts
    scored = {a.path for a in mlflow.MlflowClient().list_artifacts(first, "scores")}
    assert scored == {
        "scores/score_metrics.json",
        "scores/thresholds.json",
        "scores/export_meta.json",
    }


def test_log_run_to_mlflow_missing_run(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config.json missing"):
        log_run_to_mlflow(tmp_path / "nope", f"sqlite:///{tmp_path / 'mlflow.db'}")
