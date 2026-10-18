"""GNN training loop (port of upstream training.py / train_util.py) with best-val checkpointing,
resume, CPU-tensor checkpoints and a NaN guard."""

from __future__ import annotations

import logging
import os
import random
import resource
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from sklearn.metrics import f1_score
from torch.amp.grad_scaler import GradScaler
from torch_geometric.data import Data, HeteroData
from torch_geometric.nn import to_hetero
from torch_geometric.utils import degree

from grafin_training.config import GnnConfig
from grafin_training.errors import TrainingDivergedError
from grafin_training.graph.build import EDGE, REV, SplitGraph
from grafin_training.graph.loaders import make_loader, seed_mask
from grafin_training.models.multignn import PNA
from grafin_training.tracking import RunDir, Tracker

log = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    """Upstream util.set_seed."""
    np.random.seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ["PYTHONHASHSEED"] = str(seed)


def degree_histogram(sample_batch: Data | HeteroData) -> torch.Tensor:
    """Upstream training.get_model: in-degree histogram of the first training batch (PNA `deg`).
    Checkpoints store it under "deg"; PyG 2.6 also keeps the derived averages as buffers."""
    if isinstance(sample_batch, HeteroData):
        index = torch.cat((sample_batch[EDGE].edge_index[1], sample_batch[REV].edge_index[1]), 0)
    else:
        index = sample_batch.edge_index[1]
    return torch.bincount(degree(index, dtype=torch.long), minlength=1)


def build_model(
    sample_batch: Data | HeteroData, cfg: GnnConfig, deg: torch.Tensor | None = None
) -> torch.nn.Module:
    """Upstream training.get_model for PNA. `deg` defaults to the sample batch's histogram."""
    hetero = isinstance(sample_batch, HeteroData)
    n_feats = (sample_batch["node"].x if hetero else sample_batch.x).shape[1]
    e_dim = (sample_batch[EDGE].edge_attr if hetero else sample_batch.edge_attr).shape[1]
    if deg is None:
        deg = degree_histogram(sample_batch)
    model: torch.nn.Module = PNA(
        num_features=n_feats,
        num_gnn_layers=cfg.model.n_gnn_layers,
        n_classes=2,
        n_hidden=round(cfg.model.n_hidden),
        edge_updates=cfg.model.edge_updates,
        edge_dim=e_dim,
        dropout=cfg.model.dropout,
        deg=deg,
        final_dropout=cfg.model.final_dropout,
    )
    if hetero:
        model = to_hetero(model, sample_batch.metadata(), aggr="mean")
    return model


def forward_edges(
    model: torch.nn.Module, batch: Data | HeteroData
) -> tuple[torch.Tensor, torch.Tensor]:
    """(logits, labels) for the batch's forward edges."""
    if isinstance(batch, HeteroData):
        out = model(batch.x_dict, batch.edge_index_dict, batch.edge_attr_dict)[EDGE]
        return out, batch[EDGE].y
    return model(batch.x, batch.edge_index, batch.edge_attr), batch.y


@dataclass
class Scores:
    prob: npt.NDArray[np.float32]
    y: npt.NDArray[np.int64]
    coverage: float

    @property
    def f1(self) -> float:
        return float(f1_score(self.y, self.prob > 0.5, zero_division=0))


@torch.no_grad()
def predict(
    model: torch.nn.Module,
    graph: SplitGraph,
    cfg: GnnConfig,
    device: torch.device,
    max_batches: int | None = None,
) -> Scores:
    """P(laundering) for the seed edges that were sampled (paper protocol)."""
    model.eval()
    loader = make_loader(
        graph,
        num_neighs=cfg.train.num_neighs,
        batch_size=cfg.train.batch_size,
        shuffle=False,
        ego=cfg.flags.ego,
    )
    probs: list[torch.Tensor] = []
    ys: list[torch.Tensor] = []
    seen = total = 0
    for k, batch in enumerate(loader):
        if max_batches is not None and k >= max_batches:
            break
        mask, n_seeds = seed_mask(batch, graph.seeds)
        total += n_seeds
        seen += int(mask.sum())
        logits, y = forward_edges(model, batch.to(device))
        mask = mask.to(device)
        probs.append(torch.softmax(logits[mask].float(), dim=-1)[:, 1].cpu())
        ys.append(y[mask].cpu())
    prob = torch.cat(probs).numpy().astype(np.float32) if probs else np.zeros(0, np.float32)
    y_all = torch.cat(ys).numpy().astype(np.int64) if ys else np.zeros(0, np.int64)
    return Scores(prob, y_all, seen / total if total else 0.0)


