"""Name the network pattern behind a flagged/blocked transaction, for the dashboard.

Read only from the transaction graph (who sent to whom, when) and never from the labels, and
causal: a transaction at time t sees only edges with timestamp in [t - window, t] (itself
included), the same window the platform's explanation evidence uses. Fan thresholds match the
backend's risk factors (grafin-ai-backend services/explain/rules.py), so a "Fan-in" typology
comes with a "Fan-in Tinggi" factor. First matching rule wins:

  cycle          the receiver already reaches the sender within CYCLE_WINDOW_S
                 (v -> u, or v -> w -> u), so this edge closes a loop of length 2 or 3
  gather-scatter one endpoint both collects from and pays out to >= FAN distinct accounts
  fan-in         receiver has >= FAN distinct senders in 24 h
  fan-out        sender has >= FAN distinct receivers in 24 h
  velocity       sender's outgoing or receiver's incoming count in 24 h >= VELOCITY
  otherwise      the model's call alone (GNN_TYPOLOGY)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

GNN_TYPOLOGY = "Anomali Jaringan (GNN)"
CYCLE = "Siklus Dana (Cycle)"
GATHER_SCATTER = "Penampung-Penyebar (Gather-Scatter)"
FAN_IN = "Pengumpulan Dana (Fan-in)"
FAN_OUT = "Penyebaran Dana (Fan-out)"
VELOCITY = "Velositas Tinggi"
TYPOLOGIES = (CYCLE, GATHER_SCATTER, FAN_IN, FAN_OUT, VELOCITY, GNN_TYPOLOGY)

WINDOW_S = 24 * 3600
CYCLE_WINDOW_S = 3 * 24 * 3600
FAN = 5  # backend FAN_THRESHOLD
VELOCITY_COUNT = 10  # backend VELOCITY_THRESHOLD

Ints = npt.NDArray[np.int64]


@dataclass(frozen=True)
class _Adjacency:
    """Edges grouped by one endpoint (`key`) and time-sorted inside each group."""

    key: Ints  # composite key[e] = node * stride + (ts - t0), ascending
    other: Ints  # the opposite endpoint, aligned with `key`
    stride: int
    t0: int

    @classmethod
    def build(cls, node: Ints, other: Ints, ts: Ints) -> _Adjacency:
        t0 = int(ts.min()) if ts.size else 0
        stride = int(ts.max()) - t0 + 2 if ts.size else 2
        order = np.lexsort((ts, node))
        key = node[order] * stride + (ts[order] - t0)
        return cls(key=key, other=other[order], stride=stride, t0=t0)

    def bounds(self, node: Ints, t: Ints, window: int) -> tuple[Ints, Ints]:
        """[lo, hi) slice of each node's edges with ts in [t - window, t]."""
        rel = t - self.t0
        lo_t = np.maximum(rel - window, 0)
        lo = np.searchsorted(self.key, node * self.stride + lo_t, side="left")
        hi = np.searchsorted(self.key, node * self.stride + rel, side="right")
        return lo.astype(np.int64), hi.astype(np.int64)

    def distinct(self, lo: Ints, hi: Ints, mask: npt.NDArray[np.bool_]) -> Ints:
        """Distinct opposite endpoints per slice; only computed where `mask` (else 0)."""
        out = np.zeros(lo.shape[0], dtype=np.int64)
        for j in np.flatnonzero(mask):
            out[j] = np.unique(self.other[lo[j] : hi[j]]).size
        return out


def typologies(src: Ints, dst: Ints, ts: Ints, query: Ints) -> list[str]:
    """One typology name per edge index in `query` (indices into src/dst/ts)."""
    if query.size == 0:
        return []
    by_src = _Adjacency.build(src, dst, ts)
    by_dst = _Adjacency.build(dst, src, ts)
    u, v, t = src[query], dst[query], ts[query]

    # counts first; distinct counts only where the raw count can reach FAN
    out_u = by_src.bounds(u, t, WINDOW_S)
    in_v = by_dst.bounds(v, t, WINDOW_S)
    in_u = by_dst.bounds(u, t, WINDOW_S)
    out_v = by_src.bounds(v, t, WINDOW_S)
    n_out_u, n_in_v = out_u[1] - out_u[0], in_v[1] - in_v[0]
    fan_out_u = by_src.distinct(*out_u, n_out_u >= FAN)
    fan_in_v = by_dst.distinct(*in_v, n_in_v >= FAN)
    fan_in_u = by_dst.distinct(*in_u, (in_u[1] - in_u[0] >= FAN) & (fan_out_u >= FAN))
    fan_out_v = by_src.distinct(*out_v, (out_v[1] - out_v[0] >= FAN) & (fan_in_v >= FAN))

    cyc_out_v = by_src.bounds(v, t, CYCLE_WINDOW_S)
    cyc_in_u = by_dst.bounds(u, t, CYCLE_WINDOW_S)

    names: list[str] = []
    for j in range(query.size):
        if _closes_cycle(by_src, by_dst, int(u[j]), int(v[j]), cyc_out_v, cyc_in_u, j):
            names.append(CYCLE)
        elif (fan_in_u[j] >= FAN and fan_out_u[j] >= FAN) or (
            fan_in_v[j] >= FAN and fan_out_v[j] >= FAN
        ):
            names.append(GATHER_SCATTER)
        elif fan_in_v[j] >= FAN:
            names.append(FAN_IN)
        elif fan_out_u[j] >= FAN:
            names.append(FAN_OUT)
        elif max(n_out_u[j], n_in_v[j]) >= VELOCITY_COUNT:
            names.append(VELOCITY)
        else:
            names.append(GNN_TYPOLOGY)
    return names


def _closes_cycle(
    by_src: _Adjacency,
    by_dst: _Adjacency,
    u: int,
    v: int,
    out_v: tuple[Ints, Ints],
    in_u: tuple[Ints, Ints],
    j: int,
) -> bool:
    if u == v:
        return False
    succ = by_src.other[out_v[0][j] : out_v[1][j]]  # v -> succ
    if succ.size == 0:
        return False
    if np.any(succ == u):
        return True
    pred = by_dst.other[in_u[0][j] : in_u[1][j]]  # pred -> u
    mid = np.intersect1d(succ, pred)
    return bool(np.any((mid != u) & (mid != v)))
