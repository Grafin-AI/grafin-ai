# HI Dataset Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `garda-ai-dataset`. It is a deterministic, validated pipeline that turns IBM's original AMLworld HI-Small and HI-Medium files into an Indonesian-localized dataset that the platform and Multi-GNN can read unchanged.

**Architecture:** The pipeline has four stages: `fetch`, `localize`, `validate` and `all`.
- **Transforms** are pure Polars expressions and functions, driven by versioned mapping CSVs. They never receive the label column.
- **Localize runs in two passes.** Pass 1 streams the raw file through the transforms into a Parquet file. Pass 2 sorts one dataset day at a time and appends it to the output CSV. Memory is therefore bounded on HI-Medium (~32M rows, 16 GB machine).
- **The validator re-derives every invariant independently, also per day.** Every check has a mutation test proving it can fail.

**Tech Stack:** Python 3.12, uv, Polars 2.x, Faker 40.x (`id_ID`), pytest, ruff, mypy `--strict`. Kaggle is reached through its REST API with stdlib `urllib`.

**Spec:** `docs/superpowers/specs/2026-10-16-hi-dataset-localization-design.md` (read it first).

---

## Ground rules for every task

- **Working directory:** `/Users/thariqiskandar/Documents/Career/BI - OJK Hackathon 2025/repositories/garda-ai-dataset`. The path contains spaces, so always quote it.
- **Commits:** the author is already configured in this repo (Thariq Iskandar Zulkarnain M P, thariqiskandar9@gmail.com). End every commit message with:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
- **Never commit data.** `.gitignore` already ignores `*.csv` and `*.txt`, except `mappings/*.csv` and test fixtures. Check `git status` before each commit.
- **Import order:** if `ruff check .` reports only import-order findings (`I001`) in the plan's code, run `uv run ruff check --fix .` and include the reordered files in the same commit. Any other ruff finding is a real defect; fix it by hand.
- **Do not modify any other repository.** That includes `garda-ai-sim`, `garda-ai-ingest`, `garda-ai-deploy`, `garda-ai-backend`, `garda-ai-dashboard-web`, `workspace/*` and `garda-ai-data/HI-Small/`.
- **Verified facts the code relies on** (checked against the real files on 2026-10-16):
  - **IBM Trans header:** `Timestamp,From Bank,Account,To Bank,Account,...`. Both account columns are named `Account`, so columns are read by position.
  - **Bank IDs** in Trans are zero-padded text (`010`, `0010`). Casting them to Int64 merges 0 `(bank, account)` keys on HI-Small. In `accounts.csv`, bank IDs are already unpadded.
  - **Entity name prefixes** on HI-Small: `Partnership`, `Corporation`, `Sole Proprietorship`, `Country`, `Individual`, `Direct`.
  - **Crypto banks** are named `Crytpo Bank #…` (IBM's typo). HI-Small has 943 of them.
  - **Patterns.txt:** 370 attempts, 3,209 rows, every row byte-identical to exactly one Trans line. HI-Small has 5,177 laundering rows.
  - **Polars 2.0.0** behaviour:
    - `round(0)` is half-to-even.
    - `replace_strict` raises `InvalidOperationError` on an unknown key.
    - `scan_csv(..., has_header=False, skip_rows=1, schema=...)` reads every column as text.
    - `join(..., maintain_order="left")` exists.
    - `write_csv()` with no file returns a `str`.

---

## File structure

```
garda-ai-dataset/
├── pyproject.toml, uv.lock, Makefile, README.md, .github/workflows/ci.yml
├── mappings/                     recipe tables (committed)
│   ├── fx_rates.csv  channels.csv  entity_types.csv  institutions.csv
│   ├── provinces_cities.csv  kyc_status.csv  sectors_occupations.csv
├── garda_ai_dataset/
│   ├── __init__.py               __version__
│   ├── errors.py                 exceptions carrying exit codes
│   ├── paths.py                  DatasetPaths: where raw/out files live
│   ├── hashing.py                stable_int, weighted_pick, sha256_file
│   ├── geo.py                    verbatim copy of garda-ai-ingest province logic
│   ├── mappings.py               load + validate mapping tables
│   ├── raw.py                    read IBM files as text, by position
│   ├── transforms/
│   │   ├── __init__.py
│   │   ├── transactions.py       time shift, bank ids, FX, channels, output formatting
│   │   ├── institutions.py       IBM Bank ID -> Indonesian institution
│   │   ├── entities.py           entity type/name/profile, accounts, first-seen
│   │   └── patterns.py           Patterns.txt parse/match, typologies, render
│   ├── localize.py               two-pass orchestration + in-memory variant
│   ├── validate.py               invariants + distribution report
│   ├── fetch.py                  Kaggle per-file download + SHA256SUMS
│   └── cli.py                    garda-dataset entry point
└── tests/
    ├── __init__.py
    ├── fixture_data.py           hand-made raw IBM files (12 txns, 9 accounts, 2 attempts)
    ├── conftest.py               fixtures: raw_paths, maps
    └── test_*.py
```

---

### Task 1: Project scaffold, errors, paths, hashing

**Files:**
- Create: `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `garda_ai_dataset/__init__.py`, `garda_ai_dataset/errors.py`, `garda_ai_dataset/paths.py`, `garda_ai_dataset/hashing.py`, `tests/__init__.py`
- Test: `tests/test_hashing.py`, `tests/test_paths.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "garda-ai-dataset"
version = "0.1.0"
description = "Deterministic Indonesian localization of the IBM AML (AMLworld) HI datasets"
requires-python = ">=3.12,<3.13"
dependencies = [
    "polars>=2.0,<3",
    "faker>=40,<41",
]

[project.scripts]
garda-dataset = "garda_ai_dataset.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "ruff>=0.8",
    "mypy>=1.13",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]

[tool.mypy]
python_version = "3.12"
strict = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["garda_ai_dataset"]
```

- [ ] **Step 2: Create `Makefile`** (recipe lines start with a TAB)

```make
DATASET ?= small
KAGGLE_JSON ?= $(HOME)/.kaggle/kaggle.json

.PHONY: install lint typecheck test check fetch localize validate all

install:
	uv sync

lint:
	uv run ruff check .

typecheck:
	uv run mypy garda_ai_dataset

test:
	uv run pytest -q

check: lint typecheck test

fetch:
	uv run garda-dataset fetch --dataset $(DATASET) --kaggle-json "$(KAGGLE_JSON)"

localize:
	uv run garda-dataset localize --dataset $(DATASET)

validate:
	uv run garda-dataset validate --dataset $(DATASET)

all:
	uv run garda-dataset all --dataset $(DATASET) --kaggle-json "$(KAGGLE_JSON)"
```

- [ ] **Step 3: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: pip install uv
      - name: Sync
        run: uv sync --frozen
      - name: Lint
        run: uv run ruff check .
      - name: Type-check
        run: uv run mypy garda_ai_dataset
      - name: Test
        run: uv run pytest -q
```

- [ ] **Step 4: Create the package skeleton**

`garda_ai_dataset/__init__.py`:

```python
"""Indonesian localization of the IBM AML (AMLworld) HI datasets."""

__version__ = "0.1.0"
```

`garda_ai_dataset/errors.py`:

```python
"""Exceptions carrying the CLI exit code (spec section 10)."""


class DatasetError(Exception):
    exit_code = 1


class ValidationFailed(DatasetError):
    exit_code = 1


class RawInputError(DatasetError):
    exit_code = 2


class MappingError(DatasetError):
    exit_code = 3


class FetchError(DatasetError):
    exit_code = 4


class DiskSpaceError(DatasetError):
    exit_code = 5
```

`tests/__init__.py`: an empty file.

- [ ] **Step 5: Write the failing tests**

`tests/test_hashing.py`:

```python
import hashlib
from pathlib import Path

import pytest

from garda_ai_dataset.hashing import sha256_file, stable_int, weighted_pick


def test_stable_int_is_deterministic_and_part_sensitive() -> None:
    assert stable_int("a", "b") == stable_int("a", "b")
    assert stable_int("a", "b") != stable_int("b", "a")
    assert stable_int("ab") != stable_int("a", "b")  # separator prevents collisions
    assert 0 <= stable_int("x") < 2**64


def test_stable_int_known_value() -> None:
    expected = int.from_bytes(hashlib.sha256("name\x1fE1".encode()).digest()[:8], "big")
    assert stable_int("name", "E1") == expected


def test_weighted_pick_respects_weights() -> None:
    choices = [("a", 1), ("b", 3)]
    assert [weighted_pick(choices, k) for k in range(4)] == ["a", "b", "b", "b"]
    assert weighted_pick(choices, 4) == "a"  # wraps modulo the total weight


def test_weighted_pick_rejects_zero_total() -> None:
    with pytest.raises(ValueError):
        weighted_pick([("a", 0)], 1)


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_bytes(b"hello")
    assert sha256_file(f) == hashlib.sha256(b"hello").hexdigest()
```

`tests/test_paths.py`:

```python
from pathlib import Path

import pytest

from garda_ai_dataset.paths import dataset_paths


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
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `uv sync && uv run pytest -q tests/test_hashing.py tests/test_paths.py`
Expected: an ERROR during collection, `ModuleNotFoundError: No module named 'garda_ai_dataset.hashing'`.

- [ ] **Step 7: Implement `garda_ai_dataset/hashing.py`**

```python
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
```

- [ ] **Step 8: Implement `garda_ai_dataset/paths.py`**

```python
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
```

- [ ] **Step 9: Run the tests and all tooling**

Run: `uv run pytest -q tests/test_hashing.py tests/test_paths.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `7 passed`, then `All checks passed!`, then `Success: no issues found`.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock Makefile .github garda_ai_dataset tests
git commit -m "feat: scaffold garda-ai-dataset with errors, paths and hashing helpers

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Mapping tables, geo, and the mappings loader

**Files:**
- Create: `mappings/fx_rates.csv`, `mappings/channels.csv`, `mappings/entity_types.csv`, `mappings/institutions.csv`, `mappings/provinces_cities.csv`, `mappings/kyc_status.csv`, `mappings/sectors_occupations.csv`
- Create: `garda_ai_dataset/geo.py`, `garda_ai_dataset/mappings.py`
- Test: `tests/test_geo.py`, `tests/test_mappings.py`

- [ ] **Step 1: Create `mappings/fx_rates.csv`** (rates fetched 2026-10-16 for date 2025-09-04)

```csv
currency,iso_code,idr_per_unit,rate_date,source
US Dollar,USD,16445,2025-09-04,ECB reference rate via api.frankfurter.dev
Euro,EUR,19154.37,2025-09-04,ECB reference rate via api.frankfurter.dev
Swiss Franc,CHF,20414,2025-09-04,ECB reference rate via api.frankfurter.dev
Yuan,CNY,2303.05,2025-09-04,ECB reference rate via api.frankfurter.dev
Shekel,ILS,4889.47,2025-09-04,ECB reference rate via api.frankfurter.dev
Rupee,INR,186.63,2025-09-04,ECB reference rate via api.frankfurter.dev
UK Pound,GBP,22110,2025-09-04,ECB reference rate via api.frankfurter.dev
Yen,JPY,110.87,2025-09-04,ECB reference rate via api.frankfurter.dev
Canadian Dollar,CAD,11901,2025-09-04,ECB reference rate via api.frankfurter.dev
Australian Dollar,AUD,10719,2025-09-04,ECB reference rate via api.frankfurter.dev
Mexican Peso,MXN,876.09,2025-09-04,ECB reference rate via api.frankfurter.dev
Brazil Real,BRL,3012.35,2025-09-04,ECB reference rate via api.frankfurter.dev
Ruble,RUB,203.0704,2025-09-04,Central Bank of Russia official rate (49.2440 RUB per 10000 IDR)
Saudi Riyal,SAR,4385.3333,2025-09-04,USD peg 3.75 SAR/USD x ECB USD/IDR 16445
Bitcoin,BTC,1820849602,2025-09-04,Yahoo Finance BTC-USD daily close 110723.60 x ECB USD/IDR 16445
```

- [ ] **Step 2: Create `mappings/channels.csv`**

```csv
ibm_format,channel
ACH,BI-FAST
Wire,RTGS
Cheque,SKNBI (Cek/BG)
Credit Card,Kartu Kredit
Cash,Setor/Tarik Tunai
Reinvestment,Pemindahbukuan
Bitcoin,Aset Kripto
```

- [ ] **Step 3: Create `mappings/entity_types.csv`**

```csv
ibm_prefix,entity_type,kind
Partnership,CV,business
Corporation,PT,business
Sole Proprietorship,UD,business
Country,Lembaga,business
Direct,Lembaga,business
Individual,Perorangan,individual
```

- [ ] **Step 4: Create `mappings/institutions.csv`**

It has 104 banks and 10 crypto exchanges. Weights are integers approximating the share of accounts; they are an assumption (spec 6.3).

