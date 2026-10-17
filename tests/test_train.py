from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from garda_training.config import GnnConfig, load_gnn_config
from garda_training.data.prepare import prepare_dataset
from garda_training.errors import TrainingDivergedError
from garda_training.graph.build import SplitGraph
from garda_training.tracking import RunDir, Tracker
from garda_training.train.gnn import load_checkpoint, set_seed, train_gnn
from garda_training.train.paper import paper_inputs

PAPER = Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml"


def _setup(
    fixture_paths: tuple[Path, Path], tmp_path: Path, epochs: int
) -> tuple[dict[str, SplitGraph], GnnConfig]:
    cfg = load_gnn_config(
        PAPER, {"train.epochs": epochs, "train.batch_size": 32, "train.num_neighs": [10, 10]}
    )
    prepared = prepare_dataset(fixture_paths[0], "raw", tmp_path / "cache")
    graphs, _ = paper_inputs(prepared, cfg)
    return graphs, cfg


def _train(graphs: dict[str, SplitGraph], cfg: GnnConfig, run: RunDir, resume: bool = False):  # type: ignore[no-untyped-def]
    if not resume:
        set_seed(1)
    return train_gnn(
        graphs, cfg, torch.device("cpu"), run, Tracker(None, "t", {}, {}), resume=resume
    )


def test_train_two_epochs_writes_checkpoints(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=2)
    run = RunDir.create(tmp_path / "runs", "r1")
    result = _train(graphs, cfg, run)
    assert [r.epoch for r in result.history] == [0, 1]
    assert 0 <= result.best_epoch <= 1
    assert all(np.isfinite(r.loss) for r in result.history)
    best = load_checkpoint(run.checkpoints / "best.pt")
    assert all(t.device.type == "cpu" for t in best["model"].values())
    assert best["epoch"] == result.best_epoch


def test_resume_reproduces_uninterrupted_run(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg3 = _setup(fixture_paths, tmp_path, epochs=3)
    straight = _train(graphs, cfg3, RunDir.create(tmp_path / "runs", "straight"))

    _, cfg1 = _setup(fixture_paths, tmp_path, epochs=1)
    run = RunDir.create(tmp_path / "runs", "interrupted")
    _train(graphs, cfg1, run)  # "crash" after epoch 0
    resumed = _train(graphs, cfg3, run, resume=True)

    assert [r.loss for r in resumed.history] == [r.loss for r in straight.history]
    assert [r.val_f1 for r in resumed.history] == [r.val_f1 for r in straight.history]


def test_nan_loss_aborts_and_keeps_last_good_checkpoint(
    fixture_paths: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=2)
    run = RunDir.create(tmp_path / "runs", "nan")
    _train(
        graphs,
        load_gnn_config(
            PAPER, {"train.epochs": 1, "train.batch_size": 32, "train.num_neighs": [10, 10]}
        ),
        run,
    )
    before = (run.checkpoints / "last.pt").read_bytes()

    def nan_loss(self: torch.nn.Module, *args: object, **kwargs: object) -> torch.Tensor:
        return torch.tensor(float("nan"), requires_grad=True)

    monkeypatch.setattr(torch.nn.CrossEntropyLoss, "forward", nan_loss)
    with pytest.raises(TrainingDivergedError):
        _train(graphs, cfg, run, resume=True)
    assert (run.checkpoints / "last.pt").read_bytes() == before


def test_test_split_scored_only_when_validation_improves(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=4)
    result = _train(graphs, cfg, RunDir.create(tmp_path / "runs", "lazy-test"))
    best = -1.0
    for record in result.history:
        improved = record.val_f1 > best
        assert (record.test_f1 is not None) == improved
        best = max(best, record.val_f1)
    best_record = next(r for r in result.history if r.epoch == result.best_epoch)
    assert result.test_f1_at_best == best_record.test_f1


def test_patience_and_time_budget_stop_early(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, _ = _setup(fixture_paths, tmp_path, epochs=1)
    small = {"train.batch_size": 32, "train.num_neighs": [10, 10]}
    patient = load_gnn_config(PAPER, {**small, "train.epochs": 50, "train.patience": 1})
    result = _train(graphs, patient, RunDir.create(tmp_path / "runs", "patience"))
    assert result.stop_reason == "patience" and len(result.history) < 50
    assert result.history[-1].epoch - result.best_epoch == 1
    budget = load_gnn_config(PAPER, {**small, "train.epochs": 50, "train.max_hours": 1e-9})
    result = _train(graphs, budget, RunDir.create(tmp_path / "runs", "budget"))
    assert result.stop_reason == "time_budget" and len(result.history) == 1
    assert result.peak_host_rss_mb > 0
