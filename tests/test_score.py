from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from garda_training.config import GnnConfig, load_gnn_config
from garda_training.data.prepare import PreparedData, prepare_dataset
from garda_training.errors import ConfigError
from garda_training.graph.loaders import make_loader
from garda_training.tracking import RunDir, Tracker
from garda_training.train import gnn
from garda_training.train.paper import paper_arrays, split_graphs
from garda_training.train.score import (
    Thresholds,
    causal_day_scores,
    choose_thresholds,
    restore_model,
    score_seeds,
    statuses,
)

PAPER = Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml"
CPU = torch.device("cpu")


def _cfg(**overrides: Any) -> GnnConfig:
    base: dict[str, Any] = {"train.batch_size": 32, "train.num_neighs": [10, 10]}
    return load_gnn_config(PAPER, {**base, **overrides})


def _prepared(fixture_paths: tuple[Path, Path], tmp_path: Path) -> PreparedData:
    return prepare_dataset(fixture_paths[0], "raw", tmp_path / "cache")


def _fresh_model(prepared: PreparedData, cfg: GnnConfig) -> torch.nn.Module:
    """An untrained model: injection and causality do not depend on the weights."""
    train = split_graphs(prepared, paper_arrays(prepared, cfg), cfg)["train"]
    gnn.set_seed(1)
    loader = make_loader(
        train, num_neighs=cfg.train.num_neighs, batch_size=32, shuffle=True, ego=cfg.flags.ego
    )
    return gnn.build_model(next(iter(loader)), cfg).eval()


# --- thresholds -------------------------------------------------------------------------------


def test_choose_thresholds_f1_and_recall() -> None:
    y = np.array([1, 0, 0, 1, 1])
    prob = np.array([0.2, 0.3, 0.5, 0.8, 0.9])
    th = choose_thresholds(y, prob, 0.9)
    assert th.blocked == pytest.approx(0.8)  # F1 0.8 (P 1, R 2/3) beats 0.75 at 0.2
    assert th.flagged == pytest.approx(0.2)  # largest threshold keeping recall >= 0.9
    st = statuses(np.array([0.1, 0.2, 0.5, 0.8, 0.95]), th)
    assert st.tolist() == ["approved", "flagged", "flagged", "blocked", "blocked"]
    assert th.to_dict()["selected_on"] == "val"


def test_flagged_is_capped_at_blocked() -> None:
    y = np.array([0, 0, 1, 1, 0, 1])
    prob = np.array([0.1, 0.2, 0.3, 0.8, 0.4, 0.9])
    th = choose_thresholds(y, prob, 0.6)  # recall 2/3 already at 0.8 > blocked (0.3)
    assert th.blocked == pytest.approx(0.3) and th.flagged == th.blocked
    assert statuses(np.array([0.29, 0.3]), th).tolist() == ["approved", "blocked"]


def test_choose_thresholds_degenerate() -> None:
    with pytest.raises(ConfigError, match="no laundering"):
        choose_thresholds(np.zeros(5, int), np.linspace(0, 1, 5))
    with pytest.raises(ConfigError, match="no validation rows"):
        choose_thresholds(np.zeros(0, int), np.zeros(0))
    with pytest.raises(ConfigError, match="flag-recall"):
        choose_thresholds(np.array([0, 1]), np.array([0.1, 0.9]), 0.0)
    th = choose_thresholds(np.ones(3, int), np.array([0.2, 0.5, 0.7]))  # all positive
    assert th == Thresholds(0.2, 0.2, 0.9)


# --- model restore ----------------------------------------------------------------------------


