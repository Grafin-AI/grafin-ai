from __future__ import annotations

from garda_training.errors import (
    ConfigError,
    CudaUnavailableError,
    DatasetError,
    ExportCheckError,
    GardaTrainError,
    TrainingDivergedError,
)


def test_exit_codes() -> None:
    assert GardaTrainError.exit_code == 1
    assert DatasetError.exit_code == 2
    assert ConfigError.exit_code == 3
    assert ExportCheckError.exit_code == 4
    assert CudaUnavailableError.exit_code == 5
    assert TrainingDivergedError.exit_code == 1
