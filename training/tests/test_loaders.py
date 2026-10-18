from __future__ import annotations

import numpy as np
import torch

from grafin_training.graph.build import EDGE, paper_graphs
from grafin_training.graph.loaders import AddEgoIds, make_loader, seed_mask


def test_loader_ego_ids_and_seed_mask() -> None:
    torch.manual_seed(0)
    e = 40
    ei = torch.randint(0, 12, (2, e))
    rows = {"train": np.arange(0, 30), "val": np.arange(30, 35), "test": np.arange(35, 40)}
    graphs = paper_graphs(
        12,
        ei,
        torch.randn(e, 6),
        torch.zeros(e, dtype=torch.long),
        rows,
        reverse_mp=True,
        ports=True,
    )
    loader = make_loader(graphs["val"], num_neighs=(50, 50), batch_size=5, shuffle=False, ego=True)
    batch = next(iter(loader))
    assert batch["node"].x.shape[1] == 2  # placeholder + ego column
    ego_nodes = torch.unique(batch[EDGE].edge_label_index.view(-1))
    assert torch.all(batch["node"].x[ego_nodes, 1] == 1)
    mask, n_seeds = seed_mask(batch, graphs["val"].seeds)
    assert n_seeds == 5
    assert set(batch[EDGE].e_id[mask].tolist()) <= set(graphs["val"].seeds.tolist())
    assert int(mask.sum()) == 5  # with generous fan-out every seed edge is sampled


def test_add_ego_ids_homogeneous() -> None:
    from torch_geometric.data import Data

    data = Data(x=torch.zeros(4, 1), edge_label_index=torch.tensor([[0], [2]]))
    out = AddEgoIds()(data)
    assert out.x[:, 1].tolist() == [1.0, 0.0, 1.0, 0.0]
