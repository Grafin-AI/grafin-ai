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

from garda_training.errors import ConfigError

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MLFLOW_URI = f"sqlite:///{REPO_ROOT / 'mlruns' / 'mlflow.db'}"
EXPERIMENT = "garda-training"


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
