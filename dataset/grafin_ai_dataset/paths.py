"""Where the raw and localized files of each dataset live under the data root."""

from dataclasses import dataclass
from pathlib import Path

SIZES: dict[str, str] = {"small": "HI-Small", "medium": "HI-Medium"}


@dataclass(frozen=True)
class DatasetPaths:
    name: str
    raw_dir: Path
    out_dir: Path

    @property
    def raw_trans(self) -> Path:
        return self.raw_dir / f"{self.name}_Trans.csv"

    @property
    def raw_accounts(self) -> Path:
        return self.raw_dir / f"{self.name}_accounts.csv"

    @property
    def raw_patterns(self) -> Path:
        return self.raw_dir / f"{self.name}_Patterns.txt"

    @property
    def sha256sums(self) -> Path:
        return self.raw_dir / "SHA256SUMS"

    @property
    def out_trans(self) -> Path:
        return self.out_dir / f"{self.name}_Trans_sorted.csv"

    @property
    def out_accounts(self) -> Path:
        return self.out_dir / f"{self.name}_accounts.csv"

    @property
    def out_entities(self) -> Path:
        return self.out_dir / f"{self.name}_entities.csv"

    @property
    def out_patterns(self) -> Path:
        return self.out_dir / f"{self.name}_Patterns.txt"

    @property
    def out_typologies(self) -> Path:
        return self.out_dir / f"{self.name}_typologies.csv"

    @property
    def manifest(self) -> Path:
        return self.out_dir / "MANIFEST.json"

    @property
    def tmp_dir(self) -> Path:
        return self.out_dir / ".tmp"


def dataset_paths(data_root: Path, size: str) -> DatasetPaths:
    if size not in SIZES:
        raise ValueError(f"unknown dataset size {size!r}; expected one of {sorted(SIZES)}")
    name = SIZES[size]
    return DatasetPaths(name=name, raw_dir=data_root / "raw" / name, out_dir=data_root / f"{name}-ID")
