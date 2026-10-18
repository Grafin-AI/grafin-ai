from datetime import date
from pathlib import Path

import polars as pl
import pytest

from grafin_ai_dataset.errors import MappingError, RawInputError
from grafin_ai_dataset.mappings import Mappings
from grafin_ai_dataset.paths import DatasetPaths
from grafin_ai_dataset.raw import read_raw_accounts, scan_raw_trans
from grafin_ai_dataset.transforms.entities import (
    ACCOUNT_COLUMNS,
    ENTITY_COLUMNS,
    build_accounts,
    build_entities,
    entity_prefix,
    first_seen_by_entity,
    read_legacy_accounts,
)
from grafin_ai_dataset.transforms.transactions import localize_features
from tests.fixture_data import LEGACY_ACCOUNTS

START = date(2025, 9, 4)
BANK_NAMES = {10: "Bank Rakyat Indonesia", 20: "Bank Mandiri", 30: "Bank Central Asia",
              126: "Indodax"}


def test_entity_prefix() -> None:
    assert entity_prefix("Sole Proprietorship #50438") == "Sole Proprietorship"
    assert entity_prefix("Country #1") == "Country"
    with pytest.raises(MappingError, match="Dody Sunyoto"):
        entity_prefix("Dody Sunyoto")


def test_build_entities_on_fixture(raw_paths: DatasetPaths, maps: Mappings) -> None:
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    first_seen = {"E1": START, "E2": date(2025, 9, 5)}
    ents = build_entities(accounts, first_seen, START, maps)
    assert tuple(ents.columns) == ENTITY_COLUMNS
    assert ents["Entity ID"].to_list() == ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]
    types = dict(zip(ents["Entity ID"].to_list(), ents["Entity Type"].to_list(), strict=True))
    assert types == {"E1": "PT", "E2": "Perorangan", "E3": "CV", "E4": "UD",
                     "E5": "Lembaga", "E6": "Lembaga", "E7": "PT"}
    names = dict(zip(ents["Entity ID"].to_list(), ents["Entity Name"].to_list(), strict=True))
    assert names["E1"].startswith("PT ") and names["E3"].startswith("CV ")
    assert names["E4"].startswith("UD ") and names["E5"].startswith("Lembaga ")
    assert not names["E2"].startswith(("PT ", "CV ", "UD ", "Lembaga "))
    for row in ents.iter_rows(named=True):
        assert row["City"] in maps.cities[row["Province"]]
        registered = date.fromisoformat(row["Registration Date"])
        base = first_seen.get(row["Entity ID"], START)
        assert 30 <= (base - registered).days <= 3650
        assert row["KYC Status"] in {status for status, _ in maps.kyc}
    individual_labels = {label for label, _ in maps.sectors["individual"]}
    assert ents.filter(pl.col("Entity ID") == "E2")["Sector"].item() in individual_labels


def test_build_entities_is_deterministic(raw_paths: DatasetPaths, maps: Mappings) -> None:
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    assert build_entities(accounts, {}, START, maps).equals(build_entities(accounts, {}, START, maps))


def test_province_matches_ingest(maps: Mappings) -> None:
    accounts = pl.DataFrame({"Bank Name": ["B #1"], "Bank ID": ["1"], "Account Number": ["X"],
                             "Entity ID": ["80062E240"], "Entity Name": ["Corporation #9"]})
    assert build_entities(accounts, {}, START, maps)["Province"].item() == "DKI Jakarta"


def test_unknown_prefix_raises(maps: Mappings) -> None:
    accounts = pl.DataFrame({"Bank Name": ["B #1"], "Bank ID": ["1"], "Account Number": ["X"],
                             "Entity ID": ["E9"], "Entity Name": ["Alien #1"]})
    with pytest.raises(MappingError, match="Alien"):
        build_entities(accounts, {}, START, maps)


def test_first_seen_uses_both_roles(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans)
    features = localize_features(raw.drop("is_laundering"), maps)
    seen = first_seen_by_entity(features, read_raw_accounts(raw_paths.raw_accounts))
    assert seen["E1"] == date(2025, 9, 4)  # A1 at 00:20 on raw day 1
    assert seen["E6"] == date(2025, 9, 4)  # C2 only as receiver on raw day 1
    assert seen["E5"] == date(2025, 9, 5)  # C1 receives on day 2, sends on day 3
    assert "E7" not in seen  # Z9 never transacts


def test_build_accounts(raw_paths: DatasetPaths, maps: Mappings, tmp_path: Path) -> None:
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    ents = build_entities(accounts, {}, START, maps)
    legacy_path = tmp_path / "legacy.csv"
    legacy_path.write_text(LEGACY_ACCOUNTS)
    out = build_accounts(accounts, BANK_NAMES, ents, read_legacy_accounts(legacy_path))
    assert tuple(out.columns) == ACCOUNT_COLUMNS
    assert out["Account Number"].to_list() == accounts["Account Number"].to_list()
    first = out.row(0, named=True)
    assert (first["Bank Name"], first["Bank ID"], first["risk_category"]) == (
        "Bank Rakyat Indonesia", 10, "Low"
    )
    assert out.filter(pl.col("Account Number") == "Z9")["risk_score"].to_list() == [None]
    e1_name = ents.filter(pl.col("Entity ID") == "E1")["Entity Name"].item()
    assert set(out.filter(pl.col("Entity ID") == "E1")["Entity Name"].to_list()) == {e1_name}


def test_build_accounts_without_legacy(raw_paths: DatasetPaths, maps: Mappings) -> None:
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    out = build_accounts(accounts, BANK_NAMES, build_entities(accounts, {}, START, maps), None)
    assert out["risk_score"].null_count() == out.height
    assert out["risk_category"].null_count() == out.height


def test_legacy_duplicate_keys_rejected(tmp_path: Path) -> None:
    path = tmp_path / "legacy.csv"
    path.write_text(LEGACY_ACCOUNTS + "Old Name,10,A1,E1,Old,2.0,Medium\n")
    with pytest.raises(RawInputError, match="duplicate"):
        read_legacy_accounts(path)
