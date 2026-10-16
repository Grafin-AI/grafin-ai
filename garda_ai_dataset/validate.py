"""Invariant checks (spec 8), run one dataset day at a time so HI-Medium fits in memory.

Every check re-derives its expectation from the RAW files. Nothing is trusted from the build.
"""

import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import polars as pl

from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.localize import localize_frames
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import (
    OUT_HEADER,
    TRANS_COLS,
    read_raw_accounts,
    scan_raw_trans,
    scan_trans_csv,
)
from garda_ai_dataset.transforms.entities import first_seen_by_entity
from garda_ai_dataset.transforms.patterns import build_typologies, match_patterns, parse_patterns
from garda_ai_dataset.transforms.transactions import OFFSET_DAYS, parse_ts, to_idr

LABEL_SAMPLE_ROWS = 200_000
ROW_CHECKS = ("labels", "graph_keys", "fx", "time", "order", "channels")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    distribution: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failed(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name, ok, detail))

    def render(self) -> str:
        lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.name:<20} {c.detail}" for c in self.checks]
        return "\n".join([*lines, "", "Distribution (informational):", *self.distribution])


def validate_dataset(
    paths: DatasetPaths, maps: Mappings, *, label_sample_rows: int = LABEL_SAMPLE_ROWS
) -> ValidationReport:
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    paths.tmp_dir.mkdir(parents=True)
    try:
        return _validate(paths, maps, label_sample_rows)
    finally:
        shutil.rmtree(paths.tmp_dir, ignore_errors=True)


def _differs(a: pl.Expr, b: pl.Expr) -> pl.Expr:
    return (a != b).fill_null(True)


def _as_int(column: str) -> pl.Expr:
    return pl.col(column).cast(pl.Int64, strict=False)


def _day_mismatches(r: pl.DataFrame, o: pl.DataFrame, maps: Mappings) -> dict[str, int]:
    df = pl.concat([r.rename(lambda c: f"r_{c}"), o.rename(lambda c: f"o_{c}")], how="horizontal")
    exprs = {
        "labels": _differs(pl.col("r_is_laundering"), pl.col("o_is_laundering")),
        "graph_keys": _differs(_as_int("r_from_bank"), _as_int("o_from_bank"))
        | _differs(pl.col("r_from_account"), pl.col("o_from_account"))
        | _differs(_as_int("r_to_bank"), _as_int("o_to_bank"))
        | _differs(pl.col("r_to_account"), pl.col("o_to_account")),
        "fx": _differs(to_idr("r_amount_paid", "r_payment_currency", maps.fx),
                       _as_int("o_amount_paid"))
        | _differs(to_idr("r_amount_received", "r_receiving_currency", maps.fx),
                   _as_int("o_amount_received"))
        | _differs(pl.col("o_payment_currency"), pl.lit("IDR"))
        | _differs(pl.col("o_receiving_currency"), pl.lit("IDR")),
        "time": _differs(pl.col("o_out_ts") - pl.col("r_raw_ts"),
                         pl.lit(timedelta(days=OFFSET_DAYS))),
        "order": (pl.col("o_out_ts").diff() < pl.duration(minutes=0)).fill_null(False),
        "channels": _differs(
            pl.col("r_payment_format").replace_strict(maps.channels, return_dtype=pl.String),
            pl.col("o_payment_format"),
        ),
    }
    row = df.select([e.sum().alias(k) for k, e in exprs.items()]).row(0, named=True)
    return {k: int(v) for k, v in row.items()}