```csv
name,short_name,kind,group,weight
Bank Rakyat Indonesia,BRI,bank,BUMN,140
Bank Mandiri,Mandiri,bank,BUMN,130
Bank Central Asia,BCA,bank,Swasta Nasional,110
Bank Negara Indonesia,BNI,bank,BUMN,70
Bank Tabungan Negara,BTN,bank,BUMN,35
Bank Syariah Indonesia,BSI,bank,Syariah,30
CIMB Niaga,CIMB Niaga,bank,KCBA/Campuran,25
Bank Danamon,Danamon,bank,KCBA/Campuran,18
Bank Permata,Permata,bank,KCBA/Campuran,18
Bank OCBC Indonesia,OCBC,bank,KCBA/Campuran,18
SMBC Indonesia,SMBC,bank,KCBA/Campuran,15
Panin Bank,Panin,bank,Swasta Nasional,15
Maybank Indonesia,Maybank,bank,KCBA/Campuran,14
Bank BJB,BJB,bank,BPD,12
Bank Mega,Mega,bank,Swasta Nasional,10
Bank UOB Indonesia,UOB,bank,KCBA/Campuran,10
Bank DKI,Bank DKI,bank,BPD,9
Bank Jago,Jago,bank,Bank Digital,8
KB Bank,KB Bank,bank,KCBA/Campuran,8
Bank Jateng,Bank Jateng,bank,BPD,7
Bank Jatim,Bank Jatim,bank,BPD,7
HSBC Indonesia,HSBC,bank,KCBA/Campuran,6
SeaBank Indonesia,SeaBank,bank,Bank Digital,6
Bank Sinarmas,Sinarmas,bank,Swasta Nasional,6
Bank Mayapada,Mayapada,bank,Swasta Nasional,6
Bank DBS Indonesia,DBS,bank,KCBA/Campuran,5
MUFG Bank Jakarta,MUFG,bank,KCBA/Campuran,5
Bank Muamalat,Muamalat,bank,Syariah,4
Allo Bank,Allo Bank,bank,Bank Digital,4
blu by BCA Digital,blu,bank,Bank Digital,4
Bank Neo Commerce,BNC,bank,Bank Digital,4
Standard Chartered Indonesia,StanChart,bank,KCBA/Campuran,4
Citibank Indonesia,Citi,bank,KCBA/Campuran,4
Bank Woori Saudara,Woori Saudara,bank,KCBA/Campuran,4
Bank KEB Hana Indonesia,KEB Hana,bank,KCBA/Campuran,4
Bank Sumut,Bank Sumut,bank,BPD,3
Bank Nagari,Bank Nagari,bank,BPD,3
Bank Sumsel Babel,Sumsel Babel,bank,BPD,3
Bank BPD Bali,BPD Bali,bank,BPD,3
Bankaltimtara,Bankaltimtara,bank,BPD,3
Bank Raya,Bank Raya,bank,Bank Digital,3
Superbank,Superbank,bank,Bank Digital,3
BTPN Syariah,BTPN Syariah,bank,Syariah,3
Bank Nationalnobu,Nobu,bank,Swasta Nasional,3
Bank Shinhan Indonesia,Shinhan,bank,KCBA/Campuran,3
Bank ICBC Indonesia,ICBC,bank,KCBA/Campuran,3
Bank Mizuho Indonesia,Mizuho,bank,KCBA/Campuran,3
Bank Mandiri Taspen,Mantap,bank,Swasta Nasional,2
Bank Sulselbar,Sulselbar,bank,BPD,2
Bank Kalbar,Bank Kalbar,bank,BPD,2
Bank Kalsel,Bank Kalsel,bank,BPD,2
Bank Papua,Bank Papua,bank,BPD,2
Bank BPD DIY,BPD DIY,bank,BPD,2
Bank Aceh Syariah,Bank Aceh,bank,Syariah,2
Bank Resona Perdania,Resona,bank,KCBA/Campuran,2
Bank Capital Indonesia,Capital,bank,Swasta Nasional,2
Bank QNB Indonesia,QNB,bank,KCBA/Campuran,2
Bank China Construction Bank Indonesia,CCB Indonesia,bank,KCBA/Campuran,2
Bank of China Jakarta,BOC,bank,KCBA/Campuran,2
Bank Artha Graha,Artha Graha,bank,Swasta Nasional,2
Bank MNC Internasional,MNC Bank,bank,Swasta Nasional,2
Bank Commonwealth,Commonwealth,bank,KCBA/Campuran,2
Bank NTT,Bank NTT,bank,BPD,1
Bank NTB Syariah,NTB Syariah,bank,Syariah,1
Bank SulutGo,SulutGo,bank,BPD,1
Bank Kalteng,Bank Kalteng,bank,BPD,1
Bank Jambi,Bank Jambi,bank,BPD,1
Bank Lampung,Bank Lampung,bank,BPD,1
Bank Bengkulu,Bank Bengkulu,bank,BPD,1
Bank Banten,Bank Banten,bank,BPD,1
Bank Sultra,Bank Sultra,bank,BPD,1
Bank Sulteng,Bank Sulteng,bank,BPD,1
Bank Maluku Malut,Maluku Malut,bank,BPD,1
Bank Riau Kepri Syariah,BRK Syariah,bank,Syariah,1
Bank BJB Syariah,BJB Syariah,bank,Syariah,1
BCA Syariah,BCA Syariah,bank,Syariah,1
Bank Mega Syariah,Mega Syariah,bank,Syariah,1
Bank Panin Dubai Syariah,Panin Dubai Syariah,bank,Syariah,1
Bank Victoria Syariah,Victoria Syariah,bank,Syariah,1
KB Bank Syariah,KB Syariah,bank,Syariah,1
Bank Nano Syariah,Nano Syariah,bank,Syariah,1
Bank Aladin Syariah,Aladin,bank,Bank Digital,1
Krom Bank Indonesia,Krom,bank,Bank Digital,1
Hibank,Hibank,bank,Bank Digital,1
Bank Amar Indonesia,Amar Bank,bank,Bank Digital,1
Bank Victoria International,Victoria,bank,Swasta Nasional,1
Bank Index Selindo,Index,bank,Swasta Nasional,1
Bank Ganesha,Ganesha,bank,Swasta Nasional,1
Bank Maspion,Maspion,bank,Swasta Nasional,1
Bank Multiarta Sentosa,MAS,bank,Swasta Nasional,1
Bank Oke Indonesia,Bank Oke,bank,Swasta Nasional,1
Bank Ina Perdana,Bank Ina,bank,Swasta Nasional,1
Bank Mestika Dharma,Mestika,bank,Swasta Nasional,1
Bank Sahabat Sampoerna,Sampoerna,bank,Swasta Nasional,1
Bank Jasa Jakarta,Jasa Jakarta,bank,Swasta Nasional,1
Bank Fama Internasional,Fama,bank,Swasta Nasional,1
Bank Mayora,Mayora,bank,Swasta Nasional,1
Bank JTrust Indonesia,JTrust,bank,KCBA/Campuran,1
Bank CTBC Indonesia,CTBC,bank,KCBA/Campuran,1
Bank IBK Indonesia,IBK,bank,KCBA/Campuran,1
BNP Paribas Indonesia,BNP Paribas,bank,KCBA/Campuran,1
Deutsche Bank Jakarta,Deutsche Bank,bank,KCBA/Campuran,1
JPMorgan Chase Bank Jakarta,JPMorgan,bank,KCBA/Campuran,1
Bank of America Jakarta,BofA,bank,KCBA/Campuran,1
Indodax,Indodax,crypto_exchange,Pedagang Aset Kripto,35
Tokocrypto,Tokocrypto,crypto_exchange,Pedagang Aset Kripto,15
Pintu,Pintu,crypto_exchange,Pedagang Aset Kripto,15
Reku,Reku,crypto_exchange,Pedagang Aset Kripto,8
Ajaib Kripto,Ajaib,crypto_exchange,Pedagang Aset Kripto,8
Pluang,Pluang,crypto_exchange,Pedagang Aset Kripto,6
Triv,Triv,crypto_exchange,Pedagang Aset Kripto,4
Upbit Indonesia,Upbit,crypto_exchange,Pedagang Aset Kripto,4
Nanovest,Nanovest,crypto_exchange,Pedagang Aset Kripto,3
Mobee,Mobee,crypto_exchange,Pedagang Aset Kripto,2
```

- [ ] **Step 5: Create `mappings/provinces_cities.csv`**

The provinces must equal `garda-ai-ingest`'s 15 provinces exactly.

```csv
province,city
DKI Jakarta,Jakarta Pusat
DKI Jakarta,Jakarta Selatan
DKI Jakarta,Jakarta Barat
DKI Jakarta,Jakarta Timur
DKI Jakarta,Jakarta Utara
Jawa Barat,Bandung
Jawa Barat,Bekasi
Jawa Barat,Bogor
Jawa Barat,Depok
Jawa Barat,Cirebon
Jawa Timur,Surabaya
Jawa Timur,Malang
Jawa Timur,Sidoarjo
Jawa Timur,Kediri
Jawa Tengah,Semarang
Jawa Tengah,Surakarta
Jawa Tengah,Pekalongan
Jawa Tengah,Tegal
Sumatera Utara,Medan
Sumatera Utara,Binjai
Sumatera Utara,Pematangsiantar
Banten,Tangerang
Banten,Tangerang Selatan
Banten,Serang
Banten,Cilegon
Bali,Denpasar
Bali,Badung
Bali,Gianyar
Sulawesi Selatan,Makassar
Sulawesi Selatan,Parepare
Sulawesi Selatan,Palopo
Sumatera Selatan,Palembang
Sumatera Selatan,Lubuklinggau
Sumatera Selatan,Prabumulih
Riau,Pekanbaru
Riau,Dumai
Kalimantan Timur,Samarinda
Kalimantan Timur,Balikpapan
Kalimantan Timur,Bontang
Lampung,Bandar Lampung
Lampung,Metro
Yogyakarta,Yogyakarta
Yogyakarta,Sleman
Yogyakarta,Bantul
Sumatera Barat,Padang
Sumatera Barat,Bukittinggi
Kalimantan Barat,Pontianak
Kalimantan Barat,Singkawang
```

- [ ] **Step 6: Create `mappings/kyc_status.csv` and `mappings/sectors_occupations.csv`**

The weights in both files are assumptions (spec 6.4).

`mappings/kyc_status.csv`:

```csv
status,weight
Terverifikasi,85
Perlu Pembaruan,12
Dalam Review,3
```

`mappings/sectors_occupations.csv`:

```csv
applies_to,label,weight
individual,Karyawan Swasta,30
individual,Wiraswasta,20
individual,Ibu Rumah Tangga,12
individual,Pelajar/Mahasiswa,10
individual,Pegawai Negeri Sipil,8
individual,Petani/Nelayan,6
individual,Profesional,6
individual,Pensiunan,4
individual,TNI/Polri,2
individual,Lainnya,2
business,Perdagangan Besar dan Eceran,25
business,Industri Pengolahan,12
business,Jasa Lainnya,12
business,Penyediaan Akomodasi dan Makan Minum,10
business,Konstruksi,9
business,Pertanian Kehutanan dan Perikanan,8
business,Transportasi dan Pergudangan,7
business,Jasa Keuangan dan Asuransi,6
business,Informasi dan Komunikasi,6
business,Real Estat,5
```

- [ ] **Step 7: Write the failing tests**

`tests/test_geo.py`:

```python
from garda_ai_dataset.geo import PROVINCES, province_for_entity


def test_matches_garda_ai_ingest_known_values() -> None:
    # Values produced by garda-ai-ingest/garda_ai_ingest/geo.py on 2026-10-16.
    assert province_for_entity("80062E240") == "DKI Jakarta"
    assert province_for_entity("800C998A0") == "Jawa Tengah"
    assert province_for_entity("800C47F50") == "Jawa Tengah"
    assert province_for_entity("800FE9980") == "Sumatera Utara"


def test_fifteen_provinces() -> None:
    assert len(PROVINCES) == 15
```

`tests/test_mappings.py`:

```python
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
```

- [ ] **Step 8: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_geo.py tests/test_mappings.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.geo'`.

- [ ] **Step 9: Implement `garda_ai_dataset/geo.py`**

```python
"""Province assignment: a VERBATIM copy of garda-ai-ingest/garda_ai_ingest/geo.py.

The platform already shows this province (ingest computes it at seed time), so
entities.csv must produce the identical value for every Entity ID. Change both repos
together or not at all.
"""

import hashlib

PROVINCES = [
    "DKI Jakarta", "Jawa Barat", "Jawa Timur", "Jawa Tengah", "Sumatera Utara",
    "Banten", "Bali", "Sulawesi Selatan", "Sumatera Selatan", "Riau",
    "Kalimantan Timur", "Lampung", "Yogyakarta", "Sumatera Barat", "Kalimantan Barat",
]

_WEIGHTS = [12, 9, 8, 7, 6, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1]
_BUCKET = [p for p, w in zip(PROVINCES, _WEIGHTS, strict=True) for _ in range(w)]


def province_for_entity(entity_id: str) -> str:
    """Stable, seeded province assignment from a hash of the entity id (synthetic)."""
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()
    return _BUCKET[int(digest, 16) % len(_BUCKET)]
```

- [ ] **Step 10: Implement `garda_ai_dataset/mappings.py`**

```python
"""Load and validate the versioned mapping tables in ``mappings/`` (the localization recipe)."""

import csv
from dataclasses import dataclass
from pathlib import Path

from garda_ai_dataset.errors import MappingError
from garda_ai_dataset.geo import PROVINCES
from garda_ai_dataset.hashing import sha256_file

MAPPINGS_DIR = Path(__file__).resolve().parent.parent / "mappings"
INSTITUTION_KINDS = ("bank", "crypto_exchange")
ENTITY_KINDS = ("individual", "business")


@dataclass(frozen=True)
class Institution:
    name: str
    short_name: str
    kind: str
    group: str
    weight: int


@dataclass(frozen=True)
class Mappings:
    fx: dict[str, float]  # IBM currency name -> IDR per unit
    channels: dict[str, str]  # IBM payment format -> Indonesian channel
    entity_types: dict[str, tuple[str, str]]  # IBM prefix -> (entity type, kind)
    institutions: tuple[Institution, ...]
    cities: dict[str, tuple[str, ...]]  # province -> cities
    kyc: tuple[tuple[str, int], ...]
    sectors: dict[str, tuple[tuple[str, int], ...]]  # kind -> weighted labels
    hashes: dict[str, str]  # table file name -> sha256


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise MappingError(f"mapping table missing: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise MappingError(f"{path.name}: missing columns {missing}")
        rows = list(reader)
    if not rows:
        raise MappingError(f"{path.name}: has no rows")
    cleaned: list[dict[str, str]] = []
    for line, row in enumerate(rows, start=2):
        values: dict[str, str] = {}
        for column in columns:
            value = (row.get(column) or "").strip()
            if not value:
                raise MappingError(f"{path.name}:{line}: empty value for {column!r}")
            if "," in value:
                raise MappingError(f"{path.name}:{line}: comma in {column!r} value {value!r}")
            values[column] = value
        cleaned.append(values)
    return cleaned


def _positive_int(path: Path, line: int, value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise MappingError(f"{path.name}:{line}: weight {value!r} is not an integer") from None
    if number <= 0:
        raise MappingError(f"{path.name}:{line}: weight must be positive, got {number}")
    return number


def _unique(path: Path, values: list[str], what: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MappingError(f"{path.name}: duplicate {what} {value!r}")
        seen.add(value)


def _choice(path: Path, line: int, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise MappingError(f"{path.name}:{line}: {value!r} is not one of {allowed}")
    return value


def _load_fx(path: Path) -> dict[str, float]:
    rows = _read(path, ("currency", "iso_code", "idr_per_unit", "rate_date", "source"))
    _unique(path, [r["currency"] for r in rows], "currency")
    fx: dict[str, float] = {}
    for line, row in enumerate(rows, start=2):
        try:
            rate = float(row["idr_per_unit"])
        except ValueError:
            raise MappingError(
                f"{path.name}:{line}: rate {row['idr_per_unit']!r} is not a number"
            ) from None
        if rate <= 0:
            raise MappingError(f"{path.name}:{line}: rate must be positive")
        fx[row["currency"]] = rate
    return fx


def _load_institutions(path: Path) -> tuple[Institution, ...]:
    rows = _read(path, ("name", "short_name", "kind", "group", "weight"))
    _unique(path, [r["name"] for r in rows], "institution name")
    institutions = tuple(
        Institution(
            name=r["name"],
            short_name=r["short_name"],
            kind=_choice(path, line, r["kind"], INSTITUTION_KINDS),
            group=r["group"],
            weight=_positive_int(path, line, r["weight"]),
        )
        for line, r in enumerate(rows, start=2)
    )
    for kind in INSTITUTION_KINDS:
        if not any(i.kind == kind for i in institutions):
            raise MappingError(f"{path.name}: needs at least one {kind!r} row")
    return institutions


def _load_cities(path: Path) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for row in _read(path, ("province", "city")):
        grouped.setdefault(row["province"], []).append(row["city"])
    if set(grouped) != set(PROVINCES):
        raise MappingError(
            f"{path.name}: provinces must equal geo.PROVINCES; "
            f"missing {sorted(set(PROVINCES) - set(grouped))}, "
            f"unknown {sorted(set(grouped) - set(PROVINCES))}"
        )
    return {province: tuple(cities) for province, cities in grouped.items()}


def _load_sectors(path: Path) -> dict[str, tuple[tuple[str, int], ...]]:
    grouped: dict[str, list[tuple[str, int]]] = {kind: [] for kind in ENTITY_KINDS}
    for line, row in enumerate(_read(path, ("applies_to", "label", "weight")), start=2):
        kind = _choice(path, line, row["applies_to"], ENTITY_KINDS)
        grouped[kind].append((row["label"], _positive_int(path, line, row["weight"])))
    for kind, items in grouped.items():
        if not items:
            raise MappingError(f"{path.name}: needs at least one {kind!r} row")
    return {kind: tuple(items) for kind, items in grouped.items()}


def load_mappings(directory: Path = MAPPINGS_DIR) -> Mappings:
    fx_path = directory / "fx_rates.csv"
    channels_path = directory / "channels.csv"
    types_path = directory / "entity_types.csv"
    institutions_path = directory / "institutions.csv"
    cities_path = directory / "provinces_cities.csv"
    kyc_path = directory / "kyc_status.csv"
    sectors_path = directory / "sectors_occupations.csv"

    fx = _load_fx(fx_path)

    channel_rows = _read(channels_path, ("ibm_format", "channel"))
    _unique(channels_path, [r["ibm_format"] for r in channel_rows], "ibm_format")
    channels = {r["ibm_format"]: r["channel"] for r in channel_rows}

    type_rows = _read(types_path, ("ibm_prefix", "entity_type", "kind"))
    _unique(types_path, [r["ibm_prefix"] for r in type_rows], "ibm_prefix")
    entity_types = {
        r["ibm_prefix"]: (r["entity_type"], _choice(types_path, line, r["kind"], ENTITY_KINDS))
        for line, r in enumerate(type_rows, start=2)
    }

    kyc_rows = _read(kyc_path, ("status", "weight"))
    _unique(kyc_path, [r["status"] for r in kyc_rows], "status")
    kyc = tuple(
        (r["status"], _positive_int(kyc_path, line, r["weight"]))
        for line, r in enumerate(kyc_rows, start=2)
    )

    files = (fx_path, channels_path, types_path, institutions_path, cities_path, kyc_path,
             sectors_path)
    return Mappings(
        fx=fx,
        channels=channels,
        entity_types=entity_types,
        institutions=_load_institutions(institutions_path),
        cities=_load_cities(cities_path),
        kyc=kyc,
        sectors=_load_sectors(sectors_path),
        hashes={f.name: sha256_file(f) for f in files},
    )
```

