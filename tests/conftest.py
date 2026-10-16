from pathlib import Path

import pytest

from garda_ai_dataset.mappings import Mappings, load_mappings
from garda_ai_dataset.paths import DatasetPaths
from tests.fixture_data import write_raw


@pytest.fixture
def raw_paths(tmp_path: Path) -> DatasetPaths:
    return write_raw(tmp_path / "data")


@pytest.fixture(scope="session")
def maps() -> Mappings:
    return load_mappings()
