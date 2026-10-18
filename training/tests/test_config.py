from __future__ import annotations

from pathlib import Path

import pytest

from grafin_training.config import load_gnn_config
from grafin_training.errors import ConfigError

PAPER = Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml"


def test_paper_config_matches_upstream() -> None:
    cfg = load_gnn_config(PAPER)
    assert cfg.model.name == "pna" and cfg.model.n_hidden == 20 and cfg.model.n_gnn_layers == 2
    assert cfg.model.dropout == 0.08340440094051481
    assert cfg.model.final_dropout == 0.28812979737686323
    assert cfg.model.edge_updates
    assert (cfg.flags.reverse_mp, cfg.flags.ports, cfg.flags.ego, cfg.flags.tds) == (
        True,
        True,
        True,
        False,
    )
    assert cfg.train.lr == 0.0006116418195373612
    assert (cfg.train.w_ce1, cfg.train.w_ce2) == (1.0003967674742307, 7.077633468006714)
    assert (cfg.train.epochs, cfg.train.batch_size, cfg.train.num_neighs) == (100, 8192, (100, 100))
    assert (cfg.train.patience, cfg.train.max_hours) == (0, 0.0)
    assert cfg.split.fractions == (0.6, 0.2, 0.2)


def test_overrides_apply() -> None:
    cfg = load_gnn_config(PAPER, {"train.epochs": 2, "train.num_neighs": [5, 5]})
    assert cfg.train.epochs == 2 and cfg.train.num_neighs == (5, 5)


@pytest.mark.parametrize(
    "edit, message",
    [
        (("model", "name", "gin"), "name must be one of"),
        (("model", "bogus", 1), "unknown keys"),
        (("train", "num_neighs", [10]), "one entry per GNN layer"),
        (("train", "epochs", 0), "epochs and batch_size"),
        (("split", "fractions", [0.5, 0.2, 0.2]), "summing to 1"),
        (("flags", "ego", 1), "must be bool"),
    ],
)
def test_invalid_configs(tmp_path: Path, edit: tuple[str, str, object], message: str) -> None:
    import tomllib

    raw = tomllib.loads(PAPER.read_text())
    section, key, value = edit
    raw[section][key] = value
    from grafin_training.config import parse_gnn_config

    with pytest.raises(ConfigError, match=message):
        parse_gnn_config(raw)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_gnn_config(tmp_path / "nope.toml")