@dataclass
class EpochRecord:
    epoch: int
    loss: float
    train_f1: float
    val_f1: float
    test_f1: float | None  # scored only when validation F1 improves (the reported number)
    val_coverage: float
    test_coverage: float | None
    seconds: float


@dataclass
class TrainState:
    next_epoch: int = 0
    best_epoch: int = -1
    best_val_f1: float = -1.0
    history: list[EpochRecord] = field(default_factory=list)


@dataclass(frozen=True)
class TrainResult:
    best_epoch: int
    best_val_f1: float
    test_f1_at_best: float
    history: list[EpochRecord]
    peak_gpu_mem_mb: float | None
    peak_host_rss_mb: float
    stop_reason: str  # "epochs" | "patience" | "time_budget"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["history"] = [asdict(r) for r in self.history]
        return out


def _to_cpu(obj: Any) -> Any:
    if isinstance(obj, torch.Tensor):
        return obj.detach().cpu()
    if isinstance(obj, dict):
        return {k: _to_cpu(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_cpu(v) for v in obj]
    return obj


def _rng_state() -> dict[str, Any]:
    return {
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        "numpy": np.random.get_state(),
        "python": random.getstate(),
    }


def _restore_rng(state: dict[str, Any]) -> None:
    torch.set_rng_state(state["torch"])
    if state["cuda"] is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["cuda"])
    np.random.set_state(state["numpy"])
    random.setstate(state["python"])


def peak_host_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / 2**20 if sys.platform == "darwin" else rss / 2**10  # bytes on macOS, KiB on Linux


def save_checkpoint(path: Any, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    torch.save(_to_cpu(payload), tmp)
    os.replace(tmp, path)


def load_checkpoint(path: Any) -> dict[str, Any]:
    ckpt: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=False)
    return ckpt


