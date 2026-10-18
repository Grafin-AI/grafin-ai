"""Device resolution. `auto` never picks MPS: PyG scatter ops are not reliable there."""

from __future__ import annotations

import torch

from garda_training.errors import ConfigError, CudaUnavailableError

DEVICE_CHOICES = ("auto", "cpu", "mps", "cuda")


def resolve_device(name: str) -> torch.device:
    if name not in DEVICE_CHOICES:
        raise ConfigError(f"unknown device {name!r}; choose one of {DEVICE_CHOICES}")
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name == "cuda":
        if not torch.cuda.is_available():
            raise CudaUnavailableError("--device cuda requested but CUDA is not available")
        return torch.device("cuda")
    if name == "mps":
        if not torch.backends.mps.is_available():
            raise ConfigError("--device mps requested but MPS is not available")
        return torch.device("mps")
    return torch.device("cpu")
