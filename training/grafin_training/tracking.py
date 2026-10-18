"""Run directories (source of truth) and failure-tolerant MLflow logging."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
import torch_geometric

from grafin_training.errors import ConfigError

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MLFLOW_URI = f"sqlite:///{REPO_ROOT / 'mlruns' / 'mlflow.db'}"
EXPERIMENT = "grafin-training"


def make_run_id(dataset: str, protocol: str, seed: int, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{dataset}-{protocol}-s{seed}"


class RunDir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.checkpoints = path / "checkpoints"

    @classmethod
    def create(cls, root: Path, run_id: str) -> RunDir:
        path = root / run_id
        if path.exists():
            raise ConfigError(f"run directory already exists: {path}")
        (path / "checkpoints").mkdir(parents=True)
        return cls(path)

    @classmethod
    def open(cls, root: Path, run_id: str) -> RunDir:
        path = root / run_id
        if not (path / "config.json").is_file():
            raise ConfigError(f"no run to resume at {path}")
        return cls(path)

    def write_json(self, name: str, obj: Any) -> None:
        tmp = self.path / f".{name}.tmp"
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
        os.replace(tmp, self.path / name)

    def read_json(self, name: str) -> Any:
        return json.loads((self.path / name).read_text())


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def environment_info(device: torch.device) -> dict[str, Any]:
    return {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": _git("status", "--porcelain") not in ("", "unknown"),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_geometric": torch_geometric.__version__,
        "cuda": torch.version.cuda,
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "host": platform.node(),
    }


def flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in obj.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = value
    return out


class Tracker:
    """MLflow logging that never fails a run: any MLflow error is logged once and disables it."""

    def __init__(
        self, uri: str | None, run_name: str, params: dict[str, Any], tags: dict[str, str]
    ):
        self._mlflow: Any = None
        if uri is None:
            return
        try:
            import mlflow

            if uri.startswith("sqlite:///"):
                Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            mlflow.set_tracking_uri(uri)
            experiment = mlflow.get_experiment_by_name(EXPERIMENT)
            if experiment is None:
                artifacts = Path(uri.removeprefix("sqlite:///")).parent / "artifacts"
                experiment_id = mlflow.create_experiment(
                    EXPERIMENT, artifact_location=artifacts.as_uri()
                )
            else:
                experiment_id = experiment.experiment_id
            mlflow.start_run(run_name=run_name, experiment_id=experiment_id, tags=tags)
            mlflow.log_params({k: str(v)[:500] for k, v in flatten(params).items()})
            self._mlflow = mlflow
        except Exception as exc:  # noqa: BLE001 - tracking must never fail training
            log.warning("MLflow disabled: %s", exc)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception as exc:  # noqa: BLE001
            log.warning("MLflow disabled: %s", exc)
            self._mlflow = None

    def finish(self, status: str) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.end_run(status=status)
        except Exception as exc:  # noqa: BLE001
            log.warning("MLflow end_run failed: %s", exc)
        self._mlflow = None


# --- post-hoc logging of a finished run directory -------------------------------------------

RUN_EXPERIMENT = "grafin-ai-multignn"
MODEL_NAME = "Multi-GNN PNA"
_EPOCH_KEYS = ("loss", "train_f1", "val_f1", "test_f1", "val_coverage", "test_coverage", "seconds")
_SPLIT_KEYS = (
    "f1",
    "pr_auc",
    "roc_auc",
    "precision",
    "recall",
    "recall_at_flagged",
    "n",
    "positives",
)
# what gets uploaded as artifacts: small JSON only, never scores.csv/parquet or checkpoints
_ARTIFACTS = ("config.json", "data.json", "env.json", "metrics.json")
_SCORE_ARTIFACTS = ("score_metrics.json", "thresholds.json", "export_meta.json")


def default_tracking_uri() -> str:
    """MLFLOW_TRACKING_URI if set, else the repo's SQLite store (mlruns/mlflow.db)."""
    return os.environ.get("MLFLOW_TRACKING_URI") or DEFAULT_MLFLOW_URI


def _metric_key(name: str) -> str:
    """MLflow metric names allow [A-Za-z0-9_-. /]; typology names carry parentheses."""
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name)
    return "_".join(part for part in slug.split("_") if part)


