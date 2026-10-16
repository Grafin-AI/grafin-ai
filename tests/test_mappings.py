import shutil
from pathlib import Path

import pytest

from garda_ai_dataset.errors import MappingError
from garda_ai_dataset.geo import PROVINCES
from garda_ai_dataset.mappings import MAPPINGS_DIR, load_mappings

TABLES = {
    "fx_rates.csv",
    "channels.csv",
    "entity_types.csv",
    "institutions.csv",
    "provinces_cities.csv",
    "kyc_status.csv",
    "sectors_occupations.csv",
}


def test_repo_mappings_load() -> None:
    m = load_mappings()
    assert len(m.fx) == 15
    assert m.fx["US Dollar"] == 16445
    assert m.fx["Bitcoin"] == 1820849602
    assert set(m.channels) == {
        "ACH", "Wire", "Cheque", "Credit Card", "Cash", "Reinvestment", "Bitcoin"
    }
    assert m.channels["ACH"] == "BI-FAST"
    assert m.entity_types["Partnership"] == ("CV", "business")
    assert m.entity_types["Individual"] == ("Perorangan", "individual")
    assert set(m.cities) == set(PROVINCES)
    assert sum(1 for i in m.institutions if i.kind == "bank") == 104
    assert sum(1 for i in m.institutions if i.kind == "crypto_exchange") == 10
    assert set(m.hashes) == TABLES


@pytest.fixture
def mapdir(tmp_path: Path) -> Path:
    d = tmp_path / "mappings"
    shutil.copytree(MAPPINGS_DIR, d)
    return d


def test_missing_table(mapdir: Path) -> None:
    (mapdir / "channels.csv").unlink()
    with pytest.raises(MappingError, match="channels.csv"):
        load_mappings(mapdir)


def test_non_positive_weight(mapdir: Path) -> None:
    (mapdir / "kyc_status.csv").write_text("status,weight\nTerverifikasi,0\n")
    with pytest.raises(MappingError, match="positive"):
        load_mappings(mapdir)


def test_duplicate_institution(mapdir: Path) -> None:
    path = mapdir / "institutions.csv"
    first_row = path.read_text().splitlines()[1]
    with path.open("a") as fh:
        fh.write(first_row + "\n")
    with pytest.raises(MappingError, match="duplicate"):
        load_mappings(mapdir)


def test_province_mismatch(mapdir: Path) -> None:
    (mapdir / "provinces_cities.csv").write_text("province,city\nDKI Jakarta,Jakarta Pusat\n")
    with pytest.raises(MappingError, match="provinces"):
        load_mappings(mapdir)


def test_bad_kind(mapdir: Path) -> None:
    (mapdir / "entity_types.csv").write_text("ibm_prefix,entity_type,kind\nCorporation,PT,alien\n")
    with pytest.raises(MappingError, match="alien"):
        load_mappings(mapdir)


def test_comma_in_value_rejected(mapdir: Path) -> None:
    (mapdir / "channels.csv").write_text('ibm_format,channel\nACH,"BI,FAST"\n')
    with pytest.raises(MappingError, match="comma"):
        load_mappings(mapdir)


def test_non_numeric_rate(mapdir: Path) -> None:
    (mapdir / "fx_rates.csv").write_text(
        "currency,iso_code,idr_per_unit,rate_date,source\nUS Dollar,USD,abc,2025-09-04,x\n"
    )
    with pytest.raises(MappingError, match="not a number"):
        load_mappings(mapdir)
