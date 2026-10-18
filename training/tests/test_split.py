from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from grafin_training.data.load import read_transactions
from grafin_training.data.split import calibration_split, day_index, paper_split, rows_for_days
from grafin_training.errors import ConfigError
from tests import upstream_ref

HI_SMALL_DAILY = [
    1114921,
    754449,
    207382,
    207430,
    482650,
    482089,
    482751,
    482773,
    654467,
    208325,
    396,
    281,
    184,
    121,
    46,
    46,
    23,
    11,
]


def test_paper_split_matches_upstream_on_hi_small_counts() -> None:
    day_idx = np.repeat(np.arange(len(HI_SMALL_DAILY)), HI_SMALL_DAILY).astype(np.int64)
    split = paper_split(day_idx)
    expected = upstream_ref.paper_split_days(HI_SMALL_DAILY)
    assert [list(split.train_days), list(split.val_days), list(split.test_days)] == expected
    assert split.train_days == tuple(range(6)) and split.val_days == (6, 7)


def test_paper_split_matches_upstream_on_fixture(fixture_paths: tuple[Path, Path]) -> None:
    ts = read_transactions(fixture_paths[0]).get_column("ts").to_numpy()
    day_idx = day_index(ts)
    split = paper_split(day_idx)
    expected = upstream_ref.paper_split_days(np.bincount(day_idx).tolist())
    assert [list(split.train_days), list(split.val_days), list(split.test_days)] == expected


def test_paper_split_needs_three_days() -> None:
    with pytest.raises(ConfigError):
        paper_split(np.array([0, 0, 1], dtype=np.int64))


def test_calibration_split_on_hi_small() -> None:
    day_idx = np.repeat(np.arange(len(HI_SMALL_DAILY)), HI_SMALL_DAILY).astype(np.int64)
    fit, calib = calibration_split(day_idx, tuple(range(6)))
    assert fit == (0, 1, 2, 3, 4) and calib == (5,)
    with pytest.raises(ConfigError):
        calibration_split(day_idx, (0,))


def test_rows_for_days() -> None:
    day_idx = np.array([0, 0, 1, 2, 2], dtype=np.int64)
    assert rows_for_days(day_idx, (0, 2)).tolist() == [0, 1, 3, 4]
