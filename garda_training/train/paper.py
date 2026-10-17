"""Paper protocol inputs: upstream day split, train-only normalisation, three split graphs."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from garda_training.config import GnnConfig
from garda_training.data.features import apply_norm, fit_norm
from garda_training.data.prepare import PreparedData
from garda_training.data.split import paper_split, rows_for_days
from garda_training.graph.build import SplitGraph, paper_graphs


def paper_inputs(
    prepared: PreparedData, cfg: GnnConfig
) -> tuple[dict[str, SplitGraph], dict[str, Any]]:
    """Graphs for train / val / test plus the facts recorded in the run's data.json."""
    split = paper_split(prepared.day_idx, cfg.split.fractions)
    rows = {
        "train": rows_for_days(prepared.day_idx, split.train_days),
        "val": rows_for_days(prepared.day_idx, split.val_days),
        "test": rows_for_days(prepared.day_idx, split.test_days),
    }
    feats = prepared.edge_features(ports=cfg.flags.ports, tds=cfg.flags.tds)
    stats = fit_norm(feats, rows["train"])
    graphs = paper_graphs(
        prepared.num_nodes,
        torch.from_numpy(np.vstack([prepared.src, prepared.dst])),
        torch.from_numpy(apply_norm(feats, stats)),
        torch.from_numpy(prepared.y),
        rows,
        reverse_mp=cfg.flags.reverse_mp,
        ports=cfg.flags.ports,
    )
    data_info = {
        "meta": prepared.meta,
        "split": split.to_dict(),
        "counts": {k: int(v.shape[0]) for k, v in rows.items()},
        "laundering": {k: int(prepared.y[v].sum()) for k, v in rows.items()},
        "norm": stats.to_dict(),
    }
    return graphs, data_info
