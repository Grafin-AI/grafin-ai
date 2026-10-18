"""(bank, account) → contiguous node ids, numbered like the upstream formatter."""

from __future__ import annotations

import polars as pl


def assign_node_ids(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Add from_id/to_id; return (frame, nodes[node_id, bank, account]).

    Ids follow first appearance in input row order, sender before receiver within a row — the
    order IBM's format_kaggle_files.py assigns them. The output frame keeps its row order.
    """
    by_row = frame.sort("row")
    keys = pl.concat(
        [
            by_row.select(
                "row",
                pl.lit(0, pl.Int8).alias("side"),
                pl.col("from_bank").alias("bank"),
                pl.col("from_account").alias("account"),
            ),
            by_row.select(
                "row",
                pl.lit(1, pl.Int8).alias("side"),
                pl.col("to_bank").alias("bank"),
                pl.col("to_account").alias("account"),
            ),
        ]
    ).sort(["row", "side"])
    nodes = (
        keys.unique(subset=["bank", "account"], keep="first", maintain_order=True)
        .select("bank", "account")
        .with_row_index("node_id")
        .with_columns(pl.col("node_id").cast(pl.Int64))
    )
    from_ids = nodes.rename({"node_id": "from_id", "bank": "from_bank", "account": "from_account"})
    to_ids = nodes.rename({"node_id": "to_id", "bank": "to_bank", "account": "to_account"})
    out = frame.join(from_ids, on=["from_bank", "from_account"], how="left", maintain_order="left")
    out = out.join(to_ids, on=["to_bank", "to_account"], how="left", maintain_order="left")
    return out, nodes
