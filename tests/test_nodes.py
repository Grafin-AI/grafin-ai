from __future__ import annotations

from pathlib import Path

import polars as pl

from garda_training.data.load import read_transactions
from garda_training.data.nodes import assign_node_ids


def test_node_ids_follow_upstream_first_appearance(fixture_paths: tuple[Path, Path]) -> None:
    raw_path, _ = fixture_paths
    frame, nodes = assign_node_ids(read_transactions(raw_path))
    assert nodes.get_column("node_id").to_list() == list(range(nodes.height))
    # upstream keys: bank string + account, in raw row order, sender before receiver
    lines = raw_path.read_text().splitlines()[1:]
    order: dict[str, int] = {}
    for line in lines:
        f = line.split(",")
        for key in (f[1] + f[2], f[3] + f[4]):
            order.setdefault(key, len(order))
    assert nodes.height == len(order)
    first = lines[0].split(",")
    row0 = frame.filter(pl.col("row") == 0)
    assert row0.get_column("from_id").item() == 0
    assert row0.get_column("to_id").item() == order[first[3] + first[4]]
