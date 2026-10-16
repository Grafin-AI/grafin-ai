import polars as pl

from garda_ai_dataset.mappings import Institution, Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import read_raw_accounts
from garda_ai_dataset.transforms.institutions import assign_institutions


def _inst(name: str, kind: str, weight: int) -> Institution:
    return Institution(name=name, short_name=name, kind=kind, group="G", weight=weight)


def _accounts(spec: list[tuple[str, int, int]]) -> pl.DataFrame:
    """spec items: (IBM bank name, bank id, number of accounts)."""
    rows = [
        {
            "Bank Name": name,
            "Bank ID": str(bank_id),
            "Account Number": f"{bank_id}-{k}",
            "Entity ID": f"E{bank_id}-{k}",
            "Entity Name": "Corporation #1",
        }
        for name, bank_id, n in spec
        for k in range(n)
    ]
    return pl.DataFrame(rows)


EXCHANGE = _inst("Ex", "crypto_exchange", 1)


def test_largest_bank_gets_heaviest_institution() -> None:
    accounts = _accounts([("Bank X #1", 1, 50), ("Bank Y #2", 2, 30), ("Bank Z #3", 3, 20)])
    institutions = [
        _inst("Big", "bank", 5), _inst("Mid", "bank", 3), _inst("Small", "bank", 2), EXCHANGE
    ]
    assert assign_institutions(accounts, institutions) == {1: "Big", 2: "Mid", 3: "Small"}


def test_crypto_banks_go_to_exchanges() -> None:
    accounts = _accounts([("Bank X #1", 1, 10), ("Crytpo Bank #5", 5, 3)])
    institutions = [_inst("Bank", "bank", 1), _inst("Indodax", "crypto_exchange", 1)]
    assert assign_institutions(accounts, institutions) == {1: "Bank", 5: "Indodax"}


def test_every_institution_used_and_rank_preserving() -> None:
    accounts = _accounts([(f"Bank #{i}", i, 100 - i) for i in range(1, 21)])
    weights = [50, 30, 10, 5, 5]
    institutions = [_inst(f"I{i}", "bank", w) for i, w in enumerate(weights)] + [EXCHANGE]
    out = assign_institutions(accounts, institutions)
    assert len(out) == 20
    assert set(out.values()) == {"I0", "I1", "I2", "I3", "I4"}
    ranks = [int(out[bank_id][1:]) for bank_id in range(1, 21)]  # banks largest-first
    assert ranks == sorted(ranks)


def test_ties_broken_by_bank_id() -> None:
    accounts = _accounts([("Bank #2", 2, 5), ("Bank #1", 1, 5)])
    institutions = [_inst("A", "bank", 1), _inst("B", "bank", 1), EXCHANGE]
    assert assign_institutions(accounts, institutions) == {1: "A", 2: "B"}


def test_fixture_with_real_tables(raw_paths: DatasetPaths, maps: Mappings) -> None:
    out = assign_institutions(read_raw_accounts(raw_paths.raw_accounts), maps.institutions)
    assert out == {
        10: "Bank Rakyat Indonesia",
        20: "Bank Mandiri",
        30: "Bank Central Asia",
        126: "Indodax",
    }
