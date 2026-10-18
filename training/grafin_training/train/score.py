"""Causal per-day scoring of a finished run: every validation/test transaction gets exactly one
probability from the best checkpoint, statuses use thresholds chosen on validation days."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl
import torch
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from torch_geometric.data import Data, HeteroData

from garda_training.config import GnnConfig
from garda_training.data.prepare import PreparedData
from garda_training.errors import ConfigError
from garda_training.graph.build import EDGE, REV, SplitGraph, make_graph
from garda_training.graph.loaders import make_loader
from garda_training.train.gnn import build_model, forward_edges, set_seed
from garda_training.train.paper import PaperArrays

log = logging.getLogger(__name__)
F32Array = npt.NDArray[np.float32]
APPROVED, FLAGGED, BLOCKED = "approved", "flagged", "blocked"  # platform vocabulary


def restore_model(
    train_graph: SplitGraph, cfg: GnnConfig, seed: int, ckpt: dict[str, Any]
) -> torch.nn.Module:
    """Rebuild the trained model and load its weights (CPU, eval mode).

    The architecture is rebuilt from the first training batch, re-drawn exactly as train_gnn
    drew it (same seed, loader and graph), with the checkpoint's "deg" when present. PNA's
    average degrees are also state_dict buffers in PyG 2.6, so load_state_dict restores them
    either way."""
    set_seed(seed)
    loader = make_loader(
        train_graph,
        num_neighs=cfg.train.num_neighs,
        batch_size=cfg.train.batch_size,
        shuffle=True,
        ego=cfg.flags.ego,
    )
    model = build_model(next(iter(loader)), cfg, ckpt.get("deg"))
    model.load_state_dict(ckpt["model"])
    return model.eval()


def _inject_missing_seeds(
    batch: Data | HeteroData, data: Data | HeteroData, seeds: torch.Tensor
) -> int:
    """Append to the batch every seed edge the sampler left out, so each seed gets a score.

    The batch's edge_label_index holds the local endpoints of its seeds (input_id order); the
    attribute row comes from the full graph (HeteroData: same row on the reversed edge, as
    make_graph shares attributes). Returns the number of injected edges."""
    hetero = isinstance(batch, HeteroData)
    store = batch[EDGE] if hetero else batch
    full = data[EDGE] if isinstance(data, HeteroData) else data
    gpos = seeds[store.input_id]
    missing = ~torch.isin(gpos, store.e_id)
    n = int(missing.sum())
    if n == 0:
        return 0
    pos = gpos[missing]
    local = store.edge_label_index[:, missing]
    attr = full.edge_attr[pos]
    store.edge_index = torch.cat([store.edge_index, local], dim=1)
    store.edge_attr = torch.cat([store.edge_attr, attr], dim=0)
    store.y = torch.cat([store.y, full.y[pos]], dim=0)
    store.e_id = torch.cat([store.e_id, pos], dim=0)
    if hetero:
        rev = batch[REV]
        rev.edge_index = torch.cat([rev.edge_index, local.flipud()], dim=1)
        rev.edge_attr = torch.cat([rev.edge_attr, attr], dim=0)
        if "e_id" in rev:
            rev.e_id = torch.cat([rev.e_id, pos], dim=0)
    return n


@torch.no_grad()
def score_seeds(
    model: torch.nn.Module,
    graph: SplitGraph,
    *,
    num_neighs: tuple[int, ...],
    batch_size: int,
    ego: bool,
    device: torch.device,
    inject: bool = True,
) -> tuple[F32Array, int]:
    """(P(laundering) per seed edge in graph.seeds order, number of injected seeds).

    With inject=False, seeds not sampled into their own batch are NaN (upstream semantics)."""
    model.eval()
    loader = make_loader(
        graph, num_neighs=num_neighs, batch_size=batch_size, shuffle=False, ego=ego
    )
    out = np.full(graph.seeds.shape[0], np.nan, dtype=np.float32)
    injected = 0
    for batch in loader:
        if inject:
            injected += _inject_missing_seeds(batch, graph.data, graph.seeds)
        store = batch[EDGE] if isinstance(batch, HeteroData) else batch
        input_id = store.input_id.clone()
        gpos = graph.seeds[input_id]
        e_id = store.e_id
        order = torch.argsort(e_id)
        idx = torch.searchsorted(e_id[order], gpos).clamp(max=e_id.shape[0] - 1)
        hit = e_id[order][idx] == gpos
        logits, _ = forward_edges(model, batch.to(device))
        prob = torch.softmax(logits.float(), dim=-1)[:, 1].cpu()
        out[input_id[hit].numpy()] = prob[order[idx[hit]]].numpy()
    return out, injected


@dataclass(frozen=True)
class DayScores:
    rows: npt.NDArray[np.int64]  # global (time-sorted) positions of the day's edges
    prob: F32Array
    injected: int
    seconds: float


def causal_day_scores(
    model: torch.nn.Module,
    prepared: PreparedData,
    arrays: PaperArrays,
    cfg: GnnConfig,
    days: list[int],
    *,
    batch_size: int,
    device: torch.device,
    seed: int,
) -> dict[int, DayScores]:
    """Score each day d on the graph of all edges with day_idx <= d (a prefix of the sorted
    rows). Labels never enter the graph (zeros), and sampling is re-seeded per day so a day's
    scores depend only on edges up to that day."""
    day_idx = prepared.day_idx
    if np.any(np.diff(day_idx) < 0):
        raise ConfigError("prepared rows are not sorted by time")
    out: dict[int, DayScores] = {}
    for d in days:
        start = time.perf_counter()
        lo = int(np.searchsorted(day_idx, d, side="left"))
        hi = int(np.searchsorted(day_idx, d, side="right"))
        data = make_graph(
            prepared.num_nodes,
            arrays.edge_index[:, :hi],
            arrays.edge_attr[:hi],
            torch.zeros(hi, dtype=torch.long),
            reverse_mp=cfg.flags.reverse_mp,
            ports=cfg.flags.ports,
        )
        graph = SplitGraph(data, torch.arange(lo, hi, dtype=torch.long))
        torch.manual_seed(seed + d)
        prob, injected = score_seeds(
            model,
            graph,
            num_neighs=cfg.train.num_neighs,
            batch_size=batch_size,
            ego=cfg.flags.ego,
            device=device,
        )
        if np.isnan(prob).any():
            raise RuntimeError(f"day {d}: some seed edges were not scored")
        out[d] = DayScores(np.arange(lo, hi), prob, injected, time.perf_counter() - start)
        log.info(
            "score: day %d  %d edges (%d injected)  %.1fs", d, hi - lo, injected, out[d].seconds
        )
    return out


@dataclass(frozen=True)
class Thresholds:
    blocked: float
    flagged: float
    flag_recall_target: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "flagged": self.flagged,
            "flag_recall_target": self.flag_recall_target,
            "selected_on": "val",
        }


def choose_thresholds(
    y: npt.NDArray[Any], prob: npt.NDArray[Any], flag_recall: float = 0.9
) -> Thresholds:
    """blocked = threshold maximising F1; flagged = largest threshold with recall >= target,
    capped at blocked. A row is positive when prob >= threshold."""
    if not 0 < flag_recall <= 1:
        raise ConfigError(f"--flag-recall must be in (0, 1], got {flag_recall}")
    y = np.asarray(y)
    if y.size == 0:
        raise ConfigError("no validation rows to choose thresholds on")
    if int(y.sum()) == 0:
        raise ConfigError("validation days contain no laundering rows: cannot choose thresholds")
    precision, recall, thresholds = precision_recall_curve(y, np.asarray(prob, dtype=np.float64))
    p, r = precision[:-1], recall[:-1]
    f1 = np.divide(2 * p * r, p + r, out=np.zeros_like(p), where=(p + r) > 0)
    blocked = float(thresholds[int(np.argmax(f1))])
    flagged = float(thresholds[r >= flag_recall].max())
    return Thresholds(blocked, min(flagged, blocked), flag_recall)


def statuses(prob: npt.NDArray[Any], th: Thresholds) -> npt.NDArray[np.str_]:
    return np.where(
        prob >= th.blocked, BLOCKED, np.where(prob >= th.flagged, FLAGGED, APPROVED)
    ).astype(np.str_)


def split_metrics(
    y: npt.NDArray[Any], prob: npt.NDArray[Any], status: npt.NDArray[Any], th: Thresholds
) -> dict[str, Any]:
    pos = int(y.sum())
    both = 0 < pos < y.size
    pred = prob >= th.blocked
    tp = int((pred & (y == 1)).sum())
    precision = tp / int(pred.sum()) if pred.any() else 0.0
    recall = tp / pos if pos else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    flag_tp = int(((prob >= th.flagged) & (y == 1)).sum())
    return {
        "n": int(y.size),
        "positives": pos,
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "recall_at_flagged": flag_tp / pos if pos else None,
        "pr_auc": float(average_precision_score(y, prob)) if both else None,
        "roc_auc": float(roc_auc_score(y, prob)) if both else None,
        "status_counts": {s: int((status == s).sum()) for s in (APPROVED, FLAGGED, BLOCKED)},
    }


def score_outputs(
    prepared: PreparedData,
    arrays: PaperArrays,
    day_scores: dict[int, DayScores],
    flag_recall: float,
) -> tuple[pl.DataFrame, Thresholds, dict[str, Any]]:
    """The served table, the thresholds (validation days only) and the metrics."""
    val_days, test_days = set(arrays.split.val_days), set(arrays.split.test_days)
    days = sorted(day_scores)
    if not set(days) <= val_days | test_days:
        raise ConfigError("scoring is only defined for validation and test days")
    rows = np.concatenate([day_scores[d].rows for d in days])
    prob = np.concatenate([day_scores[d].prob for d in days]).astype(np.float32)
    day = prepared.day_idx[rows]
    split = np.where(np.isin(day, list(val_days)), "val", "test")
    y = prepared.y[rows]  # labels: evaluation and threshold selection only
    is_val = split == "val"
    th = choose_thresholds(y[is_val], prob[is_val], flag_recall)
    status = statuses(prob, th)
    frame = pl.DataFrame(
        {
            "transaction_id": (prepared.row[rows] + 1).astype(np.int64),
            "day": day.astype(np.int64),
            "split": split,
            "ts": prepared.ts[rows].astype(np.int64),
            "prob": prob,
            "status": status,
            "is_laundering": y.astype(np.int8),
        }
    )
    metrics: dict[str, Any] = {
        name: split_metrics(y[mask], prob[mask], status[mask], th)
        for name, mask in (("val", is_val), ("test", ~is_val))
    }
    metrics["thresholds"] = th.to_dict()
    metrics["per_day"] = [
        {
            "day": d,
            "split": "val" if d in val_days else "test",
            "n": int(day_scores[d].rows.size),
            "positives": int(prepared.y[day_scores[d].rows].sum()),
            "injected": day_scores[d].injected,
            "seconds": day_scores[d].seconds,
        }
        for d in days
    ]
    total = sum(r["n"] for r in metrics["per_day"])
    metrics["injected_fraction"] = (
        sum(r["injected"] for r in metrics["per_day"]) / total if total else 0.0
    )
    return frame, th, metrics
