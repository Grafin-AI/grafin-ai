"""Exit-code taxonomy (spec §10). Every user-facing failure raises a subclass."""

from __future__ import annotations


class GrafinTrainError(Exception):
    """Base class; exit code 1 (unexpected / training failure)."""

    exit_code = 1


class DatasetError(GrafinTrainError):
    """Dataset missing or unreadable, or its sha256 does not match the manifest."""

    exit_code = 2


class ConfigError(GrafinTrainError):
    """Invalid configuration or CLI arguments."""

    exit_code = 3


class ExportCheckError(GrafinTrainError):
    """A model-bundle self-check failed (Plan B)."""

    exit_code = 4


class CudaUnavailableError(GrafinTrainError):
    """--device cuda was requested but CUDA is not available."""

    exit_code = 5


class TrainingDivergedError(GrafinTrainError):
    """The training loss became NaN or infinite; the last good checkpoint is kept."""

    exit_code = 1
