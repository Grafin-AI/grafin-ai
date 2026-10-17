"""Synthetic AML fixture written in both the raw Kaggle format and the localized (ID) format.

6 days, 36 accounts in 3 banks, every transaction at a unique minute (so port numbering has no
time ties), planted laundering: a fan-in on day 1, a cycle on day 3, a fan-out on day 4.
Run directly to materialise it: `uv run python tests/fixture.py <out_dir>`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RAW_HEADER = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,"
    "Amount Paid,Payment Currency,Payment Format,Is Laundering"
)
ID_HEADER = (
    "Timestamp,From Bank,Account,To Bank,To Account,Amount Received,Receiving Currency,"
    "Amount Paid,Payment Currency,Payment Format,Is Laundering"
)
BANKS = (10, 3208, 220)
RAW_BANK = {10: "010", 3208: "03208", 220: "220"}
CURRENCIES = ("US Dollar", "Euro", "Yuan")
FX = {"US Dollar": 16445.0, "Euro": 19154.37, "Yuan": 2303.05}
FORMATS = ("ACH", "Cheque", "Wire", "Credit Card")
CHANNEL = {
    "ACH": "BI-FAST",
    "Cheque": "SKNBI (Cek/BG)",
    "Wire": "RTGS",
    "Credit Card": "Kartu Kredit",
}
RAW_DAY0 = (2022, 9, 1)
ID_DAY0 = (2025, 9, 4)
N_DAYS = 6
NORMAL_PER_DAY = 36


@dataclass(frozen=True)
class Txn:
    minute: int  # minutes since day-0 midnight; unique per transaction
    src: int
    dst: int
    amount: float
    currency: str
    fmt: str
    label: int


def accounts() -> list[tuple[int, str]]:
    return [(BANKS[i % 3], f"8000{i:05X}") for i in range(36)]


def transactions(seed: int = 0) -> list[Txn]:
    rng = np.random.default_rng(seed)
    minutes = rng.permutation(N_DAYS * 1440)
    used = 0
    txns: list[Txn] = []

    def take(day: int) -> int:
        nonlocal used
        while True:
            m = int(minutes[used])
            used += 1
            if m // 1440 == day:
                return m

    for day in range(N_DAYS):
        for _ in range(NORMAL_PER_DAY):
            src, dst = (int(v) for v in rng.integers(0, 30, size=2))
            txns.append(
                Txn(
                    take(day),
                    src,
                    dst,
                    float(rng.integers(100, 50000)) / 100,
                    CURRENCIES[int(rng.integers(0, 3))],
                    FORMATS[int(rng.integers(0, 4))],
                    0,
                )
            )
    for src in range(30, 35):  # fan-in, day 1
        txns.append(Txn(take(1), src, 35, 9000.0 + src, "US Dollar", "ACH", 1))
    for a, b in ((30, 31), (31, 32), (32, 33), (33, 30)):  # cycle, day 3
        txns.append(Txn(take(3), a, b, 5000.0, "Euro", "ACH", 1))
    for dst in range(30, 34):  # fan-out, day 4
        txns.append(Txn(take(4), 35, dst, 2000.0 + dst, "US Dollar", "Wire", 1))
    return txns


def _stamp(day0: tuple[int, int, int], minute: int) -> str:
    base = np.datetime64(f"{day0[0]:04d}-{day0[1]:02d}-{day0[2]:02d}T00:00")
    t = (base + np.timedelta64(minute, "m")).astype(object)
    return t.strftime("%Y/%m/%d %H:%M")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_raw(out: Path, txns: list[Txn]) -> Path:
    """Raw Kaggle format: padded bank strings, original currencies, rows NOT time-sorted."""
    out.mkdir(parents=True, exist_ok=True)
    acc = accounts()
    rng = np.random.default_rng(1)
    lines = [RAW_HEADER]
    for i in rng.permutation(len(txns)):
        t = txns[int(i)]
        (fb, fa), (tb, ta) = acc[t.src], acc[t.dst]
        lines.append(
            f"{_stamp(RAW_DAY0, t.minute)},{RAW_BANK[fb]},{fa},{RAW_BANK[tb]},{ta},"
            f"{t.amount:.2f},{t.currency},{t.amount:.2f},{t.currency},{t.fmt},{t.label}"
        )
    path = out / "HI-Fixture_Trans.csv"
    path.write_text("\n".join(lines) + "\n")
    (out / "SHA256SUMS").write_text(f"{_sha(path)}  {path.name}\n")
    return path


def write_id(out: Path, txns: list[Txn]) -> Path:
    """Localized format: int banks, IDR amounts, Indonesian channels, rows sorted by time."""
    out.mkdir(parents=True, exist_ok=True)
    acc = accounts()
    lines = [ID_HEADER]
    for t in sorted(txns, key=lambda t: t.minute):
        (fb, fa), (tb, ta) = acc[t.src], acc[t.dst]
        idr = round(t.amount * FX[t.currency])
        lines.append(
            f"{_stamp(ID_DAY0, t.minute)},{fb},{fa},{tb},{ta},{idr},IDR,{idr},IDR,"
            f"{CHANNEL[t.fmt]},{t.label}"
        )
    path = out / "HI-Fixture_Trans_sorted.csv"
    path.write_text("\n".join(lines) + "\n")
    manifest = {"dataset": "HI-Fixture", "outputs": {path.name: _sha(path)}}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return path


def write_fixture(root: Path) -> tuple[Path, Path]:
    txns = transactions()
    return write_raw(root / "raw", txns), write_id(root / "id", txns)


if __name__ == "__main__":
    raw, idp = write_fixture(Path(sys.argv[1]))
    print(raw)
    print(idp)