def _read(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path.is_file() else None


def _numeric(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _experiment_id(mlflow: Any, uri: str, name: str) -> str:
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is not None:
        return str(experiment.experiment_id)
    location = None
    if uri.startswith("sqlite:///"):
        location = (Path(uri.removeprefix("sqlite:///")).parent / "artifacts").as_uri()
    return str(mlflow.create_experiment(name, artifact_location=location))


def log_run_to_mlflow(
    run_dir: Path | str, tracking_uri: str | None = None, experiment: str = RUN_EXPERIMENT
) -> str:
    """Mirror a finished `runs/<run-id>/` into MLflow; returns the MLflow run id.

    Idempotent per run name: an earlier MLflow run with the same name in the experiment is
    deleted first, so re-logging replaces it instead of duplicating metric history.
    """
    import mlflow

    run_dir = Path(run_dir)
    config = _read(run_dir / "config.json")
    if config is None:
        raise ConfigError(f"no run at {run_dir} (config.json missing)")
    run_name = run_dir.name
    metrics_json = _read(run_dir / "metrics.json") or {}
    data_json = _read(run_dir / "data.json") or {}
    env_json = _read(run_dir / "env.json") or {}
    scores = run_dir / "scores"
    score_metrics = _read(scores / "score_metrics.json") or {}
    thresholds = _read(scores / "thresholds.json") or score_metrics.get("thresholds") or {}
    export_meta = _read(scores / "export_meta.json") or {}

    uri = tracking_uri or default_tracking_uri()
    if uri.startswith("sqlite:///"):
        Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(uri)
    experiment_id = _experiment_id(mlflow, uri, experiment)
    client = mlflow.MlflowClient()
    for old in client.search_runs(
        [experiment_id], filter_string=f"attributes.run_name = '{run_name}'"
    ):
        client.delete_run(old.info.run_id)

    meta = data_json.get("meta", {})
    dataset = meta.get("dataset") or Path(str(config.get("data", {}).get("path", "?"))).stem
    source = config.get("data", {}).get("source", "?")
    trained_sha = env_json.get("git_sha", "unknown")
    tags = {
        "dataset": f"{dataset} ({source})",
        "model": MODEL_NAME,
        "run_id": run_name,
        "git_commit": trained_sha if trained_sha != "unknown" else _git("rev-parse", "HEAD"),
        "logged_from_commit": _git("rev-parse", "HEAD"),
        "stop_reason": str(metrics_json.get("stop_reason", "")),
        **{f"env.{k}": str(v) for k, v in env_json.items()},
    }

    params: dict[str, Any] = flatten(config)
    params.update(flatten({"counts": data_json.get("counts", {})}, "data."))
    params.update(flatten({"laundering": data_json.get("laundering", {})}, "data."))
    for key in ("n_nodes", "n_edges", "n_days", "laundering"):
        if key in meta:
            params[f"data.meta.{key}"] = meta[key]
    params.update(flatten(thresholds, "threshold."))

    final: dict[str, float] = {}
    for key in (
        "best_epoch",
        "best_val_f1",
        "test_f1_at_best",
        "peak_gpu_mem_mb",
        "peak_host_rss_mb",
    ):
        if _numeric(metrics_json.get(key)):
            final[key] = float(metrics_json[key])
    for split in ("val", "test"):
        block = score_metrics.get(split, {})
        for key in _SPLIT_KEYS:
            if _numeric(block.get(key)):
                final[f"final_{split}_{key}"] = float(block[key])
        for status, count in block.get("status_counts", {}).items():
            final[f"final_{split}_status_{status}"] = float(count)
    for key, value in thresholds.items():
        if _numeric(value):
            final[f"threshold_{key}"] = float(value)
    for name, count in export_meta.get("typology_counts", {}).items():
        final[f"typology_{_metric_key(name)}"] = float(count)
    for status, count in export_meta.get("status_counts", {}).items():
        final[f"export_status_{status}"] = float(count)
    if _numeric(export_meta.get("n_rows")):
        final["export_n_rows"] = float(export_meta["n_rows"])

    with mlflow.start_run(run_name=run_name, experiment_id=experiment_id, tags=tags) as active:
        mlflow.log_params({k: str(v)[:500] for k, v in params.items()})
        for row in metrics_json.get("history", []):
            epoch_metrics = {k: float(row[k]) for k in _EPOCH_KEYS if _numeric(row.get(k))}
            if epoch_metrics:
                mlflow.log_metrics(epoch_metrics, step=int(row["epoch"]))
        if final:
            mlflow.log_metrics(final)
        if export_meta.get("typology_counts"):
            mlflow.log_dict(export_meta["typology_counts"], "typology_counts.json")
        for name in _ARTIFACTS:
            if (run_dir / name).is_file():
                mlflow.log_artifact(str(run_dir / name))
        for name in _SCORE_ARTIFACTS:
            if (scores / name).is_file():
                mlflow.log_artifact(str(scores / name), artifact_path="scores")
        return str(active.info.run_id)
