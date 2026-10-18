from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import torch
from torch_geometric.data import HeteroData

from grafin_training.graph.build import (
    EDGE,
    REV,
    _ports,
    make_graph,
    paper_graphs,
    port_columns,
    time_delta_columns,
)
from tests import upstream_ref


def _random_graph(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    rng = np.random.default_rng(seed)
    n, e = int(rng.integers(5, 40)), int(rng.integers(20, 300))
    src, dst = rng.integers(0, n, e), rng.integers(0, n, e)
    ts = rng.permutation(e * 3)[:e].astype(np.int64)  # unique timestamps
    return src.astype(np.int64), dst.astype(np.int64), ts, n


def _upstream(src: np.ndarray, dst: np.ndarray, ts: np.ndarray, n: int) -> np.ndarray:
    ei = torch.tensor(np.vstack([src, dst]))
    data = SimpleNamespace(
        num_nodes=n, edge_index=ei, timestamps=torch.tensor(ts, dtype=torch.float32)
    )
    a_in, a_out = upstream_ref.to_adj_nodes_with_times(data)
    e_in, e_out = upstream_ref.to_adj_edges_with_times(data)
    return np.hstack(
        [
            upstream_ref.ports(ei, a_in).numpy(),
            upstream_ref.ports(ei.flipud(), a_out).numpy(),
            upstream_ref.time_deltas(data, e_in).numpy(),
            upstream_ref.time_deltas(data, e_out).numpy(),
        ]
    )


def test_ports_and_time_deltas_match_upstream_on_random_graphs() -> None:
    for seed in range(15):
        src, dst, ts, n = _random_graph(seed)
        ours = np.hstack([port_columns(src, dst, ts), time_delta_columns(src, dst, ts)])
        np.testing.assert_array_equal(ours, _upstream(src, dst, ts, n))


def test_port_ties_break_by_edge_order() -> None:
    # node 9 receives from 1 then 2 at the same instant: edge order decides the ranks
    src = np.array([1, 2], dtype=np.int64)
    dst = np.array([9, 9], dtype=np.int64)
    ts = np.array([5, 5], dtype=np.int64)
    assert _ports(dst, src, ts).tolist() == [0.0, 1.0]


def test_hetero_graph_reproduces_upstream_port_swap_quirk() -> None:
    attr = torch.arange(12, dtype=torch.float32).view(2, 6)
    data = make_graph(
        3, torch.tensor([[0, 1], [1, 2]]), attr, torch.tensor([0, 1]), reverse_mp=True, ports=True
    )
    assert isinstance(data, HeteroData)
    expected = attr.clone()
    expected[:, [-1, -2]] = attr[:, [-2, -1]]
    assert torch.equal(data[EDGE].edge_attr, expected)
    assert torch.equal(data[REV].edge_attr, expected)
    assert torch.equal(data[REV].edge_index, torch.tensor([[1, 2], [0, 1]]))
    assert torch.equal(data["node"].x, torch.zeros(3, 1))
    assert torch.equal(attr, torch.arange(12, dtype=torch.float32).view(2, 6))  # input untouched


def test_paper_graphs_layout() -> None:
    e = 10
    rows = {"train": np.arange(0, 6), "val": np.arange(6, 8), "test": np.arange(8, 10)}
    graphs = paper_graphs(
        4,
        torch.randint(0, 4, (2, e)),
        torch.randn(e, 6),
        torch.zeros(e, dtype=torch.long),
        rows,
        reverse_mp=False,
        ports=True,
    )
    assert graphs["train"].data.num_edges == 6 and graphs["train"].seeds.tolist() == list(range(6))
    assert graphs["val"].data.num_edges == 8 and graphs["val"].seeds.tolist() == [6, 7]
    assert graphs["test"].data.num_edges == 10 and graphs["test"].seeds.tolist() == [8, 9]
