"""`prepare`: verify → read → node ids → codebooks → features → cache (keyed by file sha256)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from grafin_training.data.features import Codebooks, build_codebooks, paper_base_features
from grafin_training.data.load import Source, read_transactions, verify_dataset
from grafin_training.data.nodes import assign_node_ids
from grafin_training.data.split import day_index
from grafin_training.errors import DatasetError
from grafin_training.graph.build import port_columns, time_delta_columns

log = logging.getLogger(__name__)
CACHE_VERSION = 2  # 2: adds `row` (0-based input-file row index)
_ARRAYS = ("row", "src", "dst", "ts", "y", "day_idx", "base", "ports", "tds")


@dataclass(frozen=True)
class PreparedData:
    cache_dir: Path
    meta: dict[str, Any]
    codebooks: Codebooks
    row: npt.NDArray[np.int64]  # 0-based input-file row index of each (time-sorted) edge
    src: npt.NDArray[np.int64]
    dst: npt.NDArray[np.int64]
    ts: npt.NDArray[np.int64]
    y: npt.NDArray[np.int64]
    day_idx: npt.NDArray[np.int64]
    base: npt.NDArray[np.float64]
    ports: npt.NDArray[np.float32]
    tds: npt.NDArray[np.float32]

    @property
    def num_nodes(self) -> int:
        return int(self.meta["n_nodes"])

    def edge_features(self, *, ports: bool, tds: bool) -> npt.NDArray[np.float64]:
        """Upstream edge_attr layout: base 4, then [in_port, out_port], then [in_td, out_td]."""
        cols: list[npt.NDArray[Any]] = [self.base]
        if ports:
            cols.append(self.ports)
        if tds:
            cols.append(self.tds)
        return np.hstack(cols).astype(np.float64)


def _load(cache_dir: Path, meta: dict[str, Any]) -> PreparedData:
    with np.load(cache_dir / "arrays.npz") as npz:
        arrays = {name: npz[name] for name in _ARRAYS}
    codebooks = Codebooks.from_dict(json.loads((cache_dir / "codebooks.json").read_text()))
    return PreparedData(cache_dir=cache_dir, meta=meta, codebooks=codebooks, **arrays)


def _valid_meta(cache_dir: Path, sha: str) -> dict[str, Any] | None:
    meta_path = cache_dir / "meta.json"
    if not meta_path.is_file():
        return None
    meta: dict[str, Any] = json.loads(meta_path.read_text())
    if meta.get("sha256") != sha or meta.get("cache_version") != CACHE_VERSION:
        return None
    return meta


def _build(path: Path, source: Source, sha: str, out: Path) -> None:
    """Write a complete cache into `out` (meta.json last)."""
    frame, nodes = assign_node_ids(read_transactions(path))
    codebooks = build_codebooks(frame)
    row = frame.get_column("row").to_numpy().astype(np.int64)
    src = frame.get_column("from_id").to_numpy().astype(np.int64)
    dst = frame.get_column("to_id").to_numpy().astype(np.int64)
    ts = frame.get_column("ts").to_numpy().astype(np.int64)
    y = frame.get_column("is_laundering").to_numpy().astype(np.int64)
    day_idx = day_index(ts)
    out.mkdir(parents=True)
    np.savez(
        out / "arrays.npz",
        row=row,
        src=src,
        dst=dst,
        ts=ts,
        y=y,
        day_idx=day_idx,
        base=paper_base_features(frame, codebooks),
        ports=port_columns(src, dst, ts),
        tds=time_delta_columns(src, dst, ts),
    )
    nodes.write_parquet(out / "nodes.parquet")
    (out / "codebooks.json").write_text(json.dumps(codebooks.to_dict(), indent=2))
    meta = {
        "cache_version": CACHE_VERSION,
        "dataset": path.stem,
        "path": str(path),
        "source": source,
        "sha256": sha,
        "n_edges": int(src.shape[0]),
        "n_nodes": int(nodes.height),
        "n_days": int(day_idx.max()) + 1,
        "laundering": int(y.sum()),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))


def prepare_dataset(path: Path, source: Source, cache_root: Path) -> PreparedData:
    """Verify the dataset and return its cached arrays, building the cache if needed.

    Safe for parallel jobs: each builder writes a private temp dir and renames it into place;
    a builder that loses the race discards its copy and loads the winner's."""
    sha = verify_dataset(path, source)
    # Versioned name: checkouts with a different CACHE_VERSION never rebuild each other's cache.
    cache_dir = cache_root / f"{source}-{sha[:16]}-v{CACHE_VERSION}"
    meta = _valid_meta(cache_dir, sha)
    if meta is not None:
        log.info("prepare: reusing cache %s", cache_dir)
        return _load(cache_dir, meta)
    if cache_dir.exists():  # stale or incomplete cache from an older version
        shutil.rmtree(cache_dir, ignore_errors=True)
    log.info("prepare: reading %s", path)
    tmp = cache_root / f".tmp-{os.getpid()}-{cache_dir.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    _build(path, source, sha, tmp)
    try:
        os.rename(tmp, cache_dir)
    except OSError:  # another job finished first
        shutil.rmtree(tmp, ignore_errors=True)
    meta = _valid_meta(cache_dir, sha)
    if meta is None:
        raise DatasetError(f"cache at {cache_dir} is incomplete after build")
    return _load(cache_dir, meta)
