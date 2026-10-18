from pathlib import Path

import polars as pl
import pytest

from grafin_ai_dataset.errors import RawInputError
from grafin_ai_dataset.paths import DatasetPaths
from grafin_ai_dataset.raw import TRANS_COLS, scan_raw_trans
from grafin_ai_dataset.transforms.patterns import (
    Attempt,
    build_typologies,
    match_patterns,
    parse_patterns,
    render_patterns,
)
from tests.fixture_data import RAW_ROWS


def _laundering(paths: DatasetPaths) -> pl.DataFrame:
    return scan_raw_trans(paths.raw_trans).filter(pl.col("is_laundering") == "1").collect()


def test_parse_fixture(raw_paths: DatasetPaths) -> None:
    attempts = parse_patterns(raw_paths.raw_patterns)
    assert [(a.attempt_id, a.motif, len(a.rows)) for a in attempts] == [
        (1, "FAN-OUT", 2), (2, "CYCLE", 1)
    ]
    assert attempts[0].rows[0] == RAW_ROWS[3]
    assert attempts[0].begin_line == "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out"
    assert attempts[1].end_line == "END LAUNDERING ATTEMPT - CYCLE"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("2022/09/01 00:00,1,A,1,B,1,US Dollar,1,US Dollar,ACH,1\n", "outside"),
        ("BEGIN LAUNDERING ATTEMPT - CYCLE\nBEGIN LAUNDERING ATTEMPT - CYCLE\n", "BEGIN"),
        ("END LAUNDERING ATTEMPT - CYCLE\n", "END without"),
        ("BEGIN LAUNDERING ATTEMPT - CYCLE\n", "no END"),
    ],
)
def test_parse_malformed(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "p.txt"
    path.write_text(text)
    with pytest.raises(RawInputError, match=message):
        parse_patterns(path)


def test_match_fixture(raw_paths: DatasetPaths) -> None:
    match = match_patterns(parse_patterns(raw_paths.raw_patterns), _laundering(raw_paths))
    assert match.by_raw_row == {3: (1, "FAN-OUT"), 4: (1, "FAN-OUT"), 9: (2, "CYCLE")}
    assert match.rows_per_attempt == ((3, 4), (9,))
    assert match.unmatched == 0


def test_match_is_a_multiset() -> None:
    line = RAW_ROWS[3]
    fields = line.split(",")
    rows = pl.DataFrame([fields, fields], schema=list(TRANS_COLS), orient="row").with_columns(
        pl.Series("raw_row", [8, 5], dtype=pl.UInt32)
    )
    attempt = Attempt(1, "STACK", "BEGIN LAUNDERING ATTEMPT - STACK",
                      "END LAUNDERING ATTEMPT - STACK", (line, line, line))
    match = match_patterns([attempt], rows)
    assert match.rows_per_attempt == ((5, 8, None),)  # consumed in raw order, third unmatched
    assert match.unmatched == 1


def test_build_typologies(raw_paths: DatasetPaths) -> None:
    match = match_patterns(parse_patterns(raw_paths.raw_patterns), _laundering(raw_paths))
    ids = pl.DataFrame(
        {"raw_row": [3, 4, 9, 10], "transaction_id": [2, 3, 9, 11]},
        schema={"raw_row": pl.UInt32, "transaction_id": pl.UInt32},
    )
    assert build_typologies(ids, match).rows() == [
        (2, 1, "FAN-OUT"), (3, 1, "FAN-OUT"), (9, 2, "CYCLE"), (11, None, "UNATTRIBUTED")
    ]


def test_render_round_trips_and_substitutes(raw_paths: DatasetPaths) -> None:
    attempts = parse_patterns(raw_paths.raw_patterns)
    match = match_patterns(attempts, _laundering(raw_paths))
    identity = {3: RAW_ROWS[3], 4: RAW_ROWS[4], 9: RAW_ROWS[9]}
    assert render_patterns(attempts, match, identity) == raw_paths.raw_patterns.read_text()
    assert render_patterns(attempts, match, {3: "L3", 4: "L4", 9: "L9"}) == (
        "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out\nL3\nL4\n"
        "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
        "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 1 hops\nL9\nEND LAUNDERING ATTEMPT - CYCLE\n\n"
    )