def train_gnn(
    graphs: dict[str, SplitGraph],
    cfg: GnnConfig,
    device: torch.device,
    run: RunDir,
    tracker: Tracker,
    *,
    resume: bool = False,
    max_batches: int | None = None,
) -> TrainResult:
    """Train on graphs['train'], select the epoch by graphs['val'] F1, report graphs['test'] F1.
    Call set_seed() first: the sample batch and all shuffles/sampling draw from the torch RNG."""
    tr_loader = make_loader(
        graphs["train"],
        num_neighs=cfg.train.num_neighs,
        batch_size=cfg.train.batch_size,
        shuffle=True,
        ego=cfg.flags.ego,
    )
    sample = next(iter(tr_loader))
    deg = degree_histogram(sample)
    model = build_model(sample, cfg, deg).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.train.lr)
    use_amp = cfg.train.amp and device.type == "cuda"
    scaler = GradScaler("cuda", enabled=use_amp)
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor([cfg.train.w_ce1, cfg.train.w_ce2], dtype=torch.float32).to(device)
    )
    state = TrainState()
    last_path = run.checkpoints / "last.pt"
    best_path = run.checkpoints / "best.pt"
    if resume:
        ckpt = load_checkpoint(last_path)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scaler.load_state_dict(ckpt["scaler"])
        state = TrainState(
            next_epoch=ckpt["epoch"] + 1,
            best_epoch=ckpt["best_epoch"],
            best_val_f1=ckpt["best_val_f1"],
            history=[EpochRecord(**r) for r in ckpt["history"]],
        )
        _restore_rng(ckpt["rng"])
        log.info("resumed at epoch %d", state.next_epoch)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    started = time.perf_counter()
    stop_reason = "epochs"
    for epoch in range(state.next_epoch, cfg.train.epochs):
        start = time.perf_counter()
        model.train()
        total_loss = 0.0
        n_examples = 0
        preds: list[torch.Tensor] = []
        truths: list[torch.Tensor] = []
        for k, batch in enumerate(tr_loader):
            if max_batches is not None and k >= max_batches:
                break
            mask, _ = seed_mask(batch, graphs["train"].seeds)
            if not bool(mask.any()):
                continue
            optimizer.zero_grad()
            batch = batch.to(device)
            mask = mask.to(device)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits, y = forward_edges(model, batch)
                pred = logits[mask]
                truth = y[mask]
                loss = loss_fn(pred.float(), truth)
            if not torch.isfinite(loss):
                raise TrainingDivergedError(
                    f"non-finite loss at epoch {epoch} batch {k}; last good checkpoint: {last_path}"
                )
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += float(loss) * pred.shape[0]
            n_examples += pred.shape[0]
            preds.append(pred.argmax(dim=-1).cpu())
            truths.append(truth.cpu())
        train_f1 = float(f1_score(torch.cat(truths), torch.cat(preds), zero_division=0))
        val = predict(model, graphs["val"], cfg, device, max_batches)
        improved = val.f1 > state.best_val_f1
        test = predict(model, graphs["test"], cfg, device, max_batches) if improved else None
        record = EpochRecord(
            epoch=epoch,
            loss=total_loss / max(n_examples, 1),
            train_f1=train_f1,
            val_f1=val.f1,
            test_f1=test.f1 if test else None,
            val_coverage=val.coverage,
            test_coverage=test.coverage if test else None,
            seconds=time.perf_counter() - start,
        )
        state.history.append(record)
        log.info(
            "epoch %d loss %.4f train_f1 %.4f val_f1 %.4f test_f1 %s (%.0fs)",
            epoch,
            record.loss,
            train_f1,
            val.f1,
            f"{test.f1:.4f}" if test else "-",
            record.seconds,
        )
        metrics = {"loss": record.loss, "f1_train": train_f1, "f1_val": val.f1}
        if test:
            metrics["f1_test"] = test.f1
        tracker.log_metrics(metrics, step=epoch)
        if improved:
            state.best_epoch, state.best_val_f1 = epoch, val.f1
            save_checkpoint(
                best_path,
                {"model": model.state_dict(), "epoch": epoch, "val_f1": val.f1, "deg": deg},
            )
        save_checkpoint(
            last_path,
            {
                "model": model.state_dict(),
                "deg": deg,
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "epoch": epoch,
                "best_epoch": state.best_epoch,
                "best_val_f1": state.best_val_f1,
                "history": [asdict(r) for r in state.history],
                "rng": _rng_state(),
            },
        )
        if cfg.train.patience and epoch - state.best_epoch >= cfg.train.patience:
            stop_reason = "patience"
            log.info("early stop: no validation improvement for %d epochs", cfg.train.patience)
            break
        elapsed = time.perf_counter() - started
        if cfg.train.max_hours and elapsed + record.seconds > cfg.train.max_hours * 3600:
            stop_reason = "time_budget"
            log.info("stopping: next epoch would exceed the %.2f h budget", cfg.train.max_hours)
            break

    best = next((r for r in state.history if r.epoch == state.best_epoch), None)
    peak = torch.cuda.max_memory_allocated(device) / 2**20 if device.type == "cuda" else None
    return TrainResult(
        best_epoch=state.best_epoch,
        best_val_f1=state.best_val_f1,
        test_f1_at_best=best.test_f1 if best and best.test_f1 is not None else float("nan"),
        history=state.history,
        peak_gpu_mem_mb=peak,
        peak_host_rss_mb=peak_host_rss_mb(),
        stop_reason=stop_reason,
    )
