"""Port numbers, time deltas and PyG graph objects (port of upstream data_util.py)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import torch
from torch_geometric.data import Data, HeteroData

EDGE = ("node", "to", "node")
REV = ("node", "rev_to", "node")
IntArray = npt.NDArray[np.int64]
F32Array = npt.NDArray[np.float32]


def _ports(center: IntArray, other: IntArray, ts: IntArray) -> F32Array:
    """For each edge: rank of `other` among `center`'s neighbours, ordered by the time each
    neighbour first appears (ties by edge order). Vectorised upstream data_util.ports."""
    e = np.arange(center.shape[0])
    order = np.lexsort((e, ts, center))
    n = int(max(center.max(), other.max())) + 1
    pair = center[order].astype(np.int64) * n + other[order].astype(np.int64)
    uniq_pairs, first_pos = np.unique(pair, return_index=True)
    pair_center = uniq_pairs // n
    rank_order = np.lexsort((first_pos, pair_center))
    sorted_center = pair_center[rank_order]
    group_start = np.searchsorted(sorted_center, sorted_center, side="left")
    ranks = np.empty(first_pos.shape[0], dtype=np.int64)
    ranks[rank_order] = np.arange(rank_order.shape[0]) - group_start
    edge_pair = center.astype(np.int64) * n + other.astype(np.int64)
    return ranks[np.searchsorted(uniq_pairs, edge_pair)].astype(np.float32)


def _time_deltas(center: IntArray, ts: IntArray) -> F32Array:
    """For each edge: time since the previous edge at the same `center` node (first edge → 0),
    ordering by (time, edge order). Vectorised upstream data_util.time_deltas."""
    e = np.arange(center.shape[0])
    order = np.lexsort((e, ts, center))
    c_s = center[order]
    t_s = ts[order].astype(np.float64)
    same = c_s[1:] == c_s[:-1]
    td_sorted = np.concatenate([[0.0], np.where(same, t_s[1:] - t_s[:-1], 0.0)])
    td = np.empty(center.shape[0], dtype=np.float64)
    td[order] = td_sorted
    return td.astype(np.float32)


def port_columns(src: IntArray, dst: IntArray, ts: IntArray) -> F32Array:
    """[E, 2]: in-port (rank of src among dst's in-neighbours), out-port (rank of dst among
    src's out-neighbours) — upstream add_ports column order."""
    return np.column_stack([_ports(dst, src, ts), _ports(src, dst, ts)])


def time_delta_columns(src: IntArray, dst: IntArray, ts: IntArray) -> F32Array:
    """[E, 2]: in-time-delta (at dst), out-time-delta (at src) — upstream add_time_deltas order."""
    return np.column_stack([_time_deltas(dst, ts), _time_deltas(src, ts)])


def make_graph(
    num_nodes: int,
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
    y: torch.Tensor,
    *,
    reverse_mp: bool,
    ports: bool,
) -> Data | HeteroData:
    """Homogeneous Data, or HeteroData with forward 'to' and reversed 'rev_to' edges."""
    # Upstream: z_norm of the all-ones placeholder node feature gives all zeros.
    x = torch.zeros((num_nodes, 1), dtype=torch.float32)
    if not reverse_mp:
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)
    attr = edge_attr.clone()
    if ports:
        # UPSTREAM QUIRK (data_util.create_hetero_obj @252b025): the rev_to port swap is done in
        # place on a tensor shared with the 'to' edge type, so BOTH edge types end up with the
        # last two columns swapped. Reproduced on purpose for paper parity.
        attr[:, [-1, -2]] = attr[:, [-2, -1]]
    data = HeteroData()
    data["node"].x = x
    data[EDGE].edge_index = edge_index
    data[REV].edge_index = edge_index.flipud()
    data[EDGE].edge_attr = attr
    data[REV].edge_attr = attr
    data[EDGE].y = y
    return data


@dataclass(frozen=True)
class SplitGraph:
    """A graph plus the positions (within it) of the edges that are trained on / scored."""

    data: Data | HeteroData
    seeds: torch.Tensor


def paper_graphs(
    num_nodes: int,
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
    y: torch.Tensor,
    rows: dict[str, IntArray],
    *,
    reverse_mp: bool,
    ports: bool,
) -> dict[str, SplitGraph]:
    """Upstream paper protocol: train graph = train edges; val graph = train+val edges (val
    scored); test graph = all edges (test scored). `rows` holds sorted global edge positions."""
    tr, va, te = rows["train"], rows["val"], rows["test"]
    layout = {
        "train": (tr, tr),
        "val": (np.concatenate([tr, va]), va),
        "test": (np.concatenate([tr, va, te]), te),
    }
    graphs: dict[str, SplitGraph] = {}
    for name, (graph_rows, seed_rows) in layout.items():
        ordered = np.sort(graph_rows)
        idx = torch.from_numpy(ordered)
        data = make_graph(
            num_nodes,
            edge_index[:, idx],
            edge_attr[idx],
            y[idx],
            reverse_mp=reverse_mp,
            ports=ports,
        )
        seeds = torch.from_numpy(np.searchsorted(ordered, seed_rows).astype(np.int64))
        graphs[name] = SplitGraph(data, seeds)
    return graphs