def test_restored_model_reproduces_trained_model(
    fixture_paths: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = _prepared(fixture_paths, tmp_path)
    cfg = _cfg(**{"train.epochs": 2})
    arrays = paper_arrays(prepared, cfg)
    graphs = split_graphs(prepared, arrays, cfg)
    captured: list[torch.nn.Module] = []
    real_build = gnn.build_model

    def capture(*args: Any, **kwargs: Any) -> torch.nn.Module:
        model = real_build(*args, **kwargs)
        captured.append(model)
        return model

    monkeypatch.setattr(gnn, "build_model", capture)
    run = RunDir.create(tmp_path / "runs", "r")
    gnn.set_seed(1)
    gnn.train_gnn(graphs, cfg, CPU, run, Tracker(None, "t", {}, {}))
    monkeypatch.undo()
    trained = captured[0]  # the in-memory model after the last epoch

    last = gnn.load_checkpoint(run.checkpoints / "last.pt")
    assert "deg" in last and "deg" in gnn.load_checkpoint(run.checkpoints / "best.pt")
    legacy = {k: v for k, v in last.items() if k != "deg"}  # checkpoints of in-flight runs

    def preds(model: torch.nn.Module) -> np.ndarray:
        torch.manual_seed(0)
        return gnn.predict(model, graphs["test"], cfg, CPU).prob

    want = preds(trained)
    np.testing.assert_array_equal(preds(restore_model(graphs["train"], cfg, 1, legacy)), want)
    np.testing.assert_array_equal(preds(restore_model(graphs["train"], cfg, 1, last)), want)
    # PyG 2.6 keeps PNA's average degrees as state_dict buffers, so load_state_dict restores
    # them whatever histogram the rebuilt model was constructed with.
    wrong = {**last, "deg": torch.tensor([0, 1])}  # every node has degree 1
    np.testing.assert_array_equal(preds(restore_model(graphs["train"], cfg, 1, wrong)), want)
    deg = last["deg"].double()
    avg_lin = float((torch.arange(deg.numel()) * deg).sum() / deg.sum())
    buffers = [v for k, v in last["model"].items() if k.endswith("avg_deg_lin")]
    assert buffers and all(float(b) == pytest.approx(avg_lin) for b in buffers)


# --- seed injection ---------------------------------------------------------------------------


@pytest.mark.parametrize("reverse_mp", [True, False])
def test_every_seed_scored_once_with_tiny_fanout(
    fixture_paths: tuple[Path, Path], tmp_path: Path, reverse_mp: bool
) -> None:
    prepared = _prepared(fixture_paths, tmp_path)
    cfg = _cfg(**{"train.num_neighs": [1, 1], "flags.reverse_mp": reverse_mp})
    model = _fresh_model(prepared, cfg)
    graph = split_graphs(prepared, paper_arrays(prepared, cfg), cfg)["val"]
    kw: dict[str, Any] = {"num_neighs": (1, 1), "batch_size": 16, "ego": True, "device": CPU}

    torch.manual_seed(0)
    plain, none = score_seeds(model, graph, inject=False, **kw)
    torch.manual_seed(0)
    full, injected = score_seeds(model, graph, **kw)
    assert none == 0 and plain.shape == full.shape == (graph.seeds.shape[0],)
    missing = np.isnan(plain)
    assert missing.any() and int(missing.sum()) == injected  # each missing seed injected once
    assert np.isfinite(full).all() and ((full >= 0) & (full <= 1)).all()


@pytest.mark.parametrize("reverse_mp", [True, False])
def test_injected_path_matches_plain_path_with_generous_fanout(
    fixture_paths: tuple[Path, Path], tmp_path: Path, reverse_mp: bool
) -> None:
    prepared = _prepared(fixture_paths, tmp_path)
    cfg = _cfg(**{"train.num_neighs": [100, 100], "flags.reverse_mp": reverse_mp})
    model = _fresh_model(prepared, cfg)
    graph = split_graphs(prepared, paper_arrays(prepared, cfg), cfg)["val"]
    kw: dict[str, Any] = {"num_neighs": (100, 100), "batch_size": 32, "ego": True, "device": CPU}
    torch.manual_seed(0)
    plain, _ = score_seeds(model, graph, inject=False, **kw)
    torch.manual_seed(0)
    full, injected = score_seeds(model, graph, **kw)
    assert injected == 0 and np.isfinite(plain).all()
    np.testing.assert_array_equal(full, plain)
    torch.manual_seed(0)
    reference = gnn.predict(model, graph, cfg, CPU)  # upstream eval path, batch order
    assert reference.coverage == 1.0
    np.testing.assert_allclose(np.sort(reference.prob), np.sort(full), rtol=0, atol=1e-6)


# --- causality --------------------------------------------------------------------------------


def test_day_scores_ignore_later_days_and_all_labels(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    prepared = _prepared(fixture_paths, tmp_path)
    cfg = _cfg(**{"train.num_neighs": [2, 2]})
    model = _fresh_model(prepared, cfg)
    arrays = paper_arrays(prepared, cfg)
    days = [*arrays.split.val_days, *arrays.split.test_days]
    assert days == [4, 5]

    def run(p: PreparedData) -> dict[int, np.ndarray]:
        scores = causal_day_scores(
            model, p, paper_arrays(p, cfg), cfg, days, batch_size=8, device=CPU, seed=1
        )
        return {d: s.prob for d, s in scores.items()}

    base = run(prepared)
    assert all(np.isfinite(v).all() for v in base.values())
    assert sum(v.size for v in base.values()) == int(np.isin(prepared.day_idx, days).sum())

    # Flip every validation/test label: no score may change.
    y = prepared.y.copy()
    held_out = np.isin(prepared.day_idx, days)
    y[held_out] = 1 - y[held_out]
    flipped = run(replace(prepared, y=y))
    for d in days:
        np.testing.assert_array_equal(flipped[d], base[d])

    # Rewrite day-5 amounts and receivers: day-4 scores must not move, day-5 scores must.
    later = prepared.day_idx > 4
    amounts = prepared.base.copy()
    amounts[later, 1] *= 1000.0
    dst = prepared.dst.copy()
    dst[later] = (dst[later] + 7) % prepared.num_nodes
    perturbed = run(replace(prepared, base=amounts, dst=dst))
    np.testing.assert_array_equal(perturbed[4], base[4])
    assert not np.allclose(perturbed[5], base[5])
