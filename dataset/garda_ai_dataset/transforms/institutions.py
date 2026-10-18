"""Give each IBM Bank ID one Indonesian institution name (spec 6.3). Never reads the label."""

from collections.abc import Sequence

import polars as pl

from garda_ai_dataset.mappings import Institution

CRYPTO_BANK_PREFIX = "Crytpo Bank"  # IBM's own spelling in the HI-* accounts files


def assign_institutions(
    raw_accounts: pl.DataFrame, institutions: Sequence[Institution]
) -> dict[int, str]:
    banks = (
        raw_accounts.with_columns(pl.col("Bank ID").cast(pl.Int64).alias("bank_id"))
        .group_by("bank_id")
        .agg(pl.len().alias("n_accounts"), pl.col("Bank Name").min().alias("ibm_name"))
    )
    assigned: dict[int, str] = {}
    for kind, is_crypto in (("bank", False), ("crypto_exchange", True)):
        pool = banks.filter(
            pl.col("ibm_name").str.starts_with(CRYPTO_BANK_PREFIX) == is_crypto
        ).sort(["n_accounts", "bank_id"], descending=[True, False])
        targets = sorted(
            (i for i in institutions if i.kind == kind), key=lambda i: (-i.weight, i.name)
        )
        assigned.update(_fill(pool["bank_id"].to_list(), pool["n_accounts"].to_list(), targets))
    return assigned


def _fill(bank_ids: list[int], sizes: list[int], targets: list[Institution]) -> dict[int, str]:
    """Walk banks largest-first; move to the next institution once the current one holds its
    weighted share of accounts. Advancing at most one institution per bank guarantees every
    institution gets a bank whenever there are at least as many banks as institutions."""
    if not bank_ids:
        return {}
    total_accounts = sum(sizes)
    total_weight = sum(t.weight for t in targets)
    thresholds: list[float] = []
    running = 0
    for target in targets:
        running += target.weight
        thresholds.append(total_accounts * running / total_weight)
    out: dict[int, str] = {}
    index = 0
    filled = 0
    for bank_id, size in zip(bank_ids, sizes, strict=True):
        out[bank_id] = targets[index].name
        filled += size
        if index < len(targets) - 1 and filled >= thresholds[index]:
            index += 1
    return out
