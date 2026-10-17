from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from garda_training.errors import ConfigError
from garda_training.tracking import RunDir, Tracker, environment_info, flatten, make_run_id


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
