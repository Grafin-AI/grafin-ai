"""Two-pass localization (spec 5 and 9).

Pass 1 streams raw rows through the transforms into Parquet. Pass 2 sorts one dataset day at
a time and appends it to the output CSV. Memory stays bounded by the largest day.
"""

import json
import shutil
import time
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from garda_ai_dataset import __version__
from garda_ai_dataset.errors import DiskSpaceError
from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from garda_ai_dataset.transforms.entities import (
    build_accounts,
    build_entities,
    first_seen_by_entity,
    read_legacy_accounts,
)
from garda_ai_dataset.transforms.institutions import assign_institutions
from garda_ai_dataset.transforms.patterns import (
    build_typologies,
    match_patterns,
    parse_patterns,
    render_patterns,
)
from garda_ai_dataset.transforms.transactions import (
    check_vocabulary,
    format_output,
    localize_features,
)

MIN_FREE_BYTES = 10 * 1024**3


def stage_transactions(raw: pl.LazyFrame, maps: Mappings) -> pl.LazyFrame:
    """Localized rows. The transforms never see the label; it is re-attached by raw_row."""
    features = localize_features(raw.drop("is_laundering"), maps)
    labels = raw.select("raw_row", pl.col("is_laundering").cast(pl.Int8))
    return features.join(labels, on="raw_row", how="inner").with_columns(
        pl.col("ts").dt.date().alias("day")
    )


def _first_day(staged: pl.DataFrame) -> date:
    first = staged["day"].min()
    if not isinstance(first, date):
        raise ValueError("no transactions to localize")
    return first


def localize_frames(
    raw: pl.DataFrame, raw_accounts: pl.DataFrame, maps: Mappings
) -> dict[str, pl.DataFrame]:
    """In-memory equivalent of run_localize, for tests and the label-independence check."""
    staged = stage_transactions(raw.lazy(), maps).sort(["ts", "raw_row"]).collect()
    first_seen = first_seen_by_entity(staged.lazy(), raw_accounts)
    entities = build_entities(raw_accounts, first_seen, _first_day(staged), maps)
    bank_names = assign_institutions(raw_accounts, maps.institutions)
    return {
        "trans": format_output(staged),
        "entities": entities,
        "accounts": build_accounts(raw_accounts, bank_names, entities, None),
    }


def run_localize(
    paths: DatasetPaths,
    maps: Mappings,
    legacy_accounts: Path | None,
    *,
    min_free_bytes: int | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    raw = scan_raw_trans(paths.raw_trans)
    raw_accounts = read_raw_accounts(paths.raw_accounts)
    attempts = parse_patterns(paths.raw_patterns)
    check_vocabulary(raw, maps)

    paths.out_dir.mkdir(parents=True, exist_ok=True)
    needed = MIN_FREE_BYTES if min_free_bytes is None else min_free_bytes
    free = shutil.disk_usage(paths.out_dir).free
    if free < needed:
        raise DiskSpaceError(
            f"{paths.out_dir} has {free / 1024**3:.1f} GiB free; need {needed / 1024**3:.1f} GiB"
        )
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    paths.tmp_dir.mkdir()

    # Pass 1: stream every row through the transforms into Parquet.
    stage_path = paths.tmp_dir / "localized.parquet"
    stage_transactions(raw, maps).sink_parquet(stage_path)
    staged = pl.scan_parquet(stage_path)

    # Pass 2: sort one day at a time and append to the output CSV.
    days: list[date] = staged.select(pl.col("day").unique().sort()).collect().to_series().to_list()
    id_parts: list[pl.DataFrame] = []
    written = 0
    with paths.out_trans.open("w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(OUT_HEADER) + "\n")
        for day in days:
            day_df = staged.filter(pl.col("day") == day).sort(["ts", "raw_row"]).collect()
            format_output(day_df).write_csv(fh, include_header=False)
            id_parts.append(
                day_df.with_row_index("transaction_id", offset=written + 1)
                .filter(pl.col("is_laundering") == 1)
                .select("raw_row", "transaction_id")
            )
            written += day_df.height
    laundering_ids = pl.concat(id_parts)

    bank_names = assign_institutions(raw_accounts, maps.institutions)
    entities = build_entities(raw_accounts, first_seen_by_entity(staged, raw_accounts), days[0], maps)
    legacy = read_legacy_accounts(legacy_accounts) if legacy_accounts is not None else None
    accounts = build_accounts(raw_accounts, bank_names, entities, legacy)
    entities.write_csv(paths.out_entities)
    accounts.write_csv(paths.out_accounts)

    match = match_patterns(attempts, raw.filter(pl.col("is_laundering") == "1").collect())
    build_typologies(laundering_ids, match).write_csv(paths.out_typologies)
    matched = (
        staged.filter(pl.col("raw_row").is_in(list(match.by_raw_row))).collect().sort("raw_row")
    )
    lines = format_output(matched).write_csv(include_header=False).splitlines()
    localized_lines = dict(zip(matched["raw_row"].to_list(), lines, strict=True))
    paths.out_patterns.write_text(
        render_patterns(attempts, match, localized_lines), encoding="utf-8"
    )

    raw_files = (paths.raw_trans, paths.raw_accounts, paths.raw_patterns)
    out_files = (paths.out_trans, paths.out_accounts, paths.out_entities, paths.out_patterns,
                 paths.out_typologies)
    manifest: dict[str, object] = {
        "pipeline_version": __version__,
        "dataset": paths.name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": {p.name: sha256_file(p) for p in raw_files},
        "mappings": maps.hashes,
        "legacy_accounts": None if legacy_accounts is None else {
            "path": str(legacy_accounts), "sha256": sha256_file(legacy_accounts)
        },
        "risk_source": "none" if legacy_accounts is None else "legacy-carryover",
        "outputs": {p.name: sha256_file(p) for p in out_files},
        "counts": {
            "transactions": written,
            "laundering": laundering_ids.height,
            "accounts": accounts.height,
            "entities": entities.height,
            "banks": len(bank_names),
            "days": len(days),
            "first_day": days[0].isoformat(),
            "last_day": days[-1].isoformat(),
        },
        "typology": {
            "attempts": len(attempts),
            "pattern_rows": sum(len(a.rows) for a in attempts),
            "matched_rows": len(match.by_raw_row),
            "unmatched_pattern_rows": match.unmatched,
            "laundering_coverage": round(len(match.by_raw_row) / max(laundering_ids.height, 1), 4),
        },
        "wall_time_s": round(time.perf_counter() - started, 1),
    }
    paths.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    return manifest
