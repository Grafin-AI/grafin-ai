"""Deterministic hashing helpers. All synthetic choices derive from these (spec 6.1)."""

import hashlib
from collections.abc import Sequence
from pathlib import Path


def stable_int(*parts: str) -> int:
    """A 64-bit integer derived from ``parts``; identical on every machine and run."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def weighted_pick(choices: Sequence[tuple[str, int]], key: int) -> str:
    """Pick a value with probability proportional to its integer weight, driven by ``key``."""
    total = sum(weight for _, weight in choices)
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    point = key % total
    for value, weight in choices:
        if point < weight:
            return value
        point -= weight
    raise AssertionError("unreachable: point is always below the total weight")


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
