from pathlib import Path

import pytest

import grafin_ai_dataset.localize as localize_mod
from grafin_ai_dataset.cli import default_legacy_accounts, main
from grafin_ai_dataset.paths import DatasetPaths


def _root(paths: DatasetPaths) -> str:
    return str(paths.raw_dir.parent.parent)


@pytest.fixture(autouse=True)
def no_disk_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(localize_mod, "MIN_FREE_BYTES", 0)


def test_localize_then_validate(raw_paths: DatasetPaths, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["localize", "--dataset", "small", "--data-root", _root(raw_paths)]) == 0
    out = capsys.readouterr().out
    assert "PASS  labels" in out
    assert "PASS  manifest" in out
    assert raw_paths.out_trans.exists()
    assert main(["validate", "--dataset", "small", "--data-root", _root(raw_paths)]) == 0


def test_validation_failure_exits_1(raw_paths: DatasetPaths) -> None:
    assert main(["localize", "--dataset", "small", "--data-root", _root(raw_paths)]) == 0
    raw_paths.out_trans.write_text(raw_paths.out_trans.read_text().replace("BI-FAST", "RTGS"))
    assert main(["validate", "--dataset", "small", "--data-root", _root(raw_paths)]) == 1


def test_missing_raw_exits_2(tmp_path: Path) -> None:
    assert main(["localize", "--dataset", "small", "--data-root", str(tmp_path)]) == 2


def test_unknown_currency_exits_3(raw_paths: DatasetPaths) -> None:
    raw_paths.raw_trans.write_text(raw_paths.raw_trans.read_text().replace("Yen", "Doubloon"))
    assert main(["localize", "--dataset", "small", "--data-root", _root(raw_paths)]) == 3


def test_missing_credentials_exits_4(tmp_path: Path) -> None:
    code = main(["fetch", "--dataset", "small", "--data-root", str(tmp_path),
                 "--kaggle-json", str(tmp_path / "none.json")])
    assert code == 4


def test_disk_guard_exits_5(raw_paths: DatasetPaths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(localize_mod, "MIN_FREE_BYTES", 10**18)
    assert main(["localize", "--dataset", "small", "--data-root", _root(raw_paths)]) == 5


def test_default_legacy_accounts(tmp_path: Path) -> None:
    assert default_legacy_accounts(tmp_path, "small") is None
    legacy = tmp_path / "HI-Small" / "HI-Small_accounts.csv"
    legacy.parent.mkdir()
    legacy.write_text("x")
    assert default_legacy_accounts(tmp_path, "small") == legacy
    assert default_legacy_accounts(tmp_path, "medium") is None
