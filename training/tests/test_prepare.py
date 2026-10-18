from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from grafin_training.data.prepare import prepare_dataset
from tests import upstream_ref


def test_prepare_cache_reuse_and_stale_rebuild(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    first = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert first.meta["n_edges"] == 229 and first.num_nodes == 36
    assert first.edge_features(ports=True, tds=False).shape == (229, 6)
    assert first.edge_features(ports=True, tds=True).shape == (229, 8)
    np.testing.assert_array_equal(first.row, np.arange(229))  # ID file is already time-sorted
    again = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert again.cache_dir == first.cache_dir
    (first.cache_dir / "meta.json").write_text("{}")  # stale cache must be rebuilt
    rebuilt = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert rebuilt.meta["sha256"] == first.meta["sha256"]
    assert not any(p.name.startswith(".tmp-") for p in tmp_path.iterdir())


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


def test_ports_match_upstream_on_fixture(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    p = prepare_dataset(fixture_paths[0], "raw", tmp_path)
    ours = np.hstack([p.ports, p.tds])
    np.testing.assert_array_equal(ours, _upstream(p.src, p.dst, p.ts - p.ts.min(), p.num_nodes))


def test_prepare_keeps_input_row_index(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    p = prepare_dataset(fixture_paths[0], "raw", tmp_path)  # raw rows are NOT time-sorted
    assert sorted(p.row.tolist()) == list(range(229))
    assert not np.array_equal(p.row, np.arange(229))
    assert np.all(np.diff(p.ts) >= 0)
    stamps = [line.split(",")[0] for line in fixture_paths[0].read_text().splitlines()[1:]]
    assert [stamps[r] for r in p.row] == sorted(stamps)  # unique minutes: order is unambiguous
