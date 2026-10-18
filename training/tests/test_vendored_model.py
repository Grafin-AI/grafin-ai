from __future__ import annotations

import hashlib
from pathlib import Path

import torch

from grafin_training.models.multignn import PNA

UPSTREAM_SHA256 = "00ef7142e81d3080114142106867e6ef3002d5a01ff5474e9f75cab957fcefe7"
VENDORED = Path(__file__).resolve().parents[1] / "grafin_training" / "models" / "multignn.py"


def test_vendored_models_file_is_byte_identical_to_upstream() -> None:
    assert hashlib.sha256(VENDORED.read_bytes()).hexdigest() == UPSTREAM_SHA256


def test_pna_forward_shape() -> None:
    torch.manual_seed(0)
    edge_index = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 0]])
    model = PNA(
        num_features=2,
        num_gnn_layers=2,
        n_hidden=20,
        edge_updates=True,
        edge_dim=6,
        deg=torch.tensor([0, 4]),
        final_dropout=0.0,
    )
    out = model(torch.zeros(4, 2), edge_index, torch.randn(4, 6))
    assert out.shape == (4, 2)