- [ ] **Step 11: Run the tests and tooling**

Run: `uv run pytest -q tests/test_geo.py tests/test_mappings.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `10 passed`, then ruff and mypy clean.

- [ ] **Step 12: Commit**

```bash
git add mappings garda_ai_dataset/geo.py garda_ai_dataset/mappings.py tests/test_geo.py tests/test_mappings.py
git status --short   # only these files; no data
git commit -m "feat: mapping tables (FX, channels, institutions, entity types, profiles) and loader

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Raw readers, transaction transforms, and the test fixture

**Files:**
- Create: `garda_ai_dataset/raw.py`, `garda_ai_dataset/transforms/__init__.py`, `garda_ai_dataset/transforms/transactions.py`
- Create: `tests/fixture_data.py`, `tests/conftest.py`
- Test: `tests/test_transactions.py`

- [ ] **Step 1: Create the fixture `tests/fixture_data.py`**

```python
"""A tiny hand-made IBM dataset that exercises every edge case the spec names.

Raw rows are deliberately unsorted. They include:
- same-minute ties (rows 1 and 2; rows 6 and 7);
- a zero-padded bank spelling ("0010", only ever used with account A3, so no node merges);
- an account number under two banks (DUP at 10 and at 20);
- a cross-currency row (5);
- two identical rows (6 and 7);
- every IBM payment format;
- 4 laundering rows: 3 in Patterns.txt and 1 unattributed (row 10).
"""

from pathlib import Path

from garda_ai_dataset.paths import DatasetPaths, dataset_paths

RAW_HEADER = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,"
    "Amount Paid,Payment Currency,Payment Format,Is Laundering"
)
RAW_ROWS = [
    "2022/09/02 10:00,010,A1,020,B1,100.00,US Dollar,100.00,US Dollar,ACH,0",
    "2022/09/01 09:30,020,B1,010,A2,250.50,Euro,250.50,Euro,Wire,0",
    "2022/09/01 09:30,0010,A3,020,DUP,1000.00,Yen,1000.00,Yen,Cheque,0",
    "2022/09/01 08:00,010,DUP,030,C2,0.5,Bitcoin,0.5,Bitcoin,Bitcoin,1",
    "2022/09/01 08:05,010,DUP,020,B1,0.25,Bitcoin,0.25,Bitcoin,Bitcoin,1",
    "2022/09/03 23:59,126,C1,010,A1,75.00,US Dollar,70.00,Euro,Credit Card,0",
    "2022/09/02 12:00,020,DUP,010,A2,500.00,US Dollar,500.00,US Dollar,Cash,0",
    "2022/09/02 12:00,020,DUP,010,A2,500.00,US Dollar,500.00,US Dollar,Cash,0",
    "2022/09/03 01:00,030,C2,030,C2,42.42,US Dollar,42.42,US Dollar,Reinvestment,0",
    "2022/09/02 18:45,010,A2,126,C1,3000.00,US Dollar,3000.00,US Dollar,ACH,1",
    "2022/09/03 02:00,020,B1,030,C2,9999.99,Euro,9999.99,Euro,ACH,1",
    "2022/09/01 00:20,010,A1,010,A1,3697.34,US Dollar,3697.34,US Dollar,Reinvestment,0",
]
# Sorted by (timestamp, raw_row): raw row -> the 1-based transaction_id it must receive.
EXPECTED_TID = {11: 1, 3: 2, 4: 3, 1: 4, 2: 5, 0: 6, 6: 7, 7: 8, 9: 9, 8: 10, 10: 11, 5: 12}

RAW_ACCOUNTS = """Bank Name,Bank ID,Account Number,Entity ID,Entity Name
Bank A #1,10,A1,E1,Corporation #1
Bank A #1,10,A2,E1,Corporation #1
Bank A #1,10,A3,E1,Corporation #1
Bank B #2,20,B1,E2,Individual #1
Bank A #1,10,DUP,E3,Partnership #1
Bank B #2,20,DUP,E4,Sole Proprietorship #1
Crytpo Bank #5,126,C1,E5,Country #1
Bank C #3,30,C2,E6,Direct #1
Bank C #3,30,Z9,E7,Corporation #2
"""

RAW_PATTERNS = (
    "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out\n"
    f"{RAW_ROWS[3]}\n{RAW_ROWS[4]}\n"
    "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
    "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 1 hops\n"
    f"{RAW_ROWS[9]}\n"
    "END LAUNDERING ATTEMPT - CYCLE\n\n"
)

LEGACY_ACCOUNTS = """Bank Name,Bank ID,Account Number,Entity ID,Entity Name,risk_score,risk_category
Old Name,10,A1,E1,Old,1.0,Low
Old Name,20,B1,E2,Old,69.44,High
"""


def write_raw(data_root: Path) -> DatasetPaths:
    paths = dataset_paths(data_root, "small")
    paths.raw_dir.mkdir(parents=True)
    paths.raw_trans.write_text(RAW_HEADER + "\n" + "\n".join(RAW_ROWS) + "\n", encoding="utf-8")
    paths.raw_accounts.write_text(RAW_ACCOUNTS, encoding="utf-8")
    paths.raw_patterns.write_text(RAW_PATTERNS, encoding="utf-8")
    return paths
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Write the failing tests in `tests/test_transactions.py`**

```python
import datetime as dt
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import polars as pl
import pytest

from garda_ai_dataset.errors import MappingError, RawInputError
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from garda_ai_dataset.transforms.transactions import (
    OFFSET_DAYS,
    check_vocabulary,
    format_output,
    localize_features,
)


