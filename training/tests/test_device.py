from __future__ import annotations

import pytest
import torch

from grafin_training.device import resolve_device
from grafin_training.errors import ConfigError, CudaUnavailableError


def test_resolve_device_cpu_and_unknown() -> None:
    assert resolve_device("cpu") == torch.device("cpu")
    with pytest.raises(ConfigError):
        resolve_device("tpu")


@pytest.mark.skipif(torch.cuda.is_available(), reason="needs a machine without CUDA")
def test_cuda_requested_without_cuda() -> None:
    with pytest.raises(CudaUnavailableError):
        resolve_device("cuda")
    assert resolve_device("auto") == torch.device("cpu")