def _validate(paths: DatasetPaths, maps: Mappings, label_sample_rows: int) -> ValidationReport:
    report = ValidationReport()
    with paths.out_trans.open(encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n")
    report.add("header", header == ",".join(OUT_HEADER), header)

    raw_pq = paths.tmp_dir / "raw.parquet"
    out_pq = paths.tmp_dir / "out.parquet"
    scan_raw_trans(paths.raw_trans).with_columns(parse_ts("timestamp").alias("raw_ts")).with_columns(
        pl.col("raw_ts").dt.date().alias("raw_day")
    ).sink_parquet(raw_pq)
    scan_trans_csv(paths.out_trans).with_row_index("transaction_id", offset=1).with_columns(
        parse_ts("timestamp", strict=False).alias("out_ts")
    ).sink_parquet(out_pq)
    raw = pl.scan_parquet(raw_pq)
    out = pl.scan_parquet(out_pq)

    sides = pl.concat(
        [
            raw.select(pl.col("from_bank").alias("bank"), pl.col("from_account").alias("account")),
            raw.select(pl.col("to_bank").alias("bank"), pl.col("to_account").alias("account")),
        ]
    )
    n_text = int(sides.unique().select(pl.len()).collect().item())
    n_int = int(
        sides.with_columns(pl.col("bank").cast(pl.Int64)).unique().select(pl.len()).collect().item()
    )
    report.add("node_merge", n_text == n_int, f"text keys={n_text} integer keys={n_int}")

    # Row-level checks, one raw day at a time.
    mismatches: dict[str, int] = defaultdict(int)
    day_errors: list[str] = []
    id_parts: list[pl.DataFrame] = []
    last_ts: datetime | None = None
    raw_days: list[date] = (
        raw.select(pl.col("raw_day").unique().sort()).collect().to_series().to_list()
    )
    for day in raw_days:
        r = raw.filter(pl.col("raw_day") == day).sort(["raw_ts", "raw_row"]).collect()
        o = (
            out.filter(pl.col("out_ts").dt.date() == day + timedelta(days=OFFSET_DAYS))
            .sort("transaction_id")
            .collect()
        )
        if r.height != o.height:
            day_errors.append(f"{day}: raw={r.height} out={o.height}")
            continue
        for name, count in _day_mismatches(r, o, maps).items():
            mismatches[name] += count
        if o.height:
            if last_ts is not None and o["out_ts"][0] < last_ts:
                mismatches["order"] += 1
            last_ts = o["out_ts"][-1]
        id_parts.append(
            pl.DataFrame({"raw_row": r["raw_row"], "transaction_id": o["transaction_id"],
                          "is_laundering": r["is_laundering"]})
            .filter(pl.col("is_laundering") == "1")
            .drop("is_laundering")
        )
    n_raw = int(raw.select(pl.len()).collect().item())
    n_out = int(out.select(pl.len()).collect().item())
    report.add("row_count", n_raw == n_out and not day_errors,
               f"raw={n_raw} out={n_out} {'; '.join(day_errors)}".strip())
    for name in ROW_CHECKS:
        report.add(name, mismatches[name] == 0 and not day_errors,
                   f"{mismatches[name]} mismatching rows")

    _check_label_independence(report, paths, maps, label_sample_rows)
    _check_patterns(report, paths, raw, out, id_parts)
    _check_entities(report, paths, maps, out)
    _check_manifest(report, paths, maps)
    report.distribution = _distribution(paths, maps, out)
    return report


def _check_label_independence(report: ValidationReport, paths: DatasetPaths, maps: Mappings,
                              sample_rows: int) -> None:
    sample = scan_raw_trans(paths.raw_trans).head(sample_rows).collect()
    keys = pl.concat(
        [
            sample.select(pl.col("from_bank").cast(pl.Int64).alias("b"),
                          pl.col("from_account").alias("a")),
            sample.select(pl.col("to_bank").cast(pl.Int64).alias("b"),
                          pl.col("to_account").alias("a")),
        ]
    ).unique()
    accounts = (
        read_raw_accounts(paths.raw_accounts)
        .with_columns(pl.col("Bank ID").cast(pl.Int64).alias("_b"))
        .join(keys, left_on=["_b", "Account Number"], right_on=["b", "a"], how="semi")
        .drop("_b")
    )
    inverted = sample.with_columns(
        (1 - pl.col("is_laundering").cast(pl.Int8)).cast(pl.String).alias("is_laundering")
    )
    normal = localize_frames(sample, accounts, maps)
    flipped = localize_frames(inverted, accounts, maps)
    same = (
        normal["trans"].drop("Is Laundering").equals(flipped["trans"].drop("Is Laundering"))
        and normal["entities"].equals(flipped["entities"])
        and normal["accounts"].equals(flipped["accounts"])
    )
    changed = not normal["trans"]["Is Laundering"].equals(flipped["trans"]["Is Laundering"])
    report.add("label_independence", same and changed,
               f"{sample.height} rows; labels inverted, non-label outputs "
               f"{'identical' if same else 'DIFFER'}")


def _check_patterns(report: ValidationReport, paths: DatasetPaths, raw: pl.LazyFrame,
                    out: pl.LazyFrame, id_parts: list[pl.DataFrame]) -> None:
    attempts = parse_patterns(paths.raw_patterns)
    laundering = raw.filter(pl.col("is_laundering") == "1").select(*TRANS_COLS, "raw_row").collect()
    match = match_patterns(attempts, laundering)
    ids = (
        pl.concat(id_parts)
        if id_parts
        else pl.DataFrame(schema={"raw_row": pl.UInt32, "transaction_id": pl.UInt32})
    )
    expected = build_typologies(ids, match)
    actual = pl.read_csv(
        paths.out_typologies,
        schema={"transaction_id": pl.UInt32, "attempt_id": pl.Int64, "motif": pl.String},
    )
    tids = actual.filter(pl.col("attempt_id").is_not_null())["transaction_id"].to_list()
    trans_lines = sorted(
        out.filter(pl.col("transaction_id").is_in(tids))
        .select(pl.concat_str([pl.col(c) for c in TRANS_COLS], separator=","))
        .collect()
        .to_series()
        .to_list()
    )
    pattern_lines = sorted(
        line for line in paths.out_patterns.read_text(encoding="utf-8").splitlines()
        if line[:1].isdigit()
    )
    ok = match.unmatched == 0 and expected.equals(actual) and trans_lines == pattern_lines
    report.add("patterns", ok,
               f"unmatched pattern rows={match.unmatched}; typologies "
               f"{'match' if expected.equals(actual) else 'DIFFER'}; pattern lines "
               f"{'match' if trans_lines == pattern_lines else 'DIFFER'}; coverage="
               f"{len(match.by_raw_row)}/{expected.height}")


def _check_entities(report: ValidationReport, paths: DatasetPaths, maps: Mappings,
                    out: pl.LazyFrame) -> None:
    entities = pl.read_csv(paths.out_entities, infer_schema=False)
    accounts = pl.read_csv(paths.out_accounts, infer_schema=False)
    orphan_accounts = accounts.join(entities, on="Entity ID", how="anti").height
    name_mismatch = (
        accounts.join(entities.select("Entity ID", pl.col("Entity Name").alias("_n")),
                      on="Entity ID")
        .filter(pl.col("Entity Name") != pl.col("_n"))
        .height
    )
    known = {i.name for i in maps.institutions}
    unknown_banks = sorted(set(accounts["Bank Name"].to_list()) - known)
    trans = out.select(
        pl.col("from_bank").cast(pl.Int64, strict=False),
        "from_account",
        pl.col("to_bank").cast(pl.Int64, strict=False),
        "to_account",
        pl.col("out_ts").alias("ts"),
    )
    first_seen = first_seen_by_entity(trans, accounts)
    late = 0
    for entity_id, registered in entities.select("Entity ID", "Registration Date").iter_rows():
        if entity_id not in first_seen:
            continue
        try:
            if date.fromisoformat(registered) >= first_seen[entity_id]:
                late += 1
        except ValueError:
            late += 1
    trans_keys = pl.concat(
        [
            trans.select(pl.col("from_bank").alias("b"), pl.col("from_account").alias("a")),
            trans.select(pl.col("to_bank").alias("b"), pl.col("to_account").alias("a")),
        ]
    ).unique()
    account_keys = accounts.lazy().select(
        pl.col("Bank ID").cast(pl.Int64).alias("b"), pl.col("Account Number").alias("a")
    )
    missing_accounts = int(
        trans_keys.join(account_keys, on=["b", "a"], how="anti").select(pl.len()).collect().item()
    )
    ok = not (orphan_accounts or name_mismatch or unknown_banks or late or missing_accounts)
    report.add("entities", ok,
               f"accounts without entity={orphan_accounts}, name mismatches={name_mismatch}, "
               f"unknown institutions={unknown_banks}, registration not before first "
               f"transaction={late}, transaction accounts missing from accounts.csv="
               f"{missing_accounts}")


def _check_manifest(report: ValidationReport, paths: DatasetPaths, maps: Mappings) -> None:
    try:
        manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("manifest", False, f"unreadable: {exc}")
        return
    raw_files = (paths.raw_trans, paths.raw_accounts, paths.raw_patterns)
    out_files = (paths.out_trans, paths.out_accounts, paths.out_entities, paths.out_patterns,
                 paths.out_typologies)
    ok = (
        manifest.get("inputs") == {p.name: sha256_file(p) for p in raw_files}
        and manifest.get("mappings") == maps.hashes
        and manifest.get("outputs") == {p.name: sha256_file(p) for p in out_files}
    )
    report.add("manifest", ok,
               "hashes match" if ok else "a recorded sha256 differs from the file on disk")


def _distribution(paths: DatasetPaths, maps: Mappings, out: pl.LazyFrame) -> list[str]:
    lines: list[str] = []
    per_channel = (
        out.group_by("payment_format")
        .agg(
            pl.len().alias("rows"),
            (pl.col("is_laundering") == "1").mean().alias("rate"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).median().alias("p50"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).quantile(0.99).alias("p99"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).max().alias("max"),
        )
        .sort("rows", descending=True)
        .collect()
    )
    lines.append(f"{'channel':<20}{'rows':>12}{'laundering %':>14}{'p50 IDR':>18}"
                 f"{'p99 IDR':>22}{'max IDR':>24}")
    for row in per_channel.iter_rows(named=True):
        lines.append(f"{row['payment_format']:<20}{row['rows']:>12,}{row['rate'] * 100:>13.3f}%"
                     f"{row['p50']:>18,.0f}{row['p99']:>22,.0f}{row['max']:>24,}")
    group_of = {i.name: i.group for i in maps.institutions}
    bank_group = (
        pl.read_csv(paths.out_accounts, infer_schema=False)
        .select(pl.col("Bank ID").cast(pl.Int64).alias("bank"), "Bank Name")
        .unique("bank")
        .with_columns(pl.col("Bank Name").replace_strict(group_of, default="?").alias("group"))
        .select("bank", "group")
    )
    per_group = (
        out.select(pl.col("from_bank").cast(pl.Int64, strict=False).alias("bank"))
        .join(bank_group.lazy(), on="bank", how="left")
        .group_by("group")
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
        .collect()
    )
    lines.append("")
    lines.append("sender institution group: " + ", ".join(
        f"{g}={n:,}" for g, n in per_group.iter_rows()))
    types = pl.read_csv(paths.out_entities, infer_schema=False)["Entity Type"].value_counts(
        sort=True)
    lines.append("entity types: " + ", ".join(f"{t}={n:,}" for t, n in types.iter_rows()))
    return lines
