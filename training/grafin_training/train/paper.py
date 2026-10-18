"""Paper protocol inputs: upstream day split, train-only normalisation, three split graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import torch

from grafin_training.config import GnnConfig
from grafin_training.data.features import NormStats, apply_norm, fit_norm
from grafin_training.data.prepare import PreparedData
from grafin_training.data.split import DaySplit, paper_split, rows_for_days
from grafin_training.graph.build import SplitGraph, paper_graphs


@dataclass(frozen=True)
class PaperArrays:
    """Split rows plus the full (time-sorted) edge tensors with train-only-normalised features."""

    split: DaySplit
    rows: dict[str, npt.NDArray[np.int64]]
    edge_index: torch.Tensor  # [2, E]
    edge_attr: torch.Tensor  # [E, F] float32, normalised with training-row statistics
    y: torch.Tensor  # [E]
    stats: NormStats


def paper_arrays(prepared: PreparedData, cfg: GnnConfig) -> PaperArrays:
    split = paper_split(prepared.day_idx, cfg.split.fractions)
    rows = {
        "train": rows_for_days(prepared.day_idx, split.train_days),
        "val": rows_for_days(prepared.day_idx, split.val_days),
        "test": rows_for_days(prepared.day_idx, split.test_days),
    }
    feats = prepared.edge_features(ports=cfg.flags.ports, tds=cfg.flags.tds)
    stats = fit_norm(feats, rows["train"])
    return PaperArrays(
        split=split,
        rows=rows,
        edge_index=torch.from_numpy(np.vstack([prepared.src, prepared.dst])),
        edge_attr=torch.from_numpy(apply_norm(feats, stats)),
        y=torch.from_numpy(prepared.y),
        stats=stats,
    )


def split_graphs(
    prepared: PreparedData, arrays: PaperArrays, cfg: GnnConfig
) -> dict[str, SplitGraph]:
    return paper_graphs(
        prepared.num_nodes,
        arrays.edge_index,
        arrays.edge_attr,
        arrays.y,
        arrays.rows,
        reverse_mp=cfg.flags.reverse_mp,
        ports=cfg.flags.ports,
    )


def paper_inputs(
    prepared: PreparedData, cfg: GnnConfig
) -> tuple[dict[str, SplitGraph], dict[str, Any]]:
    """Graphs for train / val / test plus the facts recorded in the run's data.json."""
    arrays = paper_arrays(prepared, cfg)
    graphs = split_graphs(prepared, arrays, cfg)
    rows = arrays.rows
    data_info = {
        "meta": prepared.meta,
        "split": arrays.split.to_dict(),
        "counts": {k: int(v.shape[0]) for k, v in rows.items()},
        "laundering": {k: int(prepared.y[v].sum()) for k, v in rows.items()},
        "norm": arrays.stats.to_dict(),
    }
    return graphs, data_info
