import os
from datetime import UTC, datetime

from garda_ai_sim.reader import SimTxn, stream_transactions


def _paths():
    d = os.path.join(os.path.dirname(__file__), "data")
    return [os.path.join(d, "trans_sample_part1.csv"), os.path.join(d, "trans_sample_part2.csv")]


def test_streams_all_rows_with_continuous_ordinals():
    rows = list(stream_transactions(_paths()))
    assert [r.ordinal for r in rows] == [1, 2, 3, 4]  # continuous across the two parts
    assert all(isinstance(r, SimTxn) for r in rows)


def test_field_mapping():
    rows = list(stream_transactions(_paths()))
    r2 = rows[1]
    assert r2.fields["from_bank_id"] == "20"
    assert r2.fields["from_account"] == "8000F4580"
    assert r2.fields["to_bank_id"] == "10"
    assert r2.fields["amount_paid"] == "250000.00"
    assert r2.fields["payment_format"] == "Cheque"
    assert r2.fields["is_laundering"] is True
    assert rows[0].fields["is_laundering"] is False
    assert "event_time" not in r2.fields  # stamped by the producer, not the reader


def test_timestamps_parsed_utc():
    rows = list(stream_transactions(_paths()))
    assert rows[2].csv_ts == datetime(2025, 9, 1, 0, 2, tzinfo=UTC)
    assert rows[3].csv_ts == datetime(2025, 9, 1, 0, 1, tzinfo=UTC)  # part2, earlier than part1's last


def test_limit_respected():
    rows = list(stream_transactions(_paths(), limit=2))
    assert [r.ordinal for r in rows] == [1, 2]
