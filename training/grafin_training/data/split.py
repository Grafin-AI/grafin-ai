"""Day-based temporal splits."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from grafin_training.errors import ConfigError

SECONDS_PER_DAY = 86_400
IntArray = npt.NDArray[np.int64]


def day_index(ts: IntArray) -> IntArray:
    """Day number relative to the first transaction (upstream: (ts - min) // 86400)."""
    out: IntArray = ((ts - ts.min()) // SECONDS_PER_DAY).astype(np.int64)
    return out


@dataclass(frozen=True)
class DaySplit:
    train_days: tuple[int, ...]
    val_days: tuple[int, ...]
    test_days: tuple[int, ...]

    def to_dict(self) -> dict[str, list[int]]:
        return {
            "train_days": list(self.train_days),
            "val_days": list(self.val_days),
            "test_days": list(self.test_days),
        }


def paper_split(
    day_idx: IntArray, fractions: tuple[float, float, float] = (0.6, 0.2, 0.2)
) -> DaySplit:
    """Upstream data_loading.get_data split: choose day boundaries i < j that minimise the
    largest relative error between the split proportions (by transaction count) and `fractions`.
    Ties keep the first (i, j) in itertools.combinations order, as upstream's min() does."""
    n_days = int(day_idx.max()) + 1
    if n_days < 3:
        raise ConfigError(f"need at least 3 days of data for a 3-way split, got {n_days}")
    d_ts = np.bincount(day_idx, minlength=n_days)
    scores: dict[tuple[int, int], float] = {}
    for i, j in itertools.combinations(range(n_days), 2):
        totals = [d_ts[:i].sum(), d_ts[i:j].sum(), d_ts[j:].sum()]
        total = float(np.sum(totals))
        props = [v / total for v in totals]
        scores[(i, j)] = max(abs(v - t) / t for v, t in zip(props, fractions))
    i, j = min(scores, key=scores.__getitem__)
    return DaySplit(tuple(range(i)), tuple(range(i, j)), tuple(range(j, n_days)))


def calibration_split(
    day_idx: IntArray, train_days: tuple[int, ...], fit_fraction: float = 0.8
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Split training days into (GNN-fit days, calibration days) at the day boundary whose
    cumulative transaction share is closest to `fit_fraction`; both parts are non-empty."""
    if len(train_days) < 2:
        raise ConfigError("calibration split needs at least 2 training days")
    counts = np.bincount(day_idx, minlength=max(train_days) + 1)[list(train_days)]
    cum = np.cumsum(counts) / counts.sum()
    k = 1 + int(np.argmin(np.abs(cum[:-1] - fit_fraction)))
    return train_days[:k], train_days[k:]


def rows_for_days(day_idx: IntArray, days: tuple[int, ...]) -> IntArray:
    return np.flatnonzero(np.isin(day_idx, np.asarray(days, dtype=np.int64))).astype(np.int64)
