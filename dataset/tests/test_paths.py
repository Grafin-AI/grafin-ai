from pathlib import Path

import pytest

from grafin_ai_dataset.paths import dataset_paths


def test_dataset_paths_layout(tmp_path: Path) -> None:
    p = dataset_paths(tmp_path, "small")
    assert p.name == "HI-Small"
    assert p.raw_trans == tmp_path / "raw" / "HI-Small" / "HI-Small_Trans.csv"
    assert p.raw_accounts.name == "HI-Small_accounts.csv"
    assert p.raw_patterns.name == "HI-Small_Patterns.txt"
    assert p.sha256sums == tmp_path / "raw" / "HI-Small" / "SHA256SUMS"
    assert p.out_trans == tmp_path / "HI-Small-ID" / "HI-Small_Trans_sorted.csv"
    assert p.out_accounts.name == "HI-Small_accounts.csv"
    assert p.out_entities.name == "HI-Small_entities.csv"
    assert p.out_patterns.name == "HI-Small_Patterns.txt"
    assert p.out_typologies.name == "HI-Small_typologies.csv"
    assert p.manifest == tmp_path / "HI-Small-ID" / "MANIFEST.json"
    assert p.tmp_dir == tmp_path / "HI-Small-ID" / ".tmp"
    assert dataset_paths(tmp_path, "medium").name == "HI-Medium"


def test_unknown_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="large"):
        dataset_paths(tmp_path, "large")
