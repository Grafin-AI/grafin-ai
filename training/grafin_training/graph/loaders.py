"""Link-neighbour loaders, ego IDs and seed-edge masks (port of upstream train_util.py)."""

from __future__ import annotations

from typing import Any

import torch
from torch_geometric.data import Data, HeteroData
from torch_geometric.loader import LinkNeighborLoader
from torch_geometric.transforms import BaseTransform

from grafin_training.graph.build import EDGE, SplitGraph


class AddEgoIds(BaseTransform):  # type: ignore[misc]
    """Append a 0/1 column to node features marking the endpoints of the batch's seed edges."""

    def forward(self, data: Any) -> Any:
        hetero = isinstance(data, HeteroData)
        x = data["node"].x if hetero else data.x
        label_index = data[EDGE].edge_label_index if hetero else data.edge_label_index
        ids = torch.zeros((x.shape[0], 1), device=x.device)
        ids[torch.unique(label_index.view(-1)).to(x.device)] = 1
        if hetero:
            data["node"].x = torch.cat([x, ids], dim=1)
        else:
            data.x = torch.cat([x, ids], dim=1)
        return data


def make_loader(
    graph: SplitGraph, *, num_neighs: tuple[int, ...], batch_size: int, shuffle: bool, ego: bool
) -> LinkNeighborLoader:
    data = graph.data
    transform = AddEgoIds() if ego else None
    if isinstance(data, HeteroData):
        return LinkNeighborLoader(
            data,
            num_neighbors=list(num_neighs),
            edge_label_index=(EDGE, data[EDGE].edge_index[:, graph.seeds]),
            edge_label=data[EDGE].y[graph.seeds],
            batch_size=batch_size,
            shuffle=shuffle,
            transform=transform,
        )
    return LinkNeighborLoader(
        data,
        num_neighbors=list(num_neighs),
        edge_label_index=data.edge_index[:, graph.seeds],
        edge_label=data.y[graph.seeds],
        batch_size=batch_size,
        shuffle=shuffle,
        transform=transform,
    )


def seed_mask(batch: Data | HeteroData, seeds: torch.Tensor) -> tuple[torch.Tensor, int]:
    """(mask over the batch's sampled forward edges selecting its seed edges, number of seeds).

    Upstream semantics: a seed edge that was not sampled into its own batch is skipped."""
    store = batch[EDGE] if isinstance(batch, HeteroData) else batch
    batch_seeds = seeds[store.input_id.cpu()]
    return torch.isin(store.e_id.cpu(), batch_seeds), int(batch_seeds.numel())
