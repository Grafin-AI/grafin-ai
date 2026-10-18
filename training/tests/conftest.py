from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixture import write_fixture


@pytest.fixture(scope="session")
def fixture_paths(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """(raw CSV, id CSV) of the synthetic fixture, written once per test session."""
    return write_fixture(tmp_path_factory.mktemp("fixture"))
