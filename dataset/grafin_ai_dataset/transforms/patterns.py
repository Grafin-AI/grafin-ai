"""Parse IBM Patterns.txt, match attempts to Trans rows, emit motif labels (spec 6.5).

Unlike every other transform this module reads the label ON PURPOSE: typologies.csv is
itself a label product. Matching only ever considers Is Laundering == 1 rows.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from grafin_ai_dataset.errors import RawInputError
from grafin_ai_dataset.raw import TRANS_COLS

_BEGIN = re.compile(r"^BEGIN LAUNDERING ATTEMPT - (?P<motif>[A-Z][A-Z-]*)")
_END = "END LAUNDERING ATTEMPT"
UNATTRIBUTED = "UNATTRIBUTED"


@dataclass(frozen=True)
class Attempt:
    attempt_id: int
    motif: str
    begin_line: str
    end_line: str
    rows: tuple[str, ...]  # raw CSV line text, exactly as in the file


@dataclass(frozen=True)
class PatternMatch:
    by_raw_row: dict[int, tuple[int, str]]  # raw_row -> (attempt_id, motif)
    rows_per_attempt: tuple[tuple[int | None, ...], ...]  # matched raw_row per pattern row
    unmatched: int


def parse_patterns(path: Path) -> list[Attempt]:
    if not path.exists():
        raise RawInputError(f"input missing: {path} (run `grafin-dataset fetch` first)")
    attempts: list[Attempt] = []
    motif: str | None = None
    begin: str | None = None
    rows: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        found = _BEGIN.match(line)
        if found:
            if begin is not None:
                raise RawInputError(f"{path.name}:{lineno}: BEGIN before the previous attempt ended")
            motif, begin, rows = found.group("motif"), line, []
        elif line.startswith(_END):
            if begin is None or motif is None:
                raise RawInputError(f"{path.name}:{lineno}: END without BEGIN")
            attempts.append(Attempt(len(attempts) + 1, motif, begin, line, tuple(rows)))
            motif, begin = None, None
        else:
            if begin is None:
                raise RawInputError(f"{path.name}:{lineno}: transaction row outside an attempt")
            rows.append(line)
    if begin is not None:
        raise RawInputError(f"{path.name}: the last attempt has no END line")
    return attempts


def match_patterns(attempts: list[Attempt], laundering_rows: pl.DataFrame) -> PatternMatch:
    """``laundering_rows``: the 11 raw text columns plus ``raw_row``, Is Laundering == 1 only.
    Rows match on exact raw line text; duplicates are consumed as a multiset in raw order."""
    keyed = laundering_rows.select(
        pl.concat_str([pl.col(c) for c in TRANS_COLS], separator=",").alias("line"), "raw_row"
    ).sort("raw_row")
    pool: dict[str, list[int]] = defaultdict(list)
    for line, raw_row in keyed.iter_rows():
        pool[line].append(raw_row)
    by_raw_row: dict[int, tuple[int, str]] = {}
    per_attempt: list[tuple[int | None, ...]] = []
    unmatched = 0
    for attempt in attempts:
        matched: list[int | None] = []
        for line in attempt.rows:
            bucket = pool.get(line)
            if bucket:
                raw_row = bucket.pop(0)
                by_raw_row[raw_row] = (attempt.attempt_id, attempt.motif)
                matched.append(raw_row)
            else:
                unmatched += 1
                matched.append(None)
        per_attempt.append(tuple(matched))
    return PatternMatch(by_raw_row, tuple(per_attempt), unmatched)


def build_typologies(laundering_ids: pl.DataFrame, match: PatternMatch) -> pl.DataFrame:
    """``laundering_ids``: raw_row + transaction_id (UInt32) of every laundering row."""
    labels = pl.DataFrame(
        {
            "raw_row": list(match.by_raw_row),
            "attempt_id": [v[0] for v in match.by_raw_row.values()],
            "motif": [v[1] for v in match.by_raw_row.values()],
        },
        schema={"raw_row": pl.UInt32, "attempt_id": pl.Int64, "motif": pl.String},
    )
    return (
        laundering_ids.join(labels, on="raw_row", how="left")
        .with_columns(pl.col("motif").fill_null(UNATTRIBUTED))
        .sort("transaction_id")
        .select("transaction_id", "attempt_id", "motif")
    )


def render_patterns(
    attempts: list[Attempt], match: PatternMatch, localized_lines: dict[int, str]
) -> str:
    """Re-emit Patterns.txt with each matched row replaced by its localized Trans line."""
    out: list[str] = []
    for attempt, raw_rows in zip(attempts, match.rows_per_attempt, strict=True):
        out.append(attempt.begin_line)
        for raw_line, raw_row in zip(attempt.rows, raw_rows, strict=True):
            out.append(localized_lines[raw_row] if raw_row is not None else raw_line)
        out.append(attempt.end_line)
        out.append("")
    return "\n".join(out) + "\n"
