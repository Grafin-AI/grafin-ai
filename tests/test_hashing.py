import hashlib
from pathlib import Path

import pytest

from garda_ai_dataset.hashing import sha256_file, stable_int, weighted_pick


def test_stable_int_is_deterministic_and_part_sensitive() -> None:
    assert stable_int("a", "b") == stable_int("a", "b")
    assert stable_int("a", "b") != stable_int("b", "a")
    assert stable_int("ab") != stable_int("a", "b")  # separator prevents collisions
    assert 0 <= stable_int("x") < 2**64


def test_stable_int_known_value() -> None:
    expected = int.from_bytes(hashlib.sha256("name\x1fE1".encode()).digest()[:8], "big")
    assert stable_int("name", "E1") == expected


def test_weighted_pick_respects_weights() -> None:
    choices = [("a", 1), ("b", 3)]
    assert [weighted_pick(choices, k) for k in range(4)] == ["a", "b", "b", "b"]
    assert weighted_pick(choices, 4) == "a"  # wraps modulo the total weight


def test_weighted_pick_rejects_zero_total() -> None:
    with pytest.raises(ValueError):
        weighted_pick([("a", 0)], 1)


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_bytes(b"hello")
    assert sha256_file(f) == hashlib.sha256(b"hello").hexdigest()
