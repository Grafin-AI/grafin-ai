from __future__ import annotations

import numpy as np

from garda_training.train.typology import (
    CYCLE,
    FAN_IN,
    FAN_OUT,
    GATHER_SCATTER,
    GNN_TYPOLOGY,
    VELOCITY,
    WINDOW_S,
    typologies,
)

H = 3600


def _name(edges: list[tuple[int, int, int]], query: int = -1) -> str:
    """Typology of edges[query] (default: the last edge) in a graph of (src, dst, ts) edges."""
    src, dst, ts = (np.array(c, dtype=np.int64) for c in zip(*edges))
    order = np.argsort(ts, kind="stable")
    q = int(np.flatnonzero(order == (query % len(edges)))[0])
    return typologies(src[order], dst[order], ts[order], np.array([q], dtype=np.int64))[0]


def test_plain_edge_is_the_model_call() -> None:
    assert _name([(1, 2, 10 * H)]) == GNN_TYPOLOGY


def test_fan_in_counts_distinct_senders() -> None:
    edges = [(s, 0, s * H) for s in range(1, 5)] + [(5, 0, 6 * H)]
    assert _name(edges) == FAN_IN
    repeat = [(1, 0, s * H) for s in range(1, 5)] + [(5, 0, 6 * H)]  # 2 distinct, 5 edges
    assert _name(repeat) == GNN_TYPOLOGY


def test_fan_out_and_window_is_causal() -> None:
    edges = [(0, r, r * H) for r in range(1, 6)]
    assert _name(edges) == FAN_OUT
    assert _name(edges, query=0) == GNN_TYPOLOGY  # later edges are not visible yet
    stale = [(0, r, r * H) for r in range(1, 5)] + [(0, 9, 4 * H + WINDOW_S + 1)]
    assert _name(stale) == GNN_TYPOLOGY  # first edges fell out of the 24 h window


def test_cycle_of_two_and_three() -> None:
    assert _name([(2, 1, 1 * H), (1, 2, 2 * H)]) == CYCLE
    assert _name([(2, 3, 1 * H), (3, 1, 2 * H), (1, 2, 3 * H)]) == CYCLE
    assert _name([(1, 1, 1 * H), (1, 1, 2 * H)]) != CYCLE  # self-loops are not cycles
    assert _name([(1, 2, 1 * H), (2, 1, 2 * H)], query=0) == GNN_TYPOLOGY  # closes later


def test_gather_scatter_beats_fan_in() -> None:
    collect = [(s, 0, s * H) for s in range(1, 6)]
    pay_out = [(0, r, 6 * H + r) for r in range(10, 15)]
    assert _name([*collect, *pay_out, (7, 0, 8 * H)]) == GATHER_SCATTER


def test_velocity_without_fan() -> None:
    edges = [(1, 2, k * 60) for k in range(10)]
    assert _name(edges) == VELOCITY


def test_empty_query() -> None:
    z = np.zeros(0, dtype=np.int64)
    assert typologies(z, z, z, z) == []
