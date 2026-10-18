"""Typed GNN configuration loaded from TOML (configs/paper_pna.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from grafin_training.errors import ConfigError

SUPPORTED_MODELS = ("pna",)

_SECTIONS: dict[str, dict[str, type]] = {
    "model": {
        "name": str,
        "n_hidden": int,
        "n_gnn_layers": int,
        "dropout": float,
        "final_dropout": float,
        "edge_updates": bool,
    },
    "flags": {"reverse_mp": bool, "ports": bool, "ego": bool, "tds": bool},
    "train": {
        "lr": float,
        "w_ce1": float,
        "w_ce2": float,
        "epochs": int,
        "batch_size": int,
        "num_neighs": list,
        "amp": bool,
        "patience": int,
        "max_hours": float,
    },
    "split": {"fractions": list},
}


@dataclass(frozen=True)
class ModelConfig:
    name: str
    n_hidden: int
    n_gnn_layers: int
    dropout: float
    final_dropout: float
    edge_updates: bool


@dataclass(frozen=True)
class FlagsConfig:
    reverse_mp: bool
    ports: bool
    ego: bool
    tds: bool


@dataclass(frozen=True)
class TrainConfig:
    lr: float
    w_ce1: float
    w_ce2: float
    epochs: int
    batch_size: int
    num_neighs: tuple[int, ...]
    amp: bool
    patience: int  # stop after this many epochs without a validation improvement; 0 = off
    max_hours: float  # stop before an epoch would exceed this wall-clock budget; 0 = off


@dataclass(frozen=True)
class SplitConfig:
    fractions: tuple[float, float, float]


@dataclass(frozen=True)
class GnnConfig:
    model: ModelConfig
    flags: FlagsConfig
    train: TrainConfig
    split: SplitConfig

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    sec = raw.get(name)
    if not isinstance(sec, dict):
        raise ConfigError(f"missing [{name}] section")
    spec = _SECTIONS[name]
    unknown = sorted(set(sec) - set(spec))
    missing = sorted(set(spec) - set(sec))
    if unknown:
        raise ConfigError(f"[{name}] unknown keys: {unknown}")
    if missing:
        raise ConfigError(f"[{name}] missing keys: {missing}")
    for key, typ in spec.items():
        value = sec[key]
        if typ is float:
            ok = _is_number(value)
        elif typ is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = isinstance(value, typ)
        if not ok:
            raise ConfigError(f"[{name}].{key} must be {typ.__name__}, got {value!r}")
    return sec


def parse_gnn_config(raw: dict[str, Any]) -> GnnConfig:
    unknown = sorted(set(raw) - set(_SECTIONS))
    if unknown:
        raise ConfigError(f"unknown sections: {unknown}")
    m, f, t, s = (_section(raw, n) for n in ("model", "flags", "train", "split"))
    if m["name"] not in SUPPORTED_MODELS:
        raise ConfigError(f"[model].name must be one of {SUPPORTED_MODELS}, got {m['name']!r}")
    if m["n_hidden"] < 5 or m["n_gnn_layers"] < 1:
        raise ConfigError("[model] needs n_hidden >= 5 and n_gnn_layers >= 1")
    if not (0 <= m["dropout"] < 1 and 0 <= m["final_dropout"] < 1):
        raise ConfigError("[model] dropouts must be in [0, 1)")
    neighs = t["num_neighs"]
    if not neighs or not all(
        isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in neighs
    ):
        raise ConfigError("[train].num_neighs must be a non-empty list of positive integers")
    if len(neighs) != m["n_gnn_layers"]:
        raise ConfigError("[train].num_neighs needs exactly one entry per GNN layer")
    if t["lr"] <= 0 or t["w_ce1"] <= 0 or t["w_ce2"] <= 0:
        raise ConfigError("[train] lr and class weights must be > 0")
    if t["patience"] < 0 or t["max_hours"] < 0:
        raise ConfigError("[train] patience and max_hours must be >= 0 (0 = off)")
    if t["epochs"] < 1 or t["batch_size"] < 1:
        raise ConfigError("[train] epochs and batch_size must be >= 1")
    fr = s["fractions"]
    if len(fr) != 3 or not all(_is_number(x) and x > 0 for x in fr) or abs(sum(fr) - 1) > 1e-9:
        raise ConfigError("[split].fractions must be three positive numbers summing to 1")
    return GnnConfig(
        model=ModelConfig(
            name=m["name"],
            n_hidden=m["n_hidden"],
            n_gnn_layers=m["n_gnn_layers"],
            dropout=float(m["dropout"]),
            final_dropout=float(m["final_dropout"]),
            edge_updates=m["edge_updates"],
        ),
        flags=FlagsConfig(**f),
        train=TrainConfig(
            lr=float(t["lr"]),
            w_ce1=float(t["w_ce1"]),
            w_ce2=float(t["w_ce2"]),
            epochs=t["epochs"],
            batch_size=t["batch_size"],
            num_neighs=tuple(neighs),
            amp=t["amp"],
            patience=t["patience"],
            max_hours=float(t["max_hours"]),
        ),
        split=SplitConfig(fractions=(float(fr[0]), float(fr[1]), float(fr[2]))),
    )


def load_gnn_config(path: Path, overrides: dict[str, Any] | None = None) -> GnnConfig:
    """Load a TOML config; `overrides` maps "section.key" to a replacement value."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    for dotted, value in (overrides or {}).items():
        section, _, key = dotted.partition(".")
        if section not in raw or not isinstance(raw[section], dict):
            raise ConfigError(f"override {dotted!r} targets a missing section")
        raw[section][key] = value
    return parse_gnn_config(raw)