def _idr(amount: str, rate: str) -> int:
    return int((Decimal(amount) * Decimal(rate)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def test_scan_reads_text_by_position(raw_paths: DatasetPaths) -> None:
    df = scan_raw_trans(raw_paths.raw_trans).collect()
    assert df.height == 12
    assert df.columns[0] == "raw_row"
    row = df.row(2, named=True)
    assert row["from_bank"] == "0010"  # kept verbatim as text
    assert row["to_account"] == "DUP"  # second "Account" column read by position


def test_localize_features(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans)
    out = localize_features(raw.drop("is_laundering"), maps).collect().sort("raw_row")
    r0 = out.row(0, named=True)
    assert r0["ts"] == dt.datetime(2025, 9, 5, 10, 0)
    assert (r0["from_bank"], r0["to_bank"]) == (10, 20)
    assert r0["amount_paid"] == _idr("100.00", "16445")
    assert out.row(1, named=True)["amount_paid"] == _idr("250.50", "19154.37")
    assert out.row(2, named=True)["from_bank"] == 10  # "0010" -> 10
    assert out.row(2, named=True)["amount_paid"] == _idr("1000.00", "110.87")
    assert out.row(3, named=True)["amount_paid"] == _idr("0.5", "1820849602")
    r5 = out.row(5, named=True)  # cross-currency: received USD, paid EUR
    assert r5["amount_received"] == _idr("75.00", "16445")
    assert r5["amount_paid"] == _idr("70.00", "19154.37")
    assert out["payment_format"].to_list() == [
        "BI-FAST", "RTGS", "SKNBI (Cek/BG)", "Aset Kripto", "Aset Kripto", "Kartu Kredit",
        "Setor/Tarik Tunai", "Setor/Tarik Tunai", "Pemindahbukuan", "BI-FAST", "BI-FAST",
        "Pemindahbukuan",
    ]


def test_localize_features_refuses_the_label(raw_paths: DatasetPaths, maps: Mappings) -> None:
    with pytest.raises(ValueError, match="label"):
        localize_features(scan_raw_trans(raw_paths.raw_trans), maps)


def test_offset_is_whole_weeks() -> None:
    start = dt.date(2022, 9, 1)
    shifted = start + dt.timedelta(days=OFFSET_DAYS)
    assert OFFSET_DAYS == 1099
    assert shifted == dt.date(2025, 9, 4)
    assert shifted.weekday() == start.weekday()


def test_format_output(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans)
    labels = raw.select("raw_row", pl.col("is_laundering").cast(pl.Int8))
    staged = (
        localize_features(raw.drop("is_laundering"), maps)
        .join(labels, on="raw_row")
        .collect()
        .sort("raw_row")
    )
    out = format_output(staged)
    assert tuple(out.columns) == OUT_HEADER
    amount = _idr("100.00", "16445")
    assert out.head(1).write_csv(include_header=False).strip() == (
        f"2025/09/05 10:00,10,A1,20,B1,{amount},IDR,{amount},IDR,BI-FAST,0"
    )


def test_check_vocabulary_ok(raw_paths: DatasetPaths, maps: Mappings) -> None:
    check_vocabulary(scan_raw_trans(raw_paths.raw_trans), maps)


def test_check_vocabulary_names_unknown_values(raw_paths: DatasetPaths, maps: Mappings) -> None:
    text = raw_paths.raw_trans.read_text().replace("Yen", "Doubloon").replace("Cheque", "Barter")
    raw_paths.raw_trans.write_text(text)
    with pytest.raises(MappingError, match="Doubloon") as exc:
        check_vocabulary(scan_raw_trans(raw_paths.raw_trans), maps)
    assert "Barter" in str(exc.value)


def test_missing_raw_file(tmp_path: Path) -> None:
    with pytest.raises(RawInputError):
        scan_raw_trans(tmp_path / "nope.csv")


def test_accounts_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "accounts.csv"
    path.write_text("Bank ID,Account Number\n1,A\n")
    with pytest.raises(RawInputError, match="Entity ID"):
        read_raw_accounts(path)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_transactions.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.raw'`.

- [ ] **Step 5: Implement `garda_ai_dataset/raw.py`**

```python
"""Readers for IBM-format files. Everything is read as text, and Trans columns by position."""

from pathlib import Path

import polars as pl

from garda_ai_dataset.errors import RawInputError

TRANS_COLS = (
    "timestamp",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_received",
    "receiving_currency",
    "amount_paid",
    "payment_currency",
    "payment_format",
    "is_laundering",
)
# IBM's header names BOTH account columns "Account". We read by position and write
# "To Account" for the second, which is what garda-ai-sim reads.
OUT_HEADER = (
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "To Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
)
ACCOUNT_COLS = ("Bank Name", "Bank ID", "Account Number", "Entity ID", "Entity Name")


def _require(path: Path) -> None:
    if not path.exists():
        raise RawInputError(f"input missing: {path} (run `garda-dataset fetch` first)")


def scan_trans_csv(path: Path) -> pl.LazyFrame:
    """Any IBM-layout Trans CSV (raw or localized) as 11 text columns named TRANS_COLS."""
    _require(path)
    schema = pl.Schema({c: pl.String for c in TRANS_COLS})
    return pl.scan_csv(path, has_header=False, skip_rows=1, schema=schema)


def scan_raw_trans(path: Path) -> pl.LazyFrame:
    """The raw Trans file plus ``raw_row``: the 0-based position in the original file."""
    return scan_trans_csv(path).with_row_index("raw_row")


def read_raw_accounts(path: Path) -> pl.DataFrame:
    _require(path)
    df = pl.read_csv(path, infer_schema=False)
    missing = [c for c in ACCOUNT_COLS if c not in df.columns]
    if missing:
        raise RawInputError(f"{path.name}: missing columns {missing}")
    return df.select(ACCOUNT_COLS)
```

- [ ] **Step 6: Implement `garda_ai_dataset/transforms/__init__.py` and `transforms/transactions.py`**

`garda_ai_dataset/transforms/__init__.py`:

```python
"""Pure transforms. None of them may read the Is Laundering label (spec 6.1)."""
```

`garda_ai_dataset/transforms/transactions.py`:

```python
"""Row-level transforms: time shift, bank ids, FX to IDR, channel names (spec 6.2)."""

import polars as pl

from garda_ai_dataset.errors import MappingError
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.raw import OUT_HEADER

OFFSET_DAYS = 1099  # 157 whole weeks: 2022-09-01 (Thu) -> 2025-09-04 (Thu)
TS_FORMAT = "%Y/%m/%d %H:%M"


def parse_ts(column: str, *, strict: bool = True) -> pl.Expr:
    return pl.col(column).str.to_datetime(TS_FORMAT, strict=strict)


def to_idr(amount_column: str, currency_column: str, fx: dict[str, float]) -> pl.Expr:
    """Amount times the fixed rate of its own currency, rounded to whole rupiah."""
    rate = pl.col(currency_column).replace_strict(fx, return_dtype=pl.Float64)
    return (pl.col(amount_column).cast(pl.Float64) * rate).round(0).cast(pl.Int64)


def localize_features(raw: pl.LazyFrame, maps: Mappings) -> pl.LazyFrame:
    """Raw text rows (WITHOUT the label) -> localized, typed rows keyed by raw_row."""
    if "is_laundering" in raw.collect_schema().names():
        raise ValueError("transforms must not receive the label column (spec 6.1)")
    return raw.select(
        "raw_row",
        (parse_ts("timestamp") + pl.duration(days=OFFSET_DAYS)).alias("ts"),
        pl.col("from_bank").cast(pl.Int64),
        "from_account",
        pl.col("to_bank").cast(pl.Int64),
        "to_account",
        to_idr("amount_received", "receiving_currency", maps.fx).alias("amount_received"),
        to_idr("amount_paid", "payment_currency", maps.fx).alias("amount_paid"),
        pl.col("payment_format").replace_strict(maps.channels, return_dtype=pl.String),
    )


def format_output(df: pl.DataFrame) -> pl.DataFrame:
    """Localized rows (with is_laundering) -> the 11 output columns, exactly as written."""
    out = df.select(
        pl.col("ts").dt.strftime(TS_FORMAT),
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_received",
        pl.lit("IDR").alias("receiving_currency"),
        "amount_paid",
        pl.lit("IDR").alias("payment_currency"),
        "payment_format",
        "is_laundering",
    )
    return out.rename(dict(zip(out.columns, OUT_HEADER, strict=True)))


def check_vocabulary(raw: pl.LazyFrame, maps: Mappings) -> None:
    """Fail early, naming every currency or payment format the mapping tables don't cover."""
    received, paid, formats = pl.collect_all(
        [
            raw.select(pl.col("receiving_currency").unique()),
            raw.select(pl.col("payment_currency").unique()),
            raw.select(pl.col("payment_format").unique()),
        ]
    )
    currencies = set(received.to_series().to_list()) | set(paid.to_series().to_list())
    missing_fx = sorted(str(c) for c in currencies if c not in maps.fx)
    missing_channels = sorted(
        str(f) for f in formats.to_series().to_list() if f not in maps.channels
    )
    if missing_fx or missing_channels:
        raise MappingError(
            "raw data has values missing from the mapping tables: "
            f"currencies {missing_fx} (add rows to mappings/fx_rates.csv), "
            f"payment formats {missing_channels} (add rows to mappings/channels.csv)"
        )
```

- [ ] **Step 7: Run the tests and tooling**

Run: `uv run pytest -q tests/test_transactions.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `9 passed`, then ruff and mypy clean.

- [ ] **Step 8: Commit**

```bash
git add garda_ai_dataset/raw.py garda_ai_dataset/transforms tests/fixture_data.py tests/conftest.py tests/test_transactions.py
git commit -m "feat: raw IBM readers and transaction transforms (time, banks, FX, channels)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Institution assignment

**Files:**
- Create: `garda_ai_dataset/transforms/institutions.py`
- Test: `tests/test_institutions.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_institutions.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.transforms.institutions'`.

- [ ] **Step 3: Implement `garda_ai_dataset/transforms/institutions.py`**

```python
"""Give each IBM Bank ID one Indonesian institution name (spec 6.3). Never reads the label."""

from collections.abc import Sequence

import polars as pl

from garda_ai_dataset.mappings import Institution

CRYPTO_BANK_PREFIX = "Crytpo Bank"  # IBM's own spelling in the HI-* accounts files


def assign_institutions(
    raw_accounts: pl.DataFrame, institutions: Sequence[Institution]
) -> dict[int, str]:
    banks = (
        raw_accounts.with_columns(pl.col("Bank ID").cast(pl.Int64).alias("bank_id"))
        .group_by("bank_id")
        .agg(pl.len().alias("n_accounts"), pl.col("Bank Name").min().alias("ibm_name"))
    )
    assigned: dict[int, str] = {}
    for kind, is_crypto in (("bank", False), ("crypto_exchange", True)):
        pool = banks.filter(
            pl.col("ibm_name").str.starts_with(CRYPTO_BANK_PREFIX) == is_crypto
        ).sort(["n_accounts", "bank_id"], descending=[True, False])
        targets = sorted(
            (i for i in institutions if i.kind == kind), key=lambda i: (-i.weight, i.name)
        )
        assigned.update(_fill(pool["bank_id"].to_list(), pool["n_accounts"].to_list(), targets))
    return assigned


def _fill(bank_ids: list[int], sizes: list[int], targets: list[Institution]) -> dict[int, str]:
    """Walk banks largest-first; move to the next institution once the current one holds its
    weighted share of accounts. Advancing at most one institution per bank guarantees every
    institution gets a bank whenever there are at least as many banks as institutions."""
    if not bank_ids:
        return {}
    total_accounts = sum(sizes)
    total_weight = sum(t.weight for t in targets)
    thresholds: list[float] = []
    running = 0
    for target in targets:
        running += target.weight
        thresholds.append(total_accounts * running / total_weight)
    out: dict[int, str] = {}
    index = 0
    filled = 0
    for bank_id, size in zip(bank_ids, sizes, strict=True):
        out[bank_id] = targets[index].name
        filled += size
        if index < len(targets) - 1 and filled >= thresholds[index]:
            index += 1
    return out
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q tests/test_institutions.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `5 passed`, then ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/transforms/institutions.py tests/test_institutions.py
git commit -m "feat: rank-preserving institution assignment with crypto-exchange pool

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Entities, accounts, and first-seen dates

**Files:**
- Create: `garda_ai_dataset/transforms/entities.py`
- Test: `tests/test_entities.py`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from garda_ai_dataset.errors import MappingError, RawInputError
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import read_raw_accounts, scan_raw_trans
from garda_ai_dataset.transforms.entities import (
    ACCOUNT_COLUMNS,
    ENTITY_COLUMNS,
    build_accounts,
    build_entities,
    entity_prefix,
    first_seen_by_entity,
    read_legacy_accounts,
)
from garda_ai_dataset.transforms.transactions import localize_features
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_entities.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.transforms.entities'`.

- [ ] **Step 3: Implement `garda_ai_dataset/transforms/entities.py`**

```python
"""Entity names, types, display-only profile fields, and the accounts file (spec 6.4).

Nothing here reads the Is Laundering label. Profile fields are for the Users tab only and
are never model features.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from faker import Faker

from garda_ai_dataset.errors import MappingError, RawInputError
from garda_ai_dataset.geo import province_for_entity
from garda_ai_dataset.hashing import stable_int, weighted_pick
from garda_ai_dataset.mappings import Mappings

ENTITY_COLUMNS = (
    "Entity ID",
    "Entity Name",
    "Entity Type",
    "Province",
    "City",
    "Registration Date",
    "KYC Status",
    "Sector",
)
ACCOUNT_COLUMNS = (
    "Bank Name",
    "Bank ID",
    "Account Number",
    "Entity ID",
    "Entity Name",
    "risk_score",
    "risk_category",
)
BUSINESS_SUFFIXES = (
    "Jaya", "Abadi", "Sejahtera", "Makmur", "Mandiri",
    "Sentosa", "Utama", "Perkasa", "Nusantara", "Lestari",
)
MIN_ACCOUNT_AGE_DAYS = 30
MAX_ACCOUNT_AGE_DAYS = 3650
_PREFIX = re.compile(r"^(?P<prefix>.+?) #\d+$")


def entity_prefix(ibm_name: str) -> str:
    match = _PREFIX.match(ibm_name)
    if match is None:
        raise MappingError(f"entity name {ibm_name!r} has no '<Prefix> #<n>' marker")
    return match.group("prefix")


def localized_name(entity_id: str, entity_type: str, kind: str, fake: Faker) -> str:
    fake.seed_instance(stable_int("name", entity_id))
    if kind == "individual":
        return f"{fake.first_name()} {fake.last_name()}"
    suffix = BUSINESS_SUFFIXES[stable_int("suffix", entity_id) % len(BUSINESS_SUFFIXES)]
    return f"{entity_type} {fake.last_name()} {suffix}"


def first_seen_by_entity(trans: pl.LazyFrame, raw_accounts: pl.DataFrame) -> dict[str, date]:
    """Earliest localized transaction date per entity, as sender OR receiver.

    ``trans`` needs Int64 ``from_bank``/``to_bank``, text accounts, and a datetime ``ts``.
    """
    sides = pl.concat(
        [
            trans.select(pl.col("from_bank").alias("bank"), pl.col("from_account").alias("account"), "ts"),
            trans.select(pl.col("to_bank").alias("bank"), pl.col("to_account").alias("account"), "ts"),
        ]
    )
    per_account = sides.group_by("bank", "account").agg(pl.col("ts").min())
    owners = raw_accounts.lazy().select(
        pl.col("Bank ID").cast(pl.Int64).alias("bank"),
        pl.col("Account Number").alias("account"),
        "Entity ID",
    )
    per_entity = (
        per_account.join(owners, on=["bank", "account"], how="inner")
        .group_by("Entity ID")
        .agg(pl.col("ts").min().dt.date().alias("first_seen"))
        .collect()
    )
    return dict(
        zip(per_entity["Entity ID"].to_list(), per_entity["first_seen"].to_list(), strict=True)
    )


def build_entities(
    raw_accounts: pl.DataFrame,
    first_seen: dict[str, date],
    fallback_day: date,
    maps: Mappings,
) -> pl.DataFrame:
    entities = raw_accounts.group_by("Entity ID").agg(pl.col("Entity Name").min()).sort("Entity ID")
    prefixes = {entity_prefix(name) for name in entities["Entity Name"].to_list()}
    unknown = sorted(prefixes - maps.entity_types.keys())
    if unknown:
        raise MappingError(f"entity prefixes missing from mappings/entity_types.csv: {unknown}")
    fake = Faker("id_ID")
    rows: list[tuple[str, ...]] = []
    for entity_id, ibm_name in entities.iter_rows():
        entity_type, kind = maps.entity_types[entity_prefix(ibm_name)]
        province = province_for_entity(entity_id)
        cities = maps.cities[province]
        age_days = MIN_ACCOUNT_AGE_DAYS + stable_int("registration", entity_id) % (
            MAX_ACCOUNT_AGE_DAYS - MIN_ACCOUNT_AGE_DAYS + 1
        )
        registered = first_seen.get(entity_id, fallback_day) - timedelta(days=age_days)
        rows.append(
            (
                entity_id,
                localized_name(entity_id, entity_type, kind, fake),
                entity_type,
                province,
                cities[stable_int("city", entity_id) % len(cities)],
                registered.isoformat(),
                weighted_pick(maps.kyc, stable_int("kyc", entity_id)),
                weighted_pick(maps.sectors[kind], stable_int("sector", entity_id)),
            )
        )
    return pl.DataFrame(rows, schema={c: pl.String for c in ENTITY_COLUMNS}, orient="row")


def read_legacy_accounts(path: Path) -> pl.DataFrame:
    """Risk columns of the old hand-made copy, keyed by (bank_id, account) (spec 5)."""
    if not path.exists():
        raise RawInputError(f"legacy accounts file not found: {path}")
    df = pl.read_csv(path, infer_schema=False)
    needed = ("Bank ID", "Account Number", "risk_score", "risk_category")
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise RawInputError(f"{path.name}: missing columns {missing}")
    out = df.select(
        pl.col("Bank ID").cast(pl.Int64).alias("bank_id"),
        pl.col("Account Number").alias("account"),
        "risk_score",
        "risk_category",
    )
    if out.select(pl.struct("bank_id", "account").is_duplicated().any()).item():
        raise RawInputError(f"{path.name}: duplicate (Bank ID, Account Number) keys")
    return out


def build_accounts(
    raw_accounts: pl.DataFrame,
    bank_names: dict[int, str],
    entities: pl.DataFrame,
    legacy: pl.DataFrame | None,
) -> pl.DataFrame:
    """Raw accounts in their original order, with Indonesian bank and entity names."""
    df = raw_accounts.with_columns(pl.col("Bank ID").cast(pl.Int64)).with_columns(
        pl.col("Bank ID").replace_strict(bank_names, return_dtype=pl.String).alias("Bank Name")
    )
    df = df.drop("Entity Name").join(
        entities.select("Entity ID", "Entity Name"), on="Entity ID", how="left",
        maintain_order="left",
    )
    if legacy is None:
        df = df.with_columns(
            pl.lit(None, dtype=pl.String).alias("risk_score"),
            pl.lit(None, dtype=pl.String).alias("risk_category"),
        )
    else:
        df = df.join(
            legacy, left_on=["Bank ID", "Account Number"], right_on=["bank_id", "account"],
            how="left", maintain_order="left",
        )
    return df.select(ACCOUNT_COLUMNS)
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q tests/test_entities.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `9 passed`, then ruff and mypy clean. If mypy reports Faker attributes as untyped, add this to `pyproject.toml` and re-run:

```toml
[[tool.mypy.overrides]]
module = ["faker", "faker.*"]
ignore_missing_imports = true
```

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/transforms/entities.py tests/test_entities.py pyproject.toml
git commit -m "feat: entity types/names/profiles and localized accounts with legacy risk carry-over

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Patterns, motif labels, and typologies

**Files:**
- Create: `garda_ai_dataset/transforms/patterns.py`
- Test: `tests/test_patterns.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import polars as pl
import pytest

from garda_ai_dataset.errors import RawInputError
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import TRANS_COLS, scan_raw_trans
from garda_ai_dataset.transforms.patterns import (
    Attempt,
    build_typologies,
    match_patterns,
    parse_patterns,
    render_patterns,
)
from tests.fixture_data import RAW_ROWS


def _laundering(paths: DatasetPaths) -> pl.DataFrame:
    return scan_raw_trans(paths.raw_trans).filter(pl.col("is_laundering") == "1").collect()


def test_parse_fixture(raw_paths: DatasetPaths) -> None:
    attempts = parse_patterns(raw_paths.raw_patterns)
    assert [(a.attempt_id, a.motif, len(a.rows)) for a in attempts] == [
        (1, "FAN-OUT", 2), (2, "CYCLE", 1)
    ]
    assert attempts[0].rows[0] == RAW_ROWS[3]
    assert attempts[0].begin_line == "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out"
    assert attempts[1].end_line == "END LAUNDERING ATTEMPT - CYCLE"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("2022/09/01 00:00,1,A,1,B,1,US Dollar,1,US Dollar,ACH,1\n", "outside"),
        ("BEGIN LAUNDERING ATTEMPT - CYCLE\nBEGIN LAUNDERING ATTEMPT - CYCLE\n", "BEGIN"),
        ("END LAUNDERING ATTEMPT - CYCLE\n", "END without"),
        ("BEGIN LAUNDERING ATTEMPT - CYCLE\n", "no END"),
    ],
)
def test_parse_malformed(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "p.txt"
    path.write_text(text)
    with pytest.raises(RawInputError, match=message):
        parse_patterns(path)


def test_match_fixture(raw_paths: DatasetPaths) -> None:
    match = match_patterns(parse_patterns(raw_paths.raw_patterns), _laundering(raw_paths))
    assert match.by_raw_row == {3: (1, "FAN-OUT"), 4: (1, "FAN-OUT"), 9: (2, "CYCLE")}
    assert match.rows_per_attempt == ((3, 4), (9,))
    assert match.unmatched == 0


def test_match_is_a_multiset() -> None:
    line = RAW_ROWS[3]
    fields = line.split(",")
    rows = pl.DataFrame([fields, fields], schema=list(TRANS_COLS), orient="row").with_columns(
        pl.Series("raw_row", [8, 5], dtype=pl.UInt32)
    )
    attempt = Attempt(1, "STACK", "BEGIN LAUNDERING ATTEMPT - STACK",
                      "END LAUNDERING ATTEMPT - STACK", (line, line, line))
    match = match_patterns([attempt], rows)
    assert match.rows_per_attempt == ((5, 8, None),)  # consumed in raw order, third unmatched
    assert match.unmatched == 1


def test_build_typologies(raw_paths: DatasetPaths) -> None:
    match = match_patterns(parse_patterns(raw_paths.raw_patterns), _laundering(raw_paths))
    ids = pl.DataFrame(
        {"raw_row": [3, 4, 9, 10], "transaction_id": [2, 3, 9, 11]},
        schema={"raw_row": pl.UInt32, "transaction_id": pl.UInt32},
    )
    assert build_typologies(ids, match).rows() == [
        (2, 1, "FAN-OUT"), (3, 1, "FAN-OUT"), (9, 2, "CYCLE"), (11, None, "UNATTRIBUTED")
    ]


def test_render_round_trips_and_substitutes(raw_paths: DatasetPaths) -> None:
    attempts = parse_patterns(raw_paths.raw_patterns)
    match = match_patterns(attempts, _laundering(raw_paths))
    identity = {3: RAW_ROWS[3], 4: RAW_ROWS[4], 9: RAW_ROWS[9]}
    assert render_patterns(attempts, match, identity) == raw_paths.raw_patterns.read_text()
    assert render_patterns(attempts, match, {3: "L3", 4: "L4", 9: "L9"}) == (
        "BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 2-degree Fan-Out\nL3\nL4\n"
        "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
        "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 1 hops\nL9\nEND LAUNDERING ATTEMPT - CYCLE\n\n"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_patterns.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.transforms.patterns'`.

- [ ] **Step 3: Implement `garda_ai_dataset/transforms/patterns.py`**

```python
"""Parse IBM Patterns.txt, match attempts to Trans rows, emit motif labels (spec 6.5).

Unlike every other transform this module reads the label ON PURPOSE: typologies.csv is
itself a label product. Matching only ever considers Is Laundering == 1 rows.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from garda_ai_dataset.errors import RawInputError
from garda_ai_dataset.raw import TRANS_COLS

_BEGIN = re.compile(r"^BEGIN LAUNDERING ATTEMPT - (?P<motif>[A-Z][A-Z-]*)")
_END = "END LAUNDERING ATTEMPT"
UNATTRIBUTED = "UNATTRIBUTED"


@dataclass(frozen=True)
class Attempt:
    attempt_id: int
    motif: str
    begin_line: str
    end_line: str
    rows: tuple[str, ...]  # raw CSV line text, exactly as in the file


@dataclass(frozen=True)
class PatternMatch:
    by_raw_row: dict[int, tuple[int, str]]  # raw_row -> (attempt_id, motif)
    rows_per_attempt: tuple[tuple[int | None, ...], ...]  # matched raw_row per pattern row
    unmatched: int


def parse_patterns(path: Path) -> list[Attempt]:
    if not path.exists():
        raise RawInputError(f"input missing: {path} (run `garda-dataset fetch` first)")
    attempts: list[Attempt] = []
    motif: str | None = None
    begin: str | None = None
    rows: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        found = _BEGIN.match(line)
        if found:
            if begin is not None:
                raise RawInputError(f"{path.name}:{lineno}: BEGIN before the previous attempt ended")
            motif, begin, rows = found.group("motif"), line, []
        elif line.startswith(_END):
            if begin is None or motif is None:
                raise RawInputError(f"{path.name}:{lineno}: END without BEGIN")
            attempts.append(Attempt(len(attempts) + 1, motif, begin, line, tuple(rows)))
            motif, begin = None, None
        else:
            if begin is None:
                raise RawInputError(f"{path.name}:{lineno}: transaction row outside an attempt")
            rows.append(line)
    if begin is not None:
        raise RawInputError(f"{path.name}: the last attempt has no END line")
    return attempts


def match_patterns(attempts: list[Attempt], laundering_rows: pl.DataFrame) -> PatternMatch:
    """``laundering_rows``: the 11 raw text columns plus ``raw_row``, Is Laundering == 1 only.
    Rows match on exact raw line text; duplicates are consumed as a multiset in raw order."""
    keyed = laundering_rows.select(
        pl.concat_str([pl.col(c) for c in TRANS_COLS], separator=",").alias("line"), "raw_row"
    ).sort("raw_row")
    pool: dict[str, list[int]] = defaultdict(list)
    for line, raw_row in keyed.iter_rows():
        pool[line].append(raw_row)
    by_raw_row: dict[int, tuple[int, str]] = {}
    per_attempt: list[tuple[int | None, ...]] = []
    unmatched = 0
    for attempt in attempts:
        matched: list[int | None] = []
        for line in attempt.rows:
            bucket = pool.get(line)
            if bucket:
                raw_row = bucket.pop(0)
                by_raw_row[raw_row] = (attempt.attempt_id, attempt.motif)
                matched.append(raw_row)
            else:
                unmatched += 1
                matched.append(None)
        per_attempt.append(tuple(matched))
    return PatternMatch(by_raw_row, tuple(per_attempt), unmatched)


def build_typologies(laundering_ids: pl.DataFrame, match: PatternMatch) -> pl.DataFrame:
    """``laundering_ids``: raw_row + transaction_id (UInt32) of every laundering row."""
    labels = pl.DataFrame(
        {
            "raw_row": list(match.by_raw_row),
            "attempt_id": [v[0] for v in match.by_raw_row.values()],
            "motif": [v[1] for v in match.by_raw_row.values()],
        },
        schema={"raw_row": pl.UInt32, "attempt_id": pl.Int64, "motif": pl.String},
    )
    return (
        laundering_ids.join(labels, on="raw_row", how="left")
        .with_columns(pl.col("motif").fill_null(UNATTRIBUTED))
        .sort("transaction_id")
        .select("transaction_id", "attempt_id", "motif")
    )


def render_patterns(
    attempts: list[Attempt], match: PatternMatch, localized_lines: dict[int, str]
) -> str:
    """Re-emit Patterns.txt with each matched row replaced by its localized Trans line."""
    out: list[str] = []
    for attempt, raw_rows in zip(attempts, match.rows_per_attempt, strict=True):
        out.append(attempt.begin_line)
        for raw_line, raw_row in zip(attempt.rows, raw_rows, strict=True):
            out.append(localized_lines[raw_row] if raw_row is not None else raw_line)
        out.append(attempt.end_line)
        out.append("")
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q tests/test_patterns.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `9 passed`, then ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/transforms/patterns.py tests/test_patterns.py
git commit -m "feat: Patterns.txt parsing, multiset matching, typology labels and rendering

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Two-pass localize orchestration

**Files:**
- Create: `garda_ai_dataset/localize.py`
- Test: `tests/test_localize.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import polars as pl
import pytest

from garda_ai_dataset.errors import DiskSpaceError, RawInputError
from garda_ai_dataset.localize import localize_frames, run_localize
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths, dataset_paths
from garda_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from tests.fixture_data import EXPECTED_TID, LEGACY_ACCOUNTS, RAW_ROWS, write_raw

OUTPUTS = ("out_trans", "out_accounts", "out_entities", "out_patterns", "out_typologies")


def _run(paths: DatasetPaths, maps: Mappings, legacy: Path | None = None) -> dict[str, object]:
    return run_localize(paths, maps, legacy, min_free_bytes=0)


def test_outputs_and_manifest(raw_paths: DatasetPaths, maps: Mappings) -> None:
    manifest = _run(raw_paths, maps)
    for attr in OUTPUTS:
        assert getattr(raw_paths, attr).exists(), attr
    assert raw_paths.manifest.exists()
    assert not raw_paths.tmp_dir.exists()
    assert manifest["counts"] == {
        "transactions": 12, "laundering": 4, "accounts": 9, "entities": 7, "banks": 4,
        "days": 3, "first_day": "2025-09-04", "last_day": "2025-09-06",
    }
    assert manifest["typology"] == {
        "attempts": 2, "pattern_rows": 3, "matched_rows": 3, "unmatched_pattern_rows": 0,
        "laundering_coverage": 0.75,
    }
    assert manifest["risk_source"] == "none"


def test_trans_is_sorted_and_labels_follow_rows(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    out = pl.read_csv(raw_paths.out_trans, infer_schema=False)
    assert tuple(out.columns) == OUT_HEADER
    raw_by_tid = {tid: raw_row for raw_row, tid in EXPECTED_TID.items()}
    raw_labels = [row.rsplit(",", 1)[1] for row in RAW_ROWS]
    assert out["Is Laundering"].to_list() == [raw_labels[raw_by_tid[t]] for t in range(1, 13)]
    assert out["Timestamp"].to_list() == sorted(out["Timestamp"].to_list())
    assert out["Timestamp"][0] == "2025/09/04 00:20"
    assert out["Account"].to_list()[3:5] == ["B1", "A3"]  # 09:30 tie broken by raw_row
    assert set(out["Receiving Currency"].to_list()) == {"IDR"}


def test_typologies(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    assert pl.read_csv(raw_paths.out_typologies).rows() == [
        (2, 1, "FAN-OUT"), (3, 1, "FAN-OUT"), (9, 2, "CYCLE"), (11, None, "UNATTRIBUTED")
    ]


def test_patterns_reuse_trans_lines(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    trans_lines = raw_paths.out_trans.read_text().splitlines()[1:]
    pattern_rows = [line for line in raw_paths.out_patterns.read_text().splitlines()
                    if line.startswith("2025")]
    assert pattern_rows == [trans_lines[1], trans_lines[2], trans_lines[8]]  # tids 2, 3, 9


def test_accounts_entities_and_legacy(raw_paths: DatasetPaths, maps: Mappings,
                                      tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.csv"
    legacy.write_text(LEGACY_ACCOUNTS)
    manifest = _run(raw_paths, maps, legacy)
    assert manifest["risk_source"] == "legacy-carryover"
    accounts = pl.read_csv(raw_paths.out_accounts, infer_schema=False)
    by_account = {r["Account Number"] + "@" + r["Bank ID"]: r
                  for r in accounts.iter_rows(named=True)}
    assert by_account["C1@126"]["Bank Name"] == "Indodax"
    assert by_account["A1@10"]["Bank Name"] == "Bank Rakyat Indonesia"
    assert by_account["A1@10"]["risk_category"] == "Low"
    entities = pl.read_csv(raw_paths.out_entities, infer_schema=False)
    assert entities.height == 7
    e1 = entities.filter(pl.col("Entity ID") == "E1").row(0, named=True)
    assert e1["Registration Date"] < "2025-09-04"
    assert by_account["A1@10"]["Entity Name"] == e1["Entity Name"]


def test_deterministic(tmp_path: Path, maps: Mappings) -> None:
    a = write_raw(tmp_path / "a")
    b = write_raw(tmp_path / "b")
    _run(a, maps)
    _run(b, maps)
    for attr in OUTPUTS:
        assert getattr(a, attr).read_bytes() == getattr(b, attr).read_bytes(), attr


def test_streaming_matches_in_memory(raw_paths: DatasetPaths, maps: Mappings) -> None:
    _run(raw_paths, maps)
    frames = localize_frames(
        scan_raw_trans(raw_paths.raw_trans).collect(),
        read_raw_accounts(raw_paths.raw_accounts),
        maps,
    )
    assert frames["trans"].write_csv() == raw_paths.out_trans.read_text()
    assert frames["entities"].write_csv() == raw_paths.out_entities.read_text()
    assert frames["accounts"].write_csv() == raw_paths.out_accounts.read_text()


def test_inverting_labels_changes_only_labels(raw_paths: DatasetPaths, maps: Mappings) -> None:
    raw = scan_raw_trans(raw_paths.raw_trans).collect()
    accounts = read_raw_accounts(raw_paths.raw_accounts)
    inverted = raw.with_columns(
        (1 - pl.col("is_laundering").cast(pl.Int8)).cast(pl.String).alias("is_laundering")
    )
    normal = localize_frames(raw, accounts, maps)
    flipped = localize_frames(inverted, accounts, maps)
    assert normal["trans"].drop("Is Laundering").equals(flipped["trans"].drop("Is Laundering"))
    assert not normal["trans"]["Is Laundering"].equals(flipped["trans"]["Is Laundering"])
    assert normal["entities"].equals(flipped["entities"])
    assert normal["accounts"].equals(flipped["accounts"])


def test_disk_space_guard(raw_paths: DatasetPaths, maps: Mappings) -> None:
    with pytest.raises(DiskSpaceError):
        run_localize(raw_paths, maps, None, min_free_bytes=10**18)


def test_missing_raw_input(tmp_path: Path, maps: Mappings) -> None:
    with pytest.raises(RawInputError):
        run_localize(dataset_paths(tmp_path, "small"), maps, None, min_free_bytes=0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_localize.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.localize'`.

- [ ] **Step 3: Implement `garda_ai_dataset/localize.py`**

```python
"""Two-pass localization (spec 5 and 9).

Pass 1 streams raw rows through the transforms into Parquet. Pass 2 sorts one dataset day at
a time and appends it to the output CSV. Memory stays bounded by the largest day.
"""

import json
import shutil
import time
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from garda_ai_dataset import __version__
from garda_ai_dataset.errors import DiskSpaceError
from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import OUT_HEADER, read_raw_accounts, scan_raw_trans
from garda_ai_dataset.transforms.entities import (
    build_accounts,
    build_entities,
    first_seen_by_entity,
    read_legacy_accounts,
)
from garda_ai_dataset.transforms.institutions import assign_institutions
from garda_ai_dataset.transforms.patterns import (
    build_typologies,
    match_patterns,
    parse_patterns,
    render_patterns,
)
from garda_ai_dataset.transforms.transactions import (
    check_vocabulary,
    format_output,
    localize_features,
)

MIN_FREE_BYTES = 10 * 1024**3


def stage_transactions(raw: pl.LazyFrame, maps: Mappings) -> pl.LazyFrame:
    """Localized rows. The transforms never see the label; it is re-attached by raw_row."""
    features = localize_features(raw.drop("is_laundering"), maps)
    labels = raw.select("raw_row", pl.col("is_laundering").cast(pl.Int8))
    return features.join(labels, on="raw_row", how="inner").with_columns(
        pl.col("ts").dt.date().alias("day")
    )


def _first_day(staged: pl.DataFrame) -> date:
    first = staged["day"].min()
    if not isinstance(first, date):
        raise ValueError("no transactions to localize")
    return first


def localize_frames(
    raw: pl.DataFrame, raw_accounts: pl.DataFrame, maps: Mappings
) -> dict[str, pl.DataFrame]:
    """In-memory equivalent of run_localize, for tests and the label-independence check."""
    staged = stage_transactions(raw.lazy(), maps).sort(["ts", "raw_row"]).collect()
    first_seen = first_seen_by_entity(staged.lazy(), raw_accounts)
    entities = build_entities(raw_accounts, first_seen, _first_day(staged), maps)
    bank_names = assign_institutions(raw_accounts, maps.institutions)
    return {
        "trans": format_output(staged),
        "entities": entities,
        "accounts": build_accounts(raw_accounts, bank_names, entities, None),
    }


def run_localize(
    paths: DatasetPaths,
    maps: Mappings,
    legacy_accounts: Path | None,
    *,
    min_free_bytes: int | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    raw = scan_raw_trans(paths.raw_trans)
    raw_accounts = read_raw_accounts(paths.raw_accounts)
    attempts = parse_patterns(paths.raw_patterns)
    check_vocabulary(raw, maps)

    paths.out_dir.mkdir(parents=True, exist_ok=True)
    needed = MIN_FREE_BYTES if min_free_bytes is None else min_free_bytes
    free = shutil.disk_usage(paths.out_dir).free
    if free < needed:
        raise DiskSpaceError(
            f"{paths.out_dir} has {free / 1024**3:.1f} GiB free; need {needed / 1024**3:.1f} GiB"
        )
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    paths.tmp_dir.mkdir()

    # Pass 1: stream every row through the transforms into Parquet.
    stage_path = paths.tmp_dir / "localized.parquet"
    stage_transactions(raw, maps).sink_parquet(stage_path)
    staged = pl.scan_parquet(stage_path)

    # Pass 2: sort one day at a time and append to the output CSV.
    days: list[date] = staged.select(pl.col("day").unique().sort()).collect().to_series().to_list()
    id_parts: list[pl.DataFrame] = []
    written = 0
    with paths.out_trans.open("w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(OUT_HEADER) + "\n")
        for day in days:
            day_df = staged.filter(pl.col("day") == day).sort(["ts", "raw_row"]).collect()
            format_output(day_df).write_csv(fh, include_header=False)
            id_parts.append(
                day_df.with_row_index("transaction_id", offset=written + 1)
                .filter(pl.col("is_laundering") == 1)
                .select("raw_row", "transaction_id")
            )
            written += day_df.height
    laundering_ids = pl.concat(id_parts)

    bank_names = assign_institutions(raw_accounts, maps.institutions)
    entities = build_entities(raw_accounts, first_seen_by_entity(staged, raw_accounts), days[0], maps)
    legacy = read_legacy_accounts(legacy_accounts) if legacy_accounts is not None else None
    accounts = build_accounts(raw_accounts, bank_names, entities, legacy)
    entities.write_csv(paths.out_entities)
    accounts.write_csv(paths.out_accounts)

    match = match_patterns(attempts, raw.filter(pl.col("is_laundering") == "1").collect())
    build_typologies(laundering_ids, match).write_csv(paths.out_typologies)
    matched = (
        staged.filter(pl.col("raw_row").is_in(list(match.by_raw_row))).collect().sort("raw_row")
    )
    lines = format_output(matched).write_csv(include_header=False).splitlines()
    localized_lines = dict(zip(matched["raw_row"].to_list(), lines, strict=True))
    paths.out_patterns.write_text(
        render_patterns(attempts, match, localized_lines), encoding="utf-8"
    )

    raw_files = (paths.raw_trans, paths.raw_accounts, paths.raw_patterns)
    out_files = (paths.out_trans, paths.out_accounts, paths.out_entities, paths.out_patterns,
                 paths.out_typologies)
    manifest: dict[str, object] = {
        "pipeline_version": __version__,
        "dataset": paths.name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": {p.name: sha256_file(p) for p in raw_files},
        "mappings": maps.hashes,
        "legacy_accounts": None if legacy_accounts is None else {
            "path": str(legacy_accounts), "sha256": sha256_file(legacy_accounts)
        },
        "risk_source": "none" if legacy_accounts is None else "legacy-carryover",
        "outputs": {p.name: sha256_file(p) for p in out_files},
        "counts": {
            "transactions": written,
            "laundering": laundering_ids.height,
            "accounts": accounts.height,
            "entities": entities.height,
            "banks": len(bank_names),
            "days": len(days),
            "first_day": days[0].isoformat(),
            "last_day": days[-1].isoformat(),
        },
        "typology": {
            "attempts": len(attempts),
            "pattern_rows": sum(len(a.rows) for a in attempts),
            "matched_rows": len(match.by_raw_row),
            "unmatched_pattern_rows": match.unmatched,
            "laundering_coverage": round(len(match.by_raw_row) / max(laundering_ids.height, 1), 4),
        },
        "wall_time_s": round(time.perf_counter() - started, 1),
    }
    paths.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    return manifest
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: the whole suite passes, and ruff and mypy are clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/localize.py tests/test_localize.py
git commit -m "feat: two-pass per-day localize orchestration with manifest

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Validator (invariants, distribution report, mutation tests)

**Files:**
- Create: `garda_ai_dataset/validate.py`
- Test: `tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

import polars as pl
import pytest

import garda_ai_dataset.validate as validate_mod
from garda_ai_dataset.localize import run_localize
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.validate import Check, ValidationReport, validate_dataset

ALL_CHECKS = {
    "header", "row_count", "node_merge", "labels", "graph_keys", "fx", "time", "order",
    "channels", "label_independence", "patterns", "entities", "manifest",
}


@pytest.fixture
def built(raw_paths: DatasetPaths, maps: Mappings) -> DatasetPaths:
    run_localize(raw_paths, maps, None, min_free_bytes=0)
    return raw_paths


def _check(report: ValidationReport, name: str) -> Check:
    return next(c for c in report.checks if c.name == name)


def _edit_trans(paths: DatasetPaths, row: int, column: str, value: str) -> None:
    """Overwrite one field of data row ``row`` (1-based == transaction_id)."""
    lines = paths.out_trans.read_text().splitlines()
    header = lines[0].split(",")
    fields = lines[row].split(",")
    fields[header.index(column)] = value
    lines[row] = ",".join(fields)
    paths.out_trans.write_text("\n".join(lines) + "\n")


def test_fresh_build_passes(built: DatasetPaths, maps: Mappings) -> None:
    report = validate_dataset(built, maps)
    assert report.ok, report.render()
    assert {c.name for c in report.checks} == ALL_CHECKS
    assert any("Pemindahbukuan" in line for line in report.distribution)
    assert not built.tmp_dir.exists()


@pytest.mark.parametrize(
    ("column", "value", "check"),
    [
        ("Is Laundering", "1", "labels"),
        ("Account", "ZZ", "graph_keys"),
        ("Amount Paid", "1", "fx"),
        ("Receiving Currency", "USD", "fx"),
        ("Timestamp", "2025/09/04 00:21", "time"),
        ("Payment Format", "RTGS", "channels"),
    ],
)
def test_corrupted_value_is_caught(built: DatasetPaths, maps: Mappings, column: str,
                                   value: str, check: str) -> None:
    _edit_trans(built, 1, column, value)
    report = validate_dataset(built, maps)
    assert not _check(report, check).ok
    assert not _check(report, "manifest").ok  # the output hash changed too


def test_dropped_row_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_trans.read_text().splitlines()
    built.out_trans.write_text("\n".join(lines[:-1]) + "\n")
    assert not _check(validate_dataset(built, maps), "row_count").ok


def test_swapped_rows_are_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_trans.read_text().splitlines()
    lines[2], lines[3] = lines[3], lines[2]  # tids 2 and 3: 08:00 and 08:05
    built.out_trans.write_text("\n".join(lines) + "\n")
    assert not _check(validate_dataset(built, maps), "order").ok


def test_typologies_tamper_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    lines = built.out_typologies.read_text().splitlines()
    built.out_typologies.write_text("\n".join(lines[:-1]) + "\n")
    assert not _check(validate_dataset(built, maps), "patterns").ok


def test_pattern_line_tamper_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    text = built.out_patterns.read_text().replace("2025/09/04 08:00", "2025/09/04 08:01")
    built.out_patterns.write_text(text)
    assert not _check(validate_dataset(built, maps), "patterns").ok


def test_unknown_institution_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    built.out_accounts.write_text(built.out_accounts.read_text().replace("Indodax", "Bank Palsu"))
    assert not _check(validate_dataset(built, maps), "entities").ok


def test_late_registration_is_caught(built: DatasetPaths, maps: Mappings) -> None:
    ents = pl.read_csv(built.out_entities, infer_schema=False).with_columns(
        pl.when(pl.col("Entity ID") == "E1").then(pl.lit("2030-01-01"))
        .otherwise(pl.col("Registration Date")).alias("Registration Date")
    )
    ents.write_csv(built.out_entities)
    assert not _check(validate_dataset(built, maps), "entities").ok


def test_manifest_tamper_fails_only_manifest(built: DatasetPaths, maps: Mappings) -> None:
    manifest = json.loads(built.manifest.read_text())
    manifest["mappings"]["fx_rates.csv"] = "0" * 64
    built.manifest.write_text(json.dumps(manifest))
    assert validate_dataset(built, maps).failed() == ["manifest"]


def test_label_leak_is_caught(built: DatasetPaths, maps: Mappings,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    real = validate_mod.localize_frames

    def leaky(raw: pl.DataFrame, accounts: pl.DataFrame, m: Mappings) -> dict[str, pl.DataFrame]:
        frames = real(raw, accounts, m)
        frames["trans"] = frames["trans"].with_columns(
            pl.when(pl.col("Is Laundering") == 1).then(pl.lit("LEAK"))
            .otherwise(pl.col("Payment Format")).alias("Payment Format")
        )
        return frames

    monkeypatch.setattr(validate_mod, "localize_frames", leaky)
    assert not _check(validate_dataset(built, maps), "label_independence").ok


def test_node_merge_is_caught(raw_paths: DatasetPaths, maps: Mappings) -> None:
    # A1 now appears under both "010" and "0010": two IBM nodes would merge into one.
    text = raw_paths.raw_trans.read_text().replace(
        "2022/09/01 09:30,0010,A3", "2022/09/01 09:30,0010,A1"
    )
    raw_paths.raw_trans.write_text(text)
    run_localize(raw_paths, maps, None, min_free_bytes=0)
    assert not _check(validate_dataset(raw_paths, maps), "node_merge").ok
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_validate.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.validate'`.

- [ ] **Step 3: Implement `garda_ai_dataset/validate.py`**

```python
"""Invariant checks (spec 8), run one dataset day at a time so HI-Medium fits in memory.

Every check re-derives its expectation from the RAW files. Nothing is trusted from the build.
"""

import json
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import polars as pl

from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.localize import localize_frames
from garda_ai_dataset.mappings import Mappings
from garda_ai_dataset.paths import DatasetPaths
from garda_ai_dataset.raw import (
    OUT_HEADER,
    TRANS_COLS,
    read_raw_accounts,
    scan_raw_trans,
    scan_trans_csv,
)
from garda_ai_dataset.transforms.entities import first_seen_by_entity
from garda_ai_dataset.transforms.patterns import build_typologies, match_patterns, parse_patterns
from garda_ai_dataset.transforms.transactions import OFFSET_DAYS, parse_ts, to_idr

LABEL_SAMPLE_ROWS = 200_000
ROW_CHECKS = ("labels", "graph_keys", "fx", "time", "order", "channels")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    distribution: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def failed(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name, ok, detail))

    def render(self) -> str:
        lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.name:<20} {c.detail}" for c in self.checks]
        return "\n".join([*lines, "", "Distribution (informational):", *self.distribution])


def validate_dataset(
    paths: DatasetPaths, maps: Mappings, *, label_sample_rows: int = LABEL_SAMPLE_ROWS
) -> ValidationReport:
    shutil.rmtree(paths.tmp_dir, ignore_errors=True)
    paths.tmp_dir.mkdir(parents=True)
    try:
        return _validate(paths, maps, label_sample_rows)
    finally:
        shutil.rmtree(paths.tmp_dir, ignore_errors=True)


def _differs(a: pl.Expr, b: pl.Expr) -> pl.Expr:
    return (a != b).fill_null(True)


def _as_int(column: str) -> pl.Expr:
    return pl.col(column).cast(pl.Int64, strict=False)


def _day_mismatches(r: pl.DataFrame, o: pl.DataFrame, maps: Mappings) -> dict[str, int]:
    df = pl.concat([r.rename(lambda c: f"r_{c}"), o.rename(lambda c: f"o_{c}")], how="horizontal")
    exprs = {
        "labels": _differs(pl.col("r_is_laundering"), pl.col("o_is_laundering")),
        "graph_keys": _differs(_as_int("r_from_bank"), _as_int("o_from_bank"))
        | _differs(pl.col("r_from_account"), pl.col("o_from_account"))
        | _differs(_as_int("r_to_bank"), _as_int("o_to_bank"))
        | _differs(pl.col("r_to_account"), pl.col("o_to_account")),
        "fx": _differs(to_idr("r_amount_paid", "r_payment_currency", maps.fx),
                       _as_int("o_amount_paid"))
        | _differs(to_idr("r_amount_received", "r_receiving_currency", maps.fx),
                   _as_int("o_amount_received"))
        | _differs(pl.col("o_payment_currency"), pl.lit("IDR"))
        | _differs(pl.col("o_receiving_currency"), pl.lit("IDR")),
        "time": _differs(pl.col("o_out_ts") - pl.col("r_raw_ts"),
                         pl.lit(timedelta(days=OFFSET_DAYS))),
        "order": (pl.col("o_out_ts").diff() < pl.duration(minutes=0)).fill_null(False),
        "channels": _differs(
            pl.col("r_payment_format").replace_strict(maps.channels, return_dtype=pl.String),
            pl.col("o_payment_format"),
        ),
    }
    row = df.select([e.sum().alias(k) for k, e in exprs.items()]).row(0, named=True)
    return {k: int(v) for k, v in row.items()}


def _validate(paths: DatasetPaths, maps: Mappings, label_sample_rows: int) -> ValidationReport:
    report = ValidationReport()
    with paths.out_trans.open(encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n")
    report.add("header", header == ",".join(OUT_HEADER), header)

    raw_pq = paths.tmp_dir / "raw.parquet"
    out_pq = paths.tmp_dir / "out.parquet"
    scan_raw_trans(paths.raw_trans).with_columns(parse_ts("timestamp").alias("raw_ts")).with_columns(
        pl.col("raw_ts").dt.date().alias("raw_day")
    ).sink_parquet(raw_pq)
    scan_trans_csv(paths.out_trans).with_row_index("transaction_id", offset=1).with_columns(
        parse_ts("timestamp", strict=False).alias("out_ts")
    ).sink_parquet(out_pq)
    raw = pl.scan_parquet(raw_pq)
    out = pl.scan_parquet(out_pq)

    sides = pl.concat(
        [
            raw.select(pl.col("from_bank").alias("bank"), pl.col("from_account").alias("account")),
            raw.select(pl.col("to_bank").alias("bank"), pl.col("to_account").alias("account")),
        ]
    )
    n_text = int(sides.unique().select(pl.len()).collect().item())
    n_int = int(
        sides.with_columns(pl.col("bank").cast(pl.Int64)).unique().select(pl.len()).collect().item()
    )
    report.add("node_merge", n_text == n_int, f"text keys={n_text} integer keys={n_int}")

    # Row-level checks, one raw day at a time.
    mismatches: dict[str, int] = defaultdict(int)
    day_errors: list[str] = []
    id_parts: list[pl.DataFrame] = []
    last_ts: datetime | None = None
    raw_days: list[date] = (
        raw.select(pl.col("raw_day").unique().sort()).collect().to_series().to_list()
    )
    for day in raw_days:
        r = raw.filter(pl.col("raw_day") == day).sort(["raw_ts", "raw_row"]).collect()
        o = (
            out.filter(pl.col("out_ts").dt.date() == day + timedelta(days=OFFSET_DAYS))
            .sort("transaction_id")
            .collect()
        )
        if r.height != o.height:
            day_errors.append(f"{day}: raw={r.height} out={o.height}")
            continue
        for name, count in _day_mismatches(r, o, maps).items():
            mismatches[name] += count
        if o.height:
            if last_ts is not None and o["out_ts"][0] < last_ts:
                mismatches["order"] += 1
            last_ts = o["out_ts"][-1]
        id_parts.append(
            pl.DataFrame({"raw_row": r["raw_row"], "transaction_id": o["transaction_id"],
                          "is_laundering": r["is_laundering"]})
            .filter(pl.col("is_laundering") == "1")
            .drop("is_laundering")
        )
    n_raw = int(raw.select(pl.len()).collect().item())
    n_out = int(out.select(pl.len()).collect().item())
    report.add("row_count", n_raw == n_out and not day_errors,
               f"raw={n_raw} out={n_out} {'; '.join(day_errors)}".strip())
    for name in ROW_CHECKS:
        report.add(name, mismatches[name] == 0 and not day_errors,
                   f"{mismatches[name]} mismatching rows")

    _check_label_independence(report, paths, maps, label_sample_rows)
    _check_patterns(report, paths, raw, out, id_parts)
    _check_entities(report, paths, maps, out)
    _check_manifest(report, paths, maps)
    report.distribution = _distribution(paths, maps, out)
    return report


def _check_label_independence(report: ValidationReport, paths: DatasetPaths, maps: Mappings,
                              sample_rows: int) -> None:
    sample = scan_raw_trans(paths.raw_trans).head(sample_rows).collect()
    keys = pl.concat(
        [
            sample.select(pl.col("from_bank").cast(pl.Int64).alias("b"),
                          pl.col("from_account").alias("a")),
            sample.select(pl.col("to_bank").cast(pl.Int64).alias("b"),
                          pl.col("to_account").alias("a")),
        ]
    ).unique()
    accounts = (
        read_raw_accounts(paths.raw_accounts)
        .with_columns(pl.col("Bank ID").cast(pl.Int64).alias("_b"))
        .join(keys, left_on=["_b", "Account Number"], right_on=["b", "a"], how="semi")
        .drop("_b")
    )
    inverted = sample.with_columns(
        (1 - pl.col("is_laundering").cast(pl.Int8)).cast(pl.String).alias("is_laundering")
    )
    normal = localize_frames(sample, accounts, maps)
    flipped = localize_frames(inverted, accounts, maps)
    same = (
        normal["trans"].drop("Is Laundering").equals(flipped["trans"].drop("Is Laundering"))
        and normal["entities"].equals(flipped["entities"])
        and normal["accounts"].equals(flipped["accounts"])
    )
    changed = not normal["trans"]["Is Laundering"].equals(flipped["trans"]["Is Laundering"])
    report.add("label_independence", same and changed,
               f"{sample.height} rows; labels inverted, non-label outputs "
               f"{'identical' if same else 'DIFFER'}")


def _check_patterns(report: ValidationReport, paths: DatasetPaths, raw: pl.LazyFrame,
                    out: pl.LazyFrame, id_parts: list[pl.DataFrame]) -> None:
    attempts = parse_patterns(paths.raw_patterns)
    laundering = raw.filter(pl.col("is_laundering") == "1").select(*TRANS_COLS, "raw_row").collect()
    match = match_patterns(attempts, laundering)
    ids = (
        pl.concat(id_parts)
        if id_parts
        else pl.DataFrame(schema={"raw_row": pl.UInt32, "transaction_id": pl.UInt32})
    )
    expected = build_typologies(ids, match)
    actual = pl.read_csv(
        paths.out_typologies,
        schema={"transaction_id": pl.UInt32, "attempt_id": pl.Int64, "motif": pl.String},
    )
    tids = actual.filter(pl.col("attempt_id").is_not_null())["transaction_id"].to_list()
    trans_lines = sorted(
        out.filter(pl.col("transaction_id").is_in(tids))
        .select(pl.concat_str([pl.col(c) for c in TRANS_COLS], separator=","))
        .collect()
        .to_series()
        .to_list()
    )
    pattern_lines = sorted(
        line for line in paths.out_patterns.read_text(encoding="utf-8").splitlines()
        if line[:1].isdigit()
    )
    ok = match.unmatched == 0 and expected.equals(actual) and trans_lines == pattern_lines
    report.add("patterns", ok,
               f"unmatched pattern rows={match.unmatched}; typologies "
               f"{'match' if expected.equals(actual) else 'DIFFER'}; pattern lines "
               f"{'match' if trans_lines == pattern_lines else 'DIFFER'}; coverage="
               f"{len(match.by_raw_row)}/{expected.height}")


def _check_entities(report: ValidationReport, paths: DatasetPaths, maps: Mappings,
                    out: pl.LazyFrame) -> None:
    entities = pl.read_csv(paths.out_entities, infer_schema=False)
    accounts = pl.read_csv(paths.out_accounts, infer_schema=False)
    orphan_accounts = accounts.join(entities, on="Entity ID", how="anti").height
    name_mismatch = (
        accounts.join(entities.select("Entity ID", pl.col("Entity Name").alias("_n")),
                      on="Entity ID")
        .filter(pl.col("Entity Name") != pl.col("_n"))
        .height
    )
    known = {i.name for i in maps.institutions}
    unknown_banks = sorted(set(accounts["Bank Name"].to_list()) - known)
    trans = out.select(
        pl.col("from_bank").cast(pl.Int64, strict=False),
        "from_account",
        pl.col("to_bank").cast(pl.Int64, strict=False),
        "to_account",
        pl.col("out_ts").alias("ts"),
    )
    first_seen = first_seen_by_entity(trans, accounts)
    late = 0
    for entity_id, registered in entities.select("Entity ID", "Registration Date").iter_rows():
        if entity_id not in first_seen:
            continue
        try:
            if date.fromisoformat(registered) >= first_seen[entity_id]:
                late += 1
        except ValueError:
            late += 1
    trans_keys = pl.concat(
        [
            trans.select(pl.col("from_bank").alias("b"), pl.col("from_account").alias("a")),
            trans.select(pl.col("to_bank").alias("b"), pl.col("to_account").alias("a")),
        ]
    ).unique()
    account_keys = accounts.lazy().select(
        pl.col("Bank ID").cast(pl.Int64).alias("b"), pl.col("Account Number").alias("a")
    )
    missing_accounts = int(
        trans_keys.join(account_keys, on=["b", "a"], how="anti").select(pl.len()).collect().item()
    )
    ok = not (orphan_accounts or name_mismatch or unknown_banks or late or missing_accounts)
    report.add("entities", ok,
               f"accounts without entity={orphan_accounts}, name mismatches={name_mismatch}, "
               f"unknown institutions={unknown_banks}, registration not before first "
               f"transaction={late}, transaction accounts missing from accounts.csv="
               f"{missing_accounts}")


def _check_manifest(report: ValidationReport, paths: DatasetPaths, maps: Mappings) -> None:
    try:
        manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("manifest", False, f"unreadable: {exc}")
        return
    raw_files = (paths.raw_trans, paths.raw_accounts, paths.raw_patterns)
    out_files = (paths.out_trans, paths.out_accounts, paths.out_entities, paths.out_patterns,
                 paths.out_typologies)
    ok = (
        manifest.get("inputs") == {p.name: sha256_file(p) for p in raw_files}
        and manifest.get("mappings") == maps.hashes
        and manifest.get("outputs") == {p.name: sha256_file(p) for p in out_files}
    )
    report.add("manifest", ok,
               "hashes match" if ok else "a recorded sha256 differs from the file on disk")


def _distribution(paths: DatasetPaths, maps: Mappings, out: pl.LazyFrame) -> list[str]:
    lines: list[str] = []
    per_channel = (
        out.group_by("payment_format")
        .agg(
            pl.len().alias("rows"),
            (pl.col("is_laundering") == "1").mean().alias("rate"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).median().alias("p50"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).quantile(0.99).alias("p99"),
            pl.col("amount_paid").cast(pl.Int64, strict=False).max().alias("max"),
        )
        .sort("rows", descending=True)
        .collect()
    )
    lines.append(f"{'channel':<20}{'rows':>12}{'laundering %':>14}{'p50 IDR':>18}"
                 f"{'p99 IDR':>22}{'max IDR':>24}")
    for row in per_channel.iter_rows(named=True):
        lines.append(f"{row['payment_format']:<20}{row['rows']:>12,}{row['rate'] * 100:>13.3f}%"
                     f"{row['p50']:>18,.0f}{row['p99']:>22,.0f}{row['max']:>24,}")
    group_of = {i.name: i.group for i in maps.institutions}
    bank_group = (
        pl.read_csv(paths.out_accounts, infer_schema=False)
        .select(pl.col("Bank ID").cast(pl.Int64).alias("bank"), "Bank Name")
        .unique("bank")
        .with_columns(pl.col("Bank Name").replace_strict(group_of, default="?").alias("group"))
        .select("bank", "group")
    )
    per_group = (
        out.select(pl.col("from_bank").cast(pl.Int64, strict=False).alias("bank"))
        .join(bank_group.lazy(), on="bank", how="left")
        .group_by("group")
        .agg(pl.len().alias("rows"))
        .sort("rows", descending=True)
        .collect()
    )
    lines.append("")
    lines.append("sender institution group: " + ", ".join(
        f"{g}={n:,}" for g, n in per_group.iter_rows()))
    types = pl.read_csv(paths.out_entities, infer_schema=False)["Entity Type"].value_counts(
        sort=True)
    lines.append("entity types: " + ", ".join(f"{t}={n:,}" for t, n in types.iter_rows()))
    return lines
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: the whole suite passes, and ruff and mypy are clean. `test_fresh_build_passes` must print nothing; on failure it renders the report.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/validate.py tests/test_validate.py
git commit -m "feat: per-day invariant validator with distribution report and mutation tests

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Kaggle fetch

**Files:**
- Create: `garda_ai_dataset/fetch.py`
- Test: `tests/test_fetch.py`

- [ ] **Step 1: Write the failing tests**

```python
import base64
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from email.message import Message
from pathlib import Path

import pytest

from garda_ai_dataset.errors import FetchError, RawInputError
from garda_ai_dataset.fetch import run_fetch
from garda_ai_dataset.paths import dataset_paths

NAMES = ["HI-Small_Trans.csv", "HI-Small_accounts.csv", "HI-Small_Patterns.txt"]


def _creds(tmp_path: Path) -> Path:
    path = tmp_path / "kaggle.json"
    path.write_text(json.dumps({"username": "u", "key": "SECRETKEY"}))
    return path


def _file_name(request: urllib.request.Request) -> str:
    return request.full_url.rsplit("/", 1)[1]


def test_downloads_and_records_hashes(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    calls: list[urllib.request.Request] = []

    def opener(request: urllib.request.Request) -> io.BytesIO:
        calls.append(request)
        return io.BytesIO(f"payload {_file_name(request)}".encode())

    sums = run_fetch(paths, _creds(tmp_path), opener=opener)
    assert [_file_name(r) for r in calls] == NAMES
    assert calls[0].full_url.startswith(
        "https://www.kaggle.com/api/v1/datasets/download/"
        "ealtman2019/ibm-transactions-for-anti-money-laundering-aml/"
    )
    assert calls[0].get_header("Authorization") == "Basic " + base64.b64encode(
        b"u:SECRETKEY").decode()
    assert paths.raw_trans.read_bytes() == b"payload HI-Small_Trans.csv"
    assert sums["HI-Small_Trans.csv"] == hashlib.sha256(b"payload HI-Small_Trans.csv").hexdigest()
    assert "HI-Small_Patterns.txt" in paths.sha256sums.read_text()


def test_existing_files_are_adopted_without_credentials(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    paths.raw_dir.mkdir(parents=True)
    for name in NAMES:
        (paths.raw_dir / name).write_text(name)

    def opener(request: urllib.request.Request) -> io.BytesIO:
        raise AssertionError("must not download")

    sums = run_fetch(paths, tmp_path / "absent.json", opener=opener)
    assert set(sums) == set(NAMES)


def test_hash_mismatch_raises(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")
    paths.raw_dir.mkdir(parents=True)
    for name in NAMES:
        (paths.raw_dir / name).write_text(name)
    run_fetch(paths, tmp_path / "absent.json")
    paths.raw_trans.write_text("tampered")
    with pytest.raises(RawInputError, match="sha256"):
        run_fetch(paths, tmp_path / "absent.json")


def test_zip_payload_is_extracted(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    def opener(request: urllib.request.Request) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr(_file_name(request), f"zipped {_file_name(request)}")
        return io.BytesIO(buffer.getvalue())

    run_fetch(paths, _creds(tmp_path), opener=opener)
    assert paths.raw_accounts.read_text() == "zipped HI-Small_accounts.csv"
    assert not list(paths.raw_dir.glob("*.part"))


def test_http_error_never_leaks_the_key(tmp_path: Path) -> None:
    paths = dataset_paths(tmp_path, "small")

    def opener(request: urllib.request.Request) -> io.BytesIO:
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", Message(), None)

    with pytest.raises(FetchError) as exc:
        run_fetch(paths, _creds(tmp_path), opener=opener)
    assert "401" in str(exc.value)
    assert "SECRETKEY" not in str(exc.value)
    assert not list(paths.raw_dir.glob("*.part"))


def test_missing_credentials(tmp_path: Path) -> None:
    with pytest.raises(FetchError, match="credentials"):
        run_fetch(dataset_paths(tmp_path, "small"), tmp_path / "nope.json")


def test_incomplete_credentials(tmp_path: Path) -> None:
    path = tmp_path / "kaggle.json"
    path.write_text("{}")
    with pytest.raises(FetchError, match="username"):
        run_fetch(dataset_paths(tmp_path, "small"), path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_fetch.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.fetch'`.

- [ ] **Step 3: Implement `garda_ai_dataset/fetch.py`**

```python
"""Download the original IBM files from Kaggle, one file at a time (spec 7).

Credentials are read from kaggle.json and only ever placed in the Authorization header.
They are never logged, written, or included in error messages.
"""

import base64
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from garda_ai_dataset.errors import FetchError, RawInputError
from garda_ai_dataset.hashing import sha256_file
from garda_ai_dataset.paths import DatasetPaths

KAGGLE_DATASET = "ealtman2019/ibm-transactions-for-anti-money-laundering-aml"
DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/{dataset}/{file}"
ZIP_MAGIC = b"PK\x03\x04"
Opener = Callable[[urllib.request.Request], Any]  # urlopen-compatible context manager


def _urlopen(request: urllib.request.Request) -> Any:
    return urllib.request.urlopen(request, timeout=600)


def _authorization(kaggle_json: Path) -> str:
    try:
        data = json.loads(kaggle_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FetchError(
            f"Kaggle credentials not found at {kaggle_json} (set GARDA_KAGGLE_JSON or pass "
            "--kaggle-json)"
        ) from None
    except json.JSONDecodeError:
        raise FetchError(f"{kaggle_json} is not valid JSON") from None
    user = data.get("username") if isinstance(data, dict) else None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(user, str) or not isinstance(key, str) or not user or not key:
        raise FetchError(f"{kaggle_json} must contain non-empty 'username' and 'key'")
    return "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode("ascii")


def read_sums(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            sums[name.strip()] = digest
    return sums


def write_sums(path: Path, sums: dict[str, str]) -> None:
    path.write_text("".join(f"{sums[n]}  {n}\n" for n in sorted(sums)), encoding="utf-8")


def _download(target: Path, authorization: str, opener: Opener) -> None:
    url = DOWNLOAD_URL.format(dataset=KAGGLE_DATASET, file=target.name)
    request = urllib.request.Request(
        url, headers={"Authorization": authorization, "User-Agent": "garda-ai-dataset"}
    )
    part = target.with_name(target.name + ".part")
    try:
        with opener(request) as response, part.open("wb") as fh:
            shutil.copyfileobj(response, fh, 1 << 20)
    except urllib.error.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise FetchError(f"Kaggle returned HTTP {exc.code} for {target.name}") from None
    except urllib.error.URLError as exc:
        part.unlink(missing_ok=True)
        raise FetchError(f"could not reach Kaggle for {target.name}: {exc.reason}") from None
    with part.open("rb") as fh:
        is_zip = fh.read(4) == ZIP_MAGIC
    if not is_zip:
        part.replace(target)
        return
    with zipfile.ZipFile(part) as archive:
        member = next((n for n in archive.namelist() if Path(n).name == target.name), None)
        if member is None:
            part.unlink()
            raise FetchError(f"the zip Kaggle returned has no {target.name}")
        with archive.open(member) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    part.unlink()


def run_fetch(
    paths: DatasetPaths, kaggle_json: Path, *, opener: Opener | None = None
) -> dict[str, str]:
    """Ensure the three raw files exist, and record or verify their sha256 in SHA256SUMS."""
    paths.raw_dir.mkdir(parents=True, exist_ok=True)
    sums = read_sums(paths.sha256sums)
    authorization: str | None = None
    for target in (paths.raw_trans, paths.raw_accounts, paths.raw_patterns):
        if target.exists():
            actual = sha256_file(target)
            recorded = sums.get(target.name)
            if recorded is not None and recorded != actual:
                raise RawInputError(
                    f"{target} does not match its recorded sha256 in {paths.sha256sums.name}; "
                    "delete it and re-run fetch"
                )
            sums[target.name] = actual
            continue
        if authorization is None:
            authorization = _authorization(kaggle_json)
        _download(target, authorization, opener or _urlopen)
        sums[target.name] = sha256_file(target)
    write_sums(paths.sha256sums, sums)
    return sums
```

- [ ] **Step 4: Run the tests and tooling**

Run: `uv run pytest -q tests/test_fetch.py && uv run ruff check . && uv run mypy garda_ai_dataset`
Expected: `7 passed`, then ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/fetch.py tests/test_fetch.py
git commit -m "feat: per-file Kaggle fetch with SHA256SUMS and zip handling

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: CLI

**Files:**
- Create: `garda_ai_dataset/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

import pytest

import garda_ai_dataset.localize as localize_mod
from garda_ai_dataset.cli import default_legacy_accounts, main
from garda_ai_dataset.paths import DatasetPaths


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_cli.py`
Expected: a collection ERROR, `ModuleNotFoundError: No module named 'garda_ai_dataset.cli'`.

- [ ] **Step 3: Implement `garda_ai_dataset/cli.py`**

```python
"""`garda-dataset fetch|localize|validate|all --dataset small|medium`."""

import argparse
import os
import sys
from pathlib import Path

from garda_ai_dataset.errors import DatasetError, ValidationFailed
from garda_ai_dataset.fetch import run_fetch
from garda_ai_dataset.localize import run_localize
from garda_ai_dataset.mappings import Mappings, load_mappings
from garda_ai_dataset.paths import SIZES, DatasetPaths, dataset_paths
from garda_ai_dataset.validate import validate_dataset

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT.parent / "garda-ai-data"
DEFAULT_KAGGLE_JSON = Path("~/.kaggle/kaggle.json")
COMMANDS = {
    "fetch": "download the original IBM files from Kaggle",
    "localize": "build the localized dataset, then validate it",
    "validate": "re-run the invariant checks on an existing build",
    "all": "fetch, localize and validate",
}


def default_legacy_accounts(data_root: Path, size: str) -> Path | None:
    """The old hand-made HI-Small copy, whose risk columns are carried over (spec 5)."""
    if size != "small":
        return None
    path = data_root / "HI-Small" / "HI-Small_accounts.csv"
    return path if path.exists() else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="garda-dataset", description="Localize the IBM AML HI datasets for Indonesia."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--dataset", choices=sorted(SIZES), required=True)
        cmd.add_argument(
            "--data-root",
            type=Path,
            default=Path(os.environ.get("GARDA_DATA_ROOT", str(DEFAULT_DATA_ROOT))),
        )
        if name in ("fetch", "all"):
            cmd.add_argument(
                "--kaggle-json",
                type=Path,
                default=Path(os.environ.get("GARDA_KAGGLE_JSON", str(DEFAULT_KAGGLE_JSON))),
            )
        if name in ("localize", "all"):
            cmd.add_argument(
                "--legacy-accounts",
                type=Path,
                default=None,
                help="accounts CSV whose risk_score/risk_category are carried over "
                "(default for small: <data-root>/HI-Small/HI-Small_accounts.csv if present)",
            )
            cmd.add_argument("--no-legacy", action="store_true",
                             help="leave risk_score/risk_category empty")
    return parser


def _validate(paths: DatasetPaths, maps: Mappings) -> None:
    report = validate_dataset(paths, maps)
    print(report.render())
    if not report.ok:
        raise ValidationFailed(f"{paths.name}: failed checks {report.failed()}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = args.data_root.expanduser()
    paths = dataset_paths(data_root, args.dataset)
    try:
        maps = load_mappings()
        if args.command in ("fetch", "all"):
            run_fetch(paths, args.kaggle_json.expanduser())
            print(f"raw files ready in {paths.raw_dir}")
        if args.command in ("localize", "all"):
            legacy = None if args.no_legacy else (
                args.legacy_accounts or default_legacy_accounts(data_root, args.dataset)
            )
            if args.dataset == "small" and legacy is None and not args.no_legacy:
                print("warning: no legacy accounts file; risk columns will be empty",
                      file=sys.stderr)
            manifest = run_localize(paths, maps, legacy)
            print(f"wrote {paths.out_dir} in {manifest['wall_time_s']}s")
        if args.command in ("localize", "validate", "all"):
            _validate(paths, maps)
    except DatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the whole suite and tooling**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy garda_ai_dataset && uv run garda-dataset --help`
Expected: all tests pass, ruff and mypy are clean, and the help text lists `fetch`, `localize`, `validate` and `all`.

- [ ] **Step 5: Commit**

```bash
git add garda_ai_dataset/cli.py tests/test_cli.py
git commit -m "feat: garda-dataset CLI with spec exit codes

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# garda-ai-dataset

A deterministic, validated localization of IBM's synthetic AML data (AMLworld,
[Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml),
NeurIPS 2023) into Indonesian terms. It covers **HI-Small** (used by the platform demo) and
**HI-Medium** (used for training).

The design and its reasoning are in
`docs/superpowers/specs/2026-10-16-hi-dataset-localization-design.md`.

## Quick start

```bash
uv sync
make all DATASET=small KAGGLE_JSON=/path/to/kaggle.json    # fetch + localize + validate
make all DATASET=medium KAGGLE_JSON=/path/to/kaggle.json   # ~3.2 GB download
```

- **Output** goes to `../garda-ai-data/HI-<Size>-ID/`. Override the location with `GARDA_DATA_ROOT` or `--data-root`.
- **Raw files** are stored in `../garda-ai-data/raw/HI-<Size>/`, alongside a `SHA256SUMS` file.
- **Re-runs are byte-identical**, except for the timestamps in `MANIFEST.json`.

## What changes, and what never does

| Kept exactly | Changed |
|---|---|
| Graph topology `(bank, account)` → `(bank, account)`, edge order, every `Is Laundering` label | Amounts converted to IDR at one fixed rate per currency (2025-09-04); never capped |
| Row count and rows per day | Payment formats renamed one-to-one to Indonesian channels (`ACH` → `BI-FAST`, …) |
| Day of week (dates shift by exactly 157 weeks) | Bank IDs keep their identity; names become real Indonesian institutions |
| | Entity names become Indonesian; the type comes from IBM's own prefix (PT/CV/UD/Lembaga/Perorangan) |

Every rule is a CSV in `mappings/`. Edit the CSV, re-run, and the manifest records the new hash.

## Outputs

- `HI-<X>_Trans_sorted.csv`: the same 11 columns as IBM, sorted by time. `transaction_id` is the 1-based row number.
- `HI-<X>_accounts.csv`: the same header as before. `risk_score` and `risk_category` are a transitional carry-over for Small and empty for Medium; real values come from the model.
- `HI-<X>_entities.csv`: entity type, province, city, registration date, KYC status and sector. These are **synthetic, display-only** fields for the Users tab and are never model features.
- `HI-<X>_typologies.csv`: the true IBM motif of each laundering transaction, or `UNATTRIBUTED`.
- `HI-<X>_Patterns.txt`: IBM's pattern file, re-expressed with the localized rows.
- `MANIFEST.json`: input, mapping and output hashes, counts and typology coverage.

## Validation

`localize` always ends with `validate`, which re-derives every invariant from the raw files and fails the build on any violation:
- row count, labels, graph keys and node merges;
- FX, time shift, order and channels;
- label independence: inverting every label must leave every non-label output byte-identical;
- patterns, entities, and manifest hashes.

## Using it on the platform

In `garda-ai-deploy/.env`, set `GARDA_DATA_HOST_DIR=../garda-ai-data/HI-Small-ID`, then reseed:
`make down`, `docker compose down -v`, `make up`, then `make demo-seed`.

The demo row offsets still land on day boundaries, because the number of rows per day is unchanged. The calendar dates move from Sep 3–9 to Sep 6–12.

## Honest framing for judges

> Synthetic data. Graph topology and laundering labels come from IBM AMLworld (NeurIPS 2023).
> Indonesian channels, institutions and currency are mapped with documented, verifiable rules.
> No real customer data is used, in line with UU PDP and bank secrecy. A production system would
> be trained on partner-bank data under an MoU.

QRIS, e-wallets and Indonesia-specific typologies (judi online, mule fan-in, pig-butchering) are not in this version. They are planned as a separate, injected-typology dataset.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with usage, guarantees, outputs and judge framing

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Real HI-Small build and consumer smoke tests

The raw HI-Small files are already in `../garda-ai-data/raw/HI-Small/`; they were downloaded on 2026-10-16. `fetch` adopts them and records their hashes without downloading. The user's Kaggle credentials are at `../../kaggle.json`, relative to this repo.

**Files:** no code changes, unless a defect is found. In that case, fix it with a test first, then commit.

- [ ] **Step 1: Build and validate HI-Small**

Run: `/usr/bin/time -l make all DATASET=small KAGGLE_JSON="$(cd ../.. && pwd)/kaggle.json" 2>&1 | tail -40`

Expected:
- Every check line reads `PASS`, and the process exits 0.
- `maximum resident set size` is printed by `time`; record it.

Then inspect the manifest:

```bash
python3 -c "import json; m=json.load(open('../garda-ai-data/HI-Small-ID/MANIFEST.json')); print(json.dumps({k: m[k] for k in ('counts','typology','risk_source','wall_time_s')}, indent=2))"
```

The expected values:
- `counts.transactions` = 5078345
- `counts.laundering` = 5177
- `counts.days` = 18
- `counts.first_day` = "2025-09-04"
- `counts.last_day` = "2025-09-21"
- `counts.banks` = 30470
- `typology.attempts` = 370
- `typology.pattern_rows` = 3209
- `typology.matched_rows` = 3209
- `typology.unmatched_pattern_rows` = 0
- `typology.laundering_coverage` = 0.6199
- `risk_source` = "legacy-carryover"

If any value differs, stop and report it. Do not adjust the expectation.

- [ ] **Step 2: Sim reader smoke test** (read-only use of `garda-ai-sim`)

```bash
cd ../garda-ai-sim && uv run python - <<'EOF'
from garda_ai_sim.reader import stream_transactions
rows = list(stream_transactions(["../garda-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv"], limit=1000))
assert len(rows) == 1000 and rows[0].ordinal == 1
assert rows[0].fields["payment_currency"] == "IDR"
print("sim OK", rows[0].csv_ts, rows[0].fields)
EOF
```

Expected: `sim OK 2025-09-04 00:... {...'payment_currency': 'IDR'...}`.

- [ ] **Step 3: Ingest seed parser smoke test** (read-only use of `garda-ai-ingest`; a fake DB connection)

```bash
cd ../garda-ai-ingest && uv run python - <<'EOF'
import asyncio
from garda_ai_ingest.seed.reference import load_reference

class FakeConn:
    async def executemany(self, sql, rows):
        return None

print("ingest OK", asyncio.run(load_reference(FakeConn(), "../garda-ai-data/HI-Small-ID/HI-Small_accounts.csv")))
EOF
```

Expected: `ingest OK LoadCounts(banks=30470, entities=..., accounts=...)`. The account count must equal `counts.accounts` in the manifest.

- [ ] **Step 4: Multi-GNN formatter smoke test** (read-only use of the training repo; output goes to the scratchpad)

```bash
SCRATCH="/private/tmp/claude-501/-Users-thariqiskandar-Documents-Career-BI---OJK-Hackathon-2025-repositories/b70070dc-9509-41ba-95d0-3323e1dfe92a/scratchpad/mgnn-smoke"
mkdir -p "$SCRATCH" && head -100001 ../garda-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv > "$SCRATCH/HI-Small_Trans.csv"
cd ../workspace/garda-ai-fraud-scorer-model && uv run --no-project --python 3.11 --with "datatable==1.1.0" --with numpy python format_kaggle_files.py "$SCRATCH/HI-Small_Trans.csv"
head -3 "$SCRATCH/formatted_transactions.csv" && wc -l "$SCRATCH/formatted_transactions.csv"
```

Expected: a header plus 100,000 rows (`100001` lines).

If `datatable==1.1.0` cannot be installed on this machine (no wheel for the platform or Python version), do not work around it. Report the exact install error as a concern.

- [ ] **Step 5: Confirm nothing outside this repo changed**

Run: `for r in garda-ai-sim garda-ai-ingest garda-ai-deploy workspace/garda-ai-fraud-scorer-model; do echo "== $r"; git -C "../$r" status --short; done`

Expected:
- **sim, ingest and deploy:** no output.
- **fraud-scorer:** only its pre-existing ` M inference.py` and the untracked `checkpoints/`, `__pycache__/` and `.DS_Store`.

- [ ] **Step 6: Record the results**

Append a "Verified builds" section to `README.md` with:
- the Small manifest counts;
- wall time;
- peak RSS;
- the three smoke-test outcomes.

Then commit:

```bash
git add README.md
git commit -m "docs: record verified HI-Small build and consumer smoke tests

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Real HI-Medium build

This downloads about 3.2 GB. The machine has about 65 GB free and 16 GB of RAM. Run it in the background and wait for it to finish.

- [ ] **Step 1: Fetch, build and validate**

Run (background): `/usr/bin/time -l make all DATASET=medium KAGGLE_JSON="$(cd ../.. && pwd)/kaggle.json" > ../garda-ai-data/medium-build.log 2>&1`

Expected:
- Exit 0, with every check `PASS` at the end of the log.
- **If it exits 3** (vocabulary): the log names the missing currency or format. Add the row to the right mapping CSV:
  - a currency needs a rate for 2025-09-04 from the same sources as `fx_rates.csv`;
  - a format needs a one-to-one channel.

  Commit it as `feat: add mapping for <value> found in HI-Medium`, then re-run.
- **If it is killed for memory**, report the peak RSS and the day that was being processed. Do not change the algorithm without asking.

- [ ] **Step 2: Record the results**

Read `../garda-ai-data/HI-Medium-ID/MANIFEST.json`. Append the Medium numbers to the README's "Verified builds" section:
- counts;
- typology coverage;
- wall time;
- peak RSS.

Commit:

```bash
git add README.md
git commit -m "docs: record verified HI-Medium build

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes (author)

**Spec coverage:**
- §4 layout: Tasks 1–2.
- §5 outputs and manifest: Task 7.
- §6.1 rules: transactions refuses the label; tested in Tasks 3 and 7.
- §6.2: Task 3.
- §6.3: Task 4.
- §6.4: Task 5.
- §6.5: Task 6.
- §7 fetch: Task 9.
- §8 validation:
  - checks 1–6: Task 8 (row checks);
  - check 7: label independence;
  - check 8: patterns;
  - check 9: entities;
  - check 10: manifest;
  - the distribution report.
- §9 two-pass per-day processing: Tasks 7 and 8.
- §10 exit codes: Tasks 1 and 10.
- §11 tests: every task.
- §12 acceptance: Tasks 12–13.

**Known trade-offs, accepted:**
- The validator shares `to_idr` with the transform. That function is unit-tested against `Decimal` in Task 3, so a bug in it would still be caught.
- The `node_merge` check compares global counts, not per-row keys. Per-row keys are covered by `graph_keys`.
