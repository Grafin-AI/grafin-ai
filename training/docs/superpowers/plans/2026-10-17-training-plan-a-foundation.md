# grafin-ai-training — Plan A: Foundation + Paper Protocol

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested, reproducible port of IBM Multi-GNN that runs the paper protocol on raw and localized IBM AML data on Mac (CPU) and a 4×T4 GCP VM (CUDA), producing Wave 1 parity results.

**Architecture:** uv package `grafin_training` with IBM's `models.py` vendored byte-for-byte and everything around it rebuilt as small modules: data (read/verify, node ids, split, features, cached `prepare`), graph (vectorised ports/time deltas, PyG graphs, loaders), train (paper protocol, training loop with resume), tracking (run dirs + MLflow SQLite), CLI, and GCP ops scripts. Plan B (causal protocol, heads, ONNX bundle) builds on this.

**Tech Stack:** Python 3.11 · torch 2.5.1 · torch_geometric 2.6.1 · pyg-lib 0.4.0 · polars 2.0.0 · numpy 2.x · scikit-learn · mlflow-skinny 3.17.1 (SQLite) · uv · ruff · mypy --strict · pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-training-repo-design.md` (§15 lists facts verified while planning).

---

## Ground rules for the implementer

- Repo: `repositories/grafin-ai-training` (git, branch `main`, no remote). **Work on branch `feat/plan-a-foundation`** (`git checkout -b feat/plan-a-foundation`). Never push.
- Commit author is preconfigured in the repo (`Thariq Iskandar Zulkarnain M P <thariqiskandar9@gmail.com>`). Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- **Every code block in this plan was executed while planning** (42 tests, ruff, mypy --strict green; real HI-Small run). Write files exactly as given. If something fails, stop and report the exact output rather than improvising.
- Downloads (`LICENSE`, `models.py`) come from IBM's GitHub at commit `252b0252afca109d1d216c411c59ff70753b25fc` and must match the sha256 values given.
- Data lives next to the repo in `../grafin-ai-data` (read-only for this plan).
- Linux only: every `uv sync` / `uv run` needs `--extra cpu` or `--extra cu124` (the Makefile handles this via `EXTRA=`). On the Mac use plain `uv`.

## File map

| File | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock`, `.python-version` | pinned stack; platform-specific torch / pyg-lib sources |
| `Makefile`, `.github/workflows/ci.yml` | install / lint / typecheck / test / smoke |
| `LICENSE`, `NOTICE`, `README.md` | Apache-2.0 + IBM attribution; usage and GPU runbook |
| `configs/paper_pna.toml` | upstream Multi-PNA+EU hyper-parameters |
| `grafin_training/errors.py` | exit-code taxonomy |
| `grafin_training/device.py` | cpu / mps / cuda resolution |
| `grafin_training/config.py` | typed TOML config with strict validation and overrides |
| `grafin_training/models/multignn.py` | IBM `models.py`, verbatim |
| `grafin_training/data/load.py` | read raw/ID CSV → canonical frame; sha256 verification |
| `grafin_training/data/nodes.py` | (bank, account) → node ids |
| `grafin_training/data/split.py` | paper day split, calibration split |
| `grafin_training/data/features.py` | paper edge features, codebooks, train-only normalisation |
| `grafin_training/data/prepare.py` | cached, race-safe dataset preparation |
| `grafin_training/graph/build.py` | ports, time deltas, PyG graphs, paper split graphs |
| `grafin_training/graph/loaders.py` | LinkNeighborLoader, ego IDs, seed masks |
| `grafin_training/train/paper.py` | paper-protocol inputs |
| `grafin_training/train/gnn.py` | training loop, checkpoints, resume |
| `grafin_training/tracking.py` | run directories, MLflow |
| `grafin_training/report.py`, `grafin_training/cli.py` | `grafin-train prepare / gnn / compare` |
| `ops/*` | GCP VM create/setup, GCS sync, one-job-per-GPU runner, job files |
| `tests/fixture.py`, `tests/conftest.py` | synthetic dataset in both formats |
| `tests/upstream_ref.py` | verbatim upstream code used as an oracle |

---

### Task 1: Scaffold, pinned toolchain and exit codes

Create the uv project with the platform-specific PyTorch / PyG wheels that were verified to lock for macOS arm64, Linux CPU (CI) and Linux CUDA 12.4 (the T4 VM). `pyg-lib` provides the neighbour sampler; it comes from direct wheel URLs because PyPI has none. The Mac must use an **arm64** Python (an x86_64 3.11 is also installed for the Rosetta datatable formatter), hence `.python-version`. The Makefile's `smoke` targets reference commands built in later tasks; that is expected. `errors.py` fixes the exit-code taxonomy from spec §10.

**Files:**
- Create: `tests/test_errors.py`
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `NOTICE`
- Create: `Makefile`
- Create: `.github/workflows/ci.yml`
- Create: `grafin_training/errors.py`
- Create: `README.md`
- Create: `grafin_training/__init__.py`
- Create: `tests/__init__.py`
- Create: `LICENSE`

- [ ] **Step 1: Write the failing tests**

`tests/test_errors.py`:

```python
from __future__ import annotations

from grafin_training.errors import (
    ConfigError,
    CudaUnavailableError,
    DatasetError,
    ExportCheckError,
    GrafinTrainError,
    TrainingDivergedError,
)


def test_exit_codes() -> None:
    assert GrafinTrainError.exit_code == 1
    assert DatasetError.exit_code == 2
    assert ConfigError.exit_code == 3
    assert ExportCheckError.exit_code == 4
    assert CudaUnavailableError.exit_code == 5
    assert TrainingDivergedError.exit_code == 1
```

- [ ] **Step 2: (Runs after the scaffold exists — see Step 4.)**

- [ ] **Step 3: Download upstream files (do not retype)**

```bash
curl -fsSL https://raw.githubusercontent.com/IBM/Multi-GNN/252b0252afca109d1d216c411c59ff70753b25fc/LICENSE -o LICENSE
shasum -a 256 LICENSE   # expect c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4
```

- [ ] **Step 4: Write the implementation**

`pyproject.toml`:

```toml
[project]
name = "grafin-ai-training"
version = "0.1.0"
description = "Grafin AI fraud-scorer training: Multi-GNN port, causal evaluation, model bundle export"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = "==3.11.*"
dependencies = [
  "torch==2.5.1",
  "torch_geometric==2.6.1",
  "pyg-lib==0.4.0; sys_platform == 'darwin'",
  "numpy>=2.0,<2.3",
  "polars==2.0.0",
  "pyarrow>=18",
  "scikit-learn>=1.5,<1.8",
  "mlflow-skinny==3.17.1",
  "sqlalchemy>=2.0,<2.1",
  "alembic>=1.13",
]

[project.optional-dependencies]
cpu = ["torch==2.5.1", "pyg-lib==0.4.0; sys_platform == 'linux'"]
cu124 = ["torch==2.5.1", "pyg-lib==0.4.0; sys_platform == 'linux'"]

[project.scripts]
grafin-train = "grafin_training.cli:run"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.8", "mypy>=1.13"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["grafin_training"]

[tool.uv]
environments = [
  "sys_platform == 'darwin' and platform_machine == 'arm64'",
  "sys_platform == 'linux' and platform_machine == 'x86_64'",
]
conflicts = [[{ extra = "cpu" }, { extra = "cu124" }]]

[tool.uv.sources]
torch = [
  { index = "pytorch-cpu", extra = "cpu", marker = "sys_platform == 'linux'" },
  { index = "pytorch-cu124", extra = "cu124", marker = "sys_platform == 'linux'" },
]
pyg-lib = [
  { url = "https://data.pyg.org/whl/torch-2.5.0%2Bcpu/pyg_lib-0.4.0%2Bpt25-cp311-cp311-macosx_14_0_universal2.whl", marker = "sys_platform == 'darwin'" },
  { url = "https://data.pyg.org/whl/torch-2.5.0%2Bcpu/pyg_lib-0.4.0%2Bpt25cpu-cp311-cp311-linux_x86_64.whl", extra = "cpu", marker = "sys_platform == 'linux'" },
  { url = "https://data.pyg.org/whl/torch-2.5.0%2Bcu124/pyg_lib-0.4.0%2Bpt25cu124-cp311-cp311-linux_x86_64.whl", extra = "cu124", marker = "sys_platform == 'linux'" },
]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[[tool.uv.index]]
name = "pytorch-cu124"
url = "https://download.pytorch.org/whl/cu124"
explicit = true

[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["grafin_training/models/multignn.py", "tests/upstream_ref.py"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["grafin_training"]
exclude = ["grafin_training/models/multignn\\.py$"]

[[tool.mypy.overrides]]
module = ["torch_geometric.*", "sklearn.*", "mlflow.*", "pyg_lib.*", "grafin_training.models.multignn"]
ignore_missing_imports = true
follow_imports = "skip"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.python-version`:

```text
cpython-3.11-macos-aarch64-none
```

`.gitignore`:

```text
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.DS_Store
cache/
runs/
mlruns/
bundles/
data/
.smoke/
ops/*.env
```

`NOTICE`:

```text
grafin-ai-training
Copyright 2026 Meaningful Intelligence (Grafin AI)

This product includes software developed by IBM as part of Multi-GNN
(https://github.com/IBM/Multi-GNN, commit 252b0252afca109d1d216c411c59ff70753b25fc),
licensed under the Apache License, Version 2.0:

- grafin_training/models/multignn.py is a verbatim copy of upstream models.py.
- tests/upstream_ref.py contains verbatim copies of upstream data_util.py functions and the
  split block of data_loading.py, used only as a test oracle.
- grafin_training/graph/ and grafin_training/train/gnn.py are adapted from upstream
  data_util.py, train_util.py and training.py.

Reference: Egressy et al., "Provably Powerful Graph Neural Networks for Directed Multigraphs",
AAAI 2024 (arXiv:2306.11586).
```

`Makefile`:

```makefile
# grafin-ai-training — common tasks. Linux needs EXTRA=cpu (CI) or EXTRA=cu124 (GPU VM).
EXTRA ?=
SYNC_FLAGS = $(if $(EXTRA),--extra $(EXTRA),)
# `uv run` re-syncs the environment: pass the same extra so CUDA/CPU torch is kept.
RUN = uv run $(SYNC_FLAGS)
DATA_ROOT ?= ../grafin-ai-data
SMOKE_DIR ?= .smoke

.PHONY: install lint typecheck test check smoke smoke-small compare clean-smoke

install:
	uv sync $(SYNC_FLAGS)

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest -q

check: lint typecheck test

# End-to-end on the synthetic fixture (CPU, ~10 s).
smoke: clean-smoke
	$(RUN) python tests/fixture.py $(SMOKE_DIR)/fixture
	$(RUN) grafin-train gnn --data $(SMOKE_DIR)/fixture/raw/HI-Fixture_Trans.csv --source raw \
		--epochs 2 --batch-size 32 --num-neighs 10 10 --device cpu \
		--runs-dir $(SMOKE_DIR)/runs --cache-dir $(SMOKE_DIR)/cache --no-mlflow
	$(RUN) grafin-train compare --runs-dir $(SMOKE_DIR)/runs

# Real HI-Small-ID, paper settings, 3 batches per loader (CPU, ~4-6 min on an M2).
smoke-small:
	$(RUN) grafin-train gnn --data $(DATA_ROOT)/HI-Small-ID/HI-Small_Trans_sorted.csv --source id \
		--epochs 1 --max-batches 3 --device cpu --runs-dir $(SMOKE_DIR)/runs \
		--cache-dir cache --no-mlflow

compare:
	$(RUN) grafin-train compare --runs-dir runs

clean-smoke:
	rm -rf $(SMOKE_DIR)
```

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
  pull_request:
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.11
      - run: make install EXTRA=cpu
      - run: make check
      - run: make smoke
```

`grafin_training/errors.py`:

```python
"""Exit-code taxonomy (spec §10). Every user-facing failure raises a subclass."""

from __future__ import annotations


class GrafinTrainError(Exception):
    """Base class; exit code 1 (unexpected / training failure)."""

    exit_code = 1


class DatasetError(GrafinTrainError):
    """Dataset missing or unreadable, or its sha256 does not match the manifest."""

    exit_code = 2


class ConfigError(GrafinTrainError):
    """Invalid configuration or CLI arguments."""

    exit_code = 3


class ExportCheckError(GrafinTrainError):
    """A model-bundle self-check failed (Plan B)."""

    exit_code = 4


class CudaUnavailableError(GrafinTrainError):
    """--device cuda was requested but CUDA is not available."""

    exit_code = 5


class TrainingDivergedError(GrafinTrainError):
    """The training loss became NaN or infinite; the last good checkpoint is kept."""

    exit_code = 1
```

`README.md`:

```markdown
# grafin-ai-training

Work in progress. Design: docs/superpowers/specs/2026-10-17-training-repo-design.md
```

`grafin_training/__init__.py`:

```python
"""Grafin AI fraud-scorer training (Multi-GNN port, causal evaluation, model bundle)."""
```

`tests/__init__.py`:

```python

```

- [ ] **Step 5: Lock and install**

```bash
uv lock
uv sync
uv run python -c "import torch, torch_geometric.typing as t; assert t.WITH_PYG_LIB; print(torch.__version__, 'pyg-lib ok')"
```
Expected: lock resolves for darwin-arm64 and linux-x86_64; last line prints `2.5.1 pyg-lib ok`.

- [ ] **Step 6: Verify**

Run: `uv run pytest tests/test_errors.py -q`
Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci.yml .gitignore .python-version LICENSE Makefile NOTICE README.md grafin_training/__init__.py grafin_training/errors.py pyproject.toml tests/__init__.py tests/test_errors.py uv.lock
git commit -m "chore: scaffold uv project, pinned torch/PyG stack, exit codes" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 2: Vendor the upstream model and the test oracle

`grafin_training/models/multignn.py` must be **byte-identical** to IBM's `models.py` at commit 252b025 (download it, never retype it). `tests/upstream_ref.py` holds verbatim upstream functions (ports, time deltas, adjacency, z_norm, and the split block of `data_loading.get_data` wrapped in a function) used only as an oracle in later tests. Both files are excluded from ruff and mypy in `pyproject.toml`.

**Files:**
- Create: `tests/test_vendored_model.py`
- Create: `tests/upstream_ref.py`
- Create: `grafin_training/models/__init__.py`
- Create: `grafin_training/models/multignn.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_vendored_model.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

import torch

from grafin_training.models.multignn import PNA

UPSTREAM_SHA256 = "00ef7142e81d3080114142106867e6ef3002d5a01ff5474e9f75cab957fcefe7"
VENDORED = Path(__file__).resolve().parents[1] / "grafin_training" / "models" / "multignn.py"


def test_vendored_models_file_is_byte_identical_to_upstream() -> None:
    assert hashlib.sha256(VENDORED.read_bytes()).hexdigest() == UPSTREAM_SHA256


def test_pna_forward_shape() -> None:
    torch.manual_seed(0)
    edge_index = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 0]])
    model = PNA(
        num_features=2,
        num_gnn_layers=2,
        n_hidden=20,
        edge_updates=True,
        edge_dim=6,
        deg=torch.tensor([0, 4]),
        final_dropout=0.0,
    )
    out = model(torch.zeros(4, 2), edge_index, torch.randn(4, 6))
    assert out.shape == (4, 2)
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_vendored_model.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_vendored_model.py`).

- [ ] **Step 3: Download upstream files (do not retype)**

```bash
mkdir -p grafin_training/models
curl -fsSL https://raw.githubusercontent.com/IBM/Multi-GNN/252b0252afca109d1d216c411c59ff70753b25fc/models.py -o grafin_training/models/multignn.py
shasum -a 256 grafin_training/models/multignn.py   # expect 00ef7142e81d3080114142106867e6ef3002d5a01ff5474e9f75cab957fcefe7
```

- [ ] **Step 4: Write the implementation**

`tests/upstream_ref.py`:

```python
"""Oracle: functions copied VERBATIM from IBM/Multi-GNN@252b0252afca109d1d216c411c59ff70753b25fc
(Apache-2.0) — data_util.py (adjacency, ports, time_deltas, z_norm) and the split block of
data_loading.get_data wrapped in a function. Used only by tests to prove the port is faithful.
Do not edit the function bodies."""

import itertools

import numpy as np
import torch
from torch_geometric.data import HeteroData


def to_adj_nodes_with_times(data):
    num_nodes = data.num_nodes
    timestamps = torch.zeros((data.edge_index.shape[1], 1)) if data.timestamps is None else data.timestamps.reshape((-1,1))
    edges = torch.cat((data.edge_index.T, timestamps), dim=1) if not isinstance(data, HeteroData) else torch.cat((data['node', 'to', 'node'].edge_index.T, timestamps), dim=1)
    adj_list_out = dict([(i, []) for i in range(num_nodes)])
    adj_list_in = dict([(i, []) for i in range(num_nodes)])
    for u,v,t in edges:
        u,v,t = int(u), int(v), int(t)
        adj_list_out[u] += [(v, t)]
        adj_list_in[v] += [(u, t)]
    return adj_list_in, adj_list_out

def to_adj_edges_with_times(data):
    num_nodes = data.num_nodes
    timestamps = torch.zeros((data.edge_index.shape[1], 1)) if data.timestamps is None else data.timestamps.reshape((-1,1))
    edges = torch.cat((data.edge_index.T, timestamps), dim=1)
    # calculate adjacent edges with times per node
    adj_edges_out = dict([(i, []) for i in range(num_nodes)])
    adj_edges_in = dict([(i, []) for i in range(num_nodes)])
    for i, (u,v,t) in enumerate(edges):
        u,v,t = int(u), int(v), int(t)
        adj_edges_out[u] += [(i, v, t)]
        adj_edges_in[v] += [(i, u, t)]
    return adj_edges_in, adj_edges_out

def ports(edge_index, adj_list):
    ports = torch.zeros(edge_index.shape[1], 1)
    ports_dict = {}
    for v, nbs in adj_list.items():
        if len(nbs) < 1: continue
        a = np.array(nbs)
        a = a[a[:, -1].argsort()]
        _, idx = np.unique(a[:,[0]],return_index=True,axis=0)
        nbs_unique = a[np.sort(idx)][:,0]
        for i, u in enumerate(nbs_unique):
            ports_dict[(u,v)] = i
    for i, e in enumerate(edge_index.T):
        ports[i] = ports_dict[tuple(e.numpy())]
    return ports

def time_deltas(data, adj_edges_list):
    time_deltas = torch.zeros(data.edge_index.shape[1], 1)
    if data.timestamps is None:
        return time_deltas
    for v, edges in adj_edges_list.items():
        if len(edges) < 1: continue
        a = np.array(edges)
        a = a[a[:, -1].argsort()]
        a_tds = [0] + [a[i+1,-1] - a[i,-1] for i in range(a.shape[0]-1)]
        tds = np.hstack((a[:,0].reshape(-1,1), np.array(a_tds).reshape(-1,1)))
        for i,td in tds:
            time_deltas[i] = td
    return time_deltas

def z_norm(data):
    std = data.std(0).unsqueeze(0)
    std = torch.where(std == 0, torch.tensor(1, dtype=torch.float32).cpu(), std)
    return (data - data.mean(0).unsqueeze(0)) / std

def paper_split_days(daily_trans):
    split_per = [0.6, 0.2, 0.2]
    daily_totals = np.array(daily_trans)
    d_ts = daily_totals
    I = list(range(len(d_ts)))
    split_scores = dict()
    for i,j in itertools.combinations(I, 2):
        if j >= i:
            split_totals = [d_ts[:i].sum(), d_ts[i:j].sum(), d_ts[j:].sum()]
            split_totals_sum = np.sum(split_totals)
            split_props = [v/split_totals_sum for v in split_totals]
            split_error = [abs(v-t)/t for v,t in zip(split_props, split_per)]
            score = max(split_error) #- (split_totals_sum/total) + 1
            split_scores[(i,j)] = score
        else:
            continue

    i,j = min(split_scores, key=split_scores.get)
    #split contains a list for each split (train, validation and test) and each list contains the days that are part of the respective split
    split = [list(range(i)), list(range(i, j)), list(range(j, len(daily_totals)))]
    return split
```

`grafin_training/models/__init__.py`:

```python

```

- [ ] **Step 5: Verify**

Run: `uv run pytest tests/test_vendored_model.py -q`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add grafin_training/models/__init__.py grafin_training/models/multignn.py tests/test_vendored_model.py tests/upstream_ref.py
git commit -m "feat: vendor IBM Multi-GNN models.py verbatim plus upstream test oracle" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 3: Device resolution and typed GNN config

`resolve_device('auto')` picks CUDA or CPU, never MPS (PyG scatter ops are not reliable there; MPS is opt-in). Requesting CUDA without it exits 5 so the VM never silently trains on CPU. `configs/paper_pna.toml` carries upstream's PNA hyper-parameters and flags exactly; `load_gnn_config` rejects unknown/missing keys and wrong types (exit 3) and accepts `section.key` overrides from the CLI.

**Files:**
- Create: `tests/test_device.py`
- Create: `tests/test_config.py`
- Create: `grafin_training/device.py`
- Create: `grafin_training/config.py`
- Create: `configs/paper_pna.toml`

- [ ] **Step 1: Write the failing tests**

`tests/test_device.py`:

```python
from __future__ import annotations

import pytest
import torch

from grafin_training.device import resolve_device
from grafin_training.errors import ConfigError, CudaUnavailableError


def test_resolve_device_cpu_and_unknown() -> None:
    assert resolve_device("cpu") == torch.device("cpu")
    with pytest.raises(ConfigError):
        resolve_device("tpu")


@pytest.mark.skipif(torch.cuda.is_available(), reason="needs a machine without CUDA")
def test_cuda_requested_without_cuda() -> None:
    with pytest.raises(CudaUnavailableError):
        resolve_device("cuda")
    assert resolve_device("auto") == torch.device("cpu")
```

`tests/test_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from grafin_training.config import load_gnn_config
from grafin_training.errors import ConfigError

PAPER = Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml"


def test_paper_config_matches_upstream() -> None:
    cfg = load_gnn_config(PAPER)
    assert cfg.model.name == "pna" and cfg.model.n_hidden == 20 and cfg.model.n_gnn_layers == 2
    assert cfg.model.dropout == 0.08340440094051481
    assert cfg.model.final_dropout == 0.28812979737686323
    assert cfg.model.edge_updates
    assert (cfg.flags.reverse_mp, cfg.flags.ports, cfg.flags.ego, cfg.flags.tds) == (
        True,
        True,
        True,
        False,
    )
    assert cfg.train.lr == 0.0006116418195373612
    assert (cfg.train.w_ce1, cfg.train.w_ce2) == (1.0003967674742307, 7.077633468006714)
    assert (cfg.train.epochs, cfg.train.batch_size, cfg.train.num_neighs) == (100, 8192, (100, 100))
    assert cfg.split.fractions == (0.6, 0.2, 0.2)


def test_overrides_apply() -> None:
    cfg = load_gnn_config(PAPER, {"train.epochs": 2, "train.num_neighs": [5, 5]})
    assert cfg.train.epochs == 2 and cfg.train.num_neighs == (5, 5)


@pytest.mark.parametrize(
    "edit, message",
    [
        (("model", "name", "gin"), "name must be one of"),
        (("model", "bogus", 1), "unknown keys"),
        (("train", "num_neighs", [10]), "one entry per GNN layer"),
        (("train", "epochs", 0), "epochs and batch_size"),
        (("split", "fractions", [0.5, 0.2, 0.2]), "summing to 1"),
        (("flags", "ego", 1), "must be bool"),
    ],
)
def test_invalid_configs(tmp_path: Path, edit: tuple[str, str, object], message: str) -> None:
    import tomllib

    raw = tomllib.loads(PAPER.read_text())
    section, key, value = edit
    raw[section][key] = value
    from grafin_training.config import parse_gnn_config

    with pytest.raises(ConfigError, match=message):
        parse_gnn_config(raw)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_gnn_config(tmp_path / "nope.toml")
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_device.py tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_device.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/device.py`:

```python
"""Device resolution. `auto` never picks MPS: PyG scatter ops are not reliable there."""

from __future__ import annotations

import torch

from grafin_training.errors import ConfigError, CudaUnavailableError

DEVICE_CHOICES = ("auto", "cpu", "mps", "cuda")


def resolve_device(name: str) -> torch.device:
    if name not in DEVICE_CHOICES:
        raise ConfigError(f"unknown device {name!r}; choose one of {DEVICE_CHOICES}")
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name == "cuda":
        if not torch.cuda.is_available():
            raise CudaUnavailableError("--device cuda requested but CUDA is not available")
        return torch.device("cuda")
    if name == "mps":
        if not torch.backends.mps.is_available():
            raise ConfigError("--device mps requested but MPS is not available")
        return torch.device("mps")
    return torch.device("cpu")
```

`grafin_training/config.py`:

```python
"""Typed GNN configuration loaded from TOML (configs/paper_pna.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from grafin_training.errors import ConfigError

SUPPORTED_MODELS = ("pna",)

_SECTIONS: dict[str, dict[str, type]] = {
    "model": {
        "name": str,
        "n_hidden": int,
        "n_gnn_layers": int,
        "dropout": float,
        "final_dropout": float,
        "edge_updates": bool,
    },
    "flags": {"reverse_mp": bool, "ports": bool, "ego": bool, "tds": bool},
    "train": {
        "lr": float,
        "w_ce1": float,
        "w_ce2": float,
        "epochs": int,
        "batch_size": int,
        "num_neighs": list,
        "amp": bool,
    },
    "split": {"fractions": list},
}


@dataclass(frozen=True)
class ModelConfig:
    name: str
    n_hidden: int
    n_gnn_layers: int
    dropout: float
    final_dropout: float
    edge_updates: bool


@dataclass(frozen=True)
class FlagsConfig:
    reverse_mp: bool
    ports: bool
    ego: bool
    tds: bool


@dataclass(frozen=True)
class TrainConfig:
    lr: float
    w_ce1: float
    w_ce2: float
    epochs: int
    batch_size: int
    num_neighs: tuple[int, ...]
    amp: bool


@dataclass(frozen=True)
class SplitConfig:
    fractions: tuple[float, float, float]


@dataclass(frozen=True)
class GnnConfig:
    model: ModelConfig
    flags: FlagsConfig
    train: TrainConfig
    split: SplitConfig

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    sec = raw.get(name)
    if not isinstance(sec, dict):
        raise ConfigError(f"missing [{name}] section")
    spec = _SECTIONS[name]
    unknown = sorted(set(sec) - set(spec))
    missing = sorted(set(spec) - set(sec))
    if unknown:
        raise ConfigError(f"[{name}] unknown keys: {unknown}")
    if missing:
        raise ConfigError(f"[{name}] missing keys: {missing}")
    for key, typ in spec.items():
        value = sec[key]
        if typ is float:
            ok = _is_number(value)
        elif typ is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = isinstance(value, typ)
        if not ok:
            raise ConfigError(f"[{name}].{key} must be {typ.__name__}, got {value!r}")
    return sec


def parse_gnn_config(raw: dict[str, Any]) -> GnnConfig:
    unknown = sorted(set(raw) - set(_SECTIONS))
    if unknown:
        raise ConfigError(f"unknown sections: {unknown}")
    m, f, t, s = (_section(raw, n) for n in ("model", "flags", "train", "split"))
    if m["name"] not in SUPPORTED_MODELS:
        raise ConfigError(f"[model].name must be one of {SUPPORTED_MODELS}, got {m['name']!r}")
    if m["n_hidden"] < 5 or m["n_gnn_layers"] < 1:
        raise ConfigError("[model] needs n_hidden >= 5 and n_gnn_layers >= 1")
    if not (0 <= m["dropout"] < 1 and 0 <= m["final_dropout"] < 1):
        raise ConfigError("[model] dropouts must be in [0, 1)")
    neighs = t["num_neighs"]
    if not neighs or not all(
        isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in neighs
    ):
        raise ConfigError("[train].num_neighs must be a non-empty list of positive integers")
    if len(neighs) != m["n_gnn_layers"]:
        raise ConfigError("[train].num_neighs needs exactly one entry per GNN layer")
    if t["lr"] <= 0 or t["w_ce1"] <= 0 or t["w_ce2"] <= 0:
        raise ConfigError("[train] lr and class weights must be > 0")
    if t["epochs"] < 1 or t["batch_size"] < 1:
        raise ConfigError("[train] epochs and batch_size must be >= 1")
    fr = s["fractions"]
    if len(fr) != 3 or not all(_is_number(x) and x > 0 for x in fr) or abs(sum(fr) - 1) > 1e-9:
        raise ConfigError("[split].fractions must be three positive numbers summing to 1")
    return GnnConfig(
        model=ModelConfig(
            name=m["name"],
            n_hidden=m["n_hidden"],
            n_gnn_layers=m["n_gnn_layers"],
            dropout=float(m["dropout"]),
            final_dropout=float(m["final_dropout"]),
            edge_updates=m["edge_updates"],
        ),
        flags=FlagsConfig(**f),
        train=TrainConfig(
            lr=float(t["lr"]),
            w_ce1=float(t["w_ce1"]),
            w_ce2=float(t["w_ce2"]),
            epochs=t["epochs"],
            batch_size=t["batch_size"],
            num_neighs=tuple(neighs),
            amp=t["amp"],
        ),
        split=SplitConfig(fractions=(float(fr[0]), float(fr[1]), float(fr[2]))),
    )


def load_gnn_config(path: Path, overrides: dict[str, Any] | None = None) -> GnnConfig:
    """Load a TOML config; `overrides` maps "section.key" to a replacement value."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    for dotted, value in (overrides or {}).items():
        section, _, key = dotted.partition(".")
        if section not in raw or not isinstance(raw[section], dict):
            raise ConfigError(f"override {dotted!r} targets a missing section")
        raw[section][key] = value
    return parse_gnn_config(raw)
```

`configs/paper_pna.toml`:

```toml
# Multi-PNA+EU exactly as IBM/Multi-GNN@252b025 (model_settings.json "pna" + main.py defaults).
# Paper: Egressy et al., AAAI 2024, Table 2 — Small HI 68.16 ± 2.65, Medium HI 66.48 ± 1.63.

[model]
name = "pna"
n_hidden = 20
n_gnn_layers = 2
dropout = 0.08340440094051481
final_dropout = 0.28812979737686323
edge_updates = true            # upstream --emlps

[flags]
reverse_mp = true              # upstream --reverse_mp
ports = true                   # upstream --ports
ego = true                     # upstream --ego
tds = false                    # upstream --tds (not part of "Multi-")

[train]
lr = 0.0006116418195373612
w_ce1 = 1.0003967674742307
w_ce2 = 7.077633468006714
epochs = 100                   # upstream --n_epochs default
batch_size = 8192
num_neighs = [100, 100]
amp = false                    # CUDA only; off for parity

[split]
fractions = [0.6, 0.2, 0.2]
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_device.py tests/test_config.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add configs/paper_pna.toml grafin_training/config.py grafin_training/device.py tests/test_config.py tests/test_device.py
git commit -m "feat: device resolution and typed paper PNA config" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 4: Synthetic fixture in both data formats

Every later test runs on this ~229-edge, 6-day synthetic dataset, written in the raw Kaggle format (padded bank strings, original currencies, unsorted rows, `SHA256SUMS`) and the localized format (int banks, IDR, Indonesian channels, rows sorted by time, `MANIFEST.json`). Every transaction has a unique minute so port numbering has no time ties. 13 laundering edges: fan-in (day 1), cycle (day 3), fan-out (day 4). `conftest.py` exposes it as the session fixture `fixture_paths`.

**Files:**
- Create: `tests/fixture.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the implementation**

`tests/fixture.py`:

```python
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
```

`tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixture import write_fixture


@pytest.fixture(scope="session")
def fixture_paths(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """(raw CSV, id CSV) of the synthetic fixture, written once per test session."""
    return write_fixture(tmp_path_factory.mktemp("fixture"))
```

- [ ] **Step 2: Verify**

Run: `uv run python tests/fixture.py .smoke/fx && wc -l .smoke/fx/raw/HI-Fixture_Trans.csv .smoke/fx/id/HI-Fixture_Trans_sorted.csv && rm -rf .smoke`
Expected: 230 lines in each file (header + 229 transactions)

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py tests/fixture.py
git commit -m "test: synthetic AML fixture in raw and localized formats" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 5: Read and verify transaction CSVs

`read_transactions` reads either format by position (headers differ: `Account` vs `To Account`) into one canonical frame sorted by (ts, input row). Bank codes become Int64, which removes raw zero padding (the dataset repo verified this merges no accounts). `verify_dataset` checks the file's sha256 against `MANIFEST.json` (id) or `SHA256SUMS` (raw) and exits 2 on any mismatch.

**Files:**
- Create: `tests/test_load.py`
- Create: `grafin_training/data/load.py`
- Create: `grafin_training/data/__init__.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_load.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

import polars as pl
import pytest

from grafin_training.data.load import read_transactions, verify_dataset
from grafin_training.errors import DatasetError


def test_read_raw_and_id_give_the_same_transactions(fixture_paths: tuple[Path, Path]) -> None:
    raw, idp = (read_transactions(p) for p in fixture_paths)
    assert raw.height == idp.height == 229
    assert raw.get_column("ts").is_sorted() and idp.get_column("ts").is_sorted()
    assert raw.schema["from_bank"] == pl.Int64 and raw.get_column("from_bank").min() == 10
    cols = ["from_bank", "from_account", "to_bank", "to_account", "is_laundering"]
    assert raw.select(cols).equals(idp.select(cols))  # same order after sorting by time
    assert idp.get_column("receiving_currency").unique().to_list() == ["IDR"]
    assert int(raw.get_column("is_laundering").sum()) == 13


def test_verify_dataset(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    raw, idp = fixture_paths
    assert len(verify_dataset(raw, "raw")) == 64
    assert len(verify_dataset(idp, "id")) == 64
    tampered = tmp_path / "id"
    shutil.copytree(idp.parent, tampered)
    with (tampered / idp.name).open("a") as fh:
        fh.write("2025/09/09 23:59,10,X,10,Y,1,IDR,1,IDR,BI-FAST,0\n")
    with pytest.raises(DatasetError, match="does not match"):
        verify_dataset(tampered / idp.name, "id")
    (tampered / "MANIFEST.json").write_text(json.dumps({"outputs": {}}))
    with pytest.raises(DatasetError, match="no entry"):
        verify_dataset(tampered / idp.name, "id")
    with pytest.raises(DatasetError, match="not found"):
        verify_dataset(tmp_path / "missing.csv", "raw")
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_load.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_load.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/data/load.py`:

```python
"""Read raw Kaggle or localized (HI-*-ID) transaction CSVs into one canonical Polars frame.

Both formats share 11 positional columns; only the header text and value vocabularies differ.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import polars as pl

from grafin_training.errors import ConfigError, DatasetError

Source = Literal["raw", "id"]
SOURCES: tuple[Source, ...] = ("raw", "id")
POSITIONAL = (
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
TS_FORMAT = "%Y/%m/%d %H:%M"


def as_source(value: str) -> Source:
    if value == "raw":
        return "raw"
    if value == "id":
        return "id"
    raise ConfigError(f"--source must be one of {SOURCES}, got {value!r}")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def expected_sha256(path: Path, source: Source) -> str:
    """ID data: grafin-ai-dataset MANIFEST.json "outputs". Raw data: SHA256SUMS from the fetch step."""
    if source == "id":
        manifest = path.parent / "MANIFEST.json"
        if not manifest.is_file():
            raise DatasetError(f"missing {manifest}")
        try:
            outputs = json.loads(manifest.read_text(encoding="utf-8"))["outputs"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise DatasetError(f"{manifest}: no readable 'outputs' section") from exc
        if path.name not in outputs:
            raise DatasetError(f"{manifest} has no entry for {path.name}")
        return str(outputs[path.name])
    sums = path.parent / "SHA256SUMS"
    if not sums.is_file():
        raise DatasetError(f"missing {sums}")
    for line in sums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == path.name:
            return parts[0]
    raise DatasetError(f"{sums} has no entry for {path.name}")


def verify_dataset(path: Path, source: Source) -> str:
    """Return the file's sha256 after checking it against the dataset's manifest."""
    if not path.is_file():
        raise DatasetError(f"dataset not found: {path}")
    expected = expected_sha256(path, source)
    actual = sha256_file(path)
    if actual != expected:
        raise DatasetError(f"{path.name}: sha256 {actual} does not match expected {expected}")
    return actual


def read_transactions(path: Path) -> pl.DataFrame:
    """Canonical frame sorted by (ts, row).

    Columns: row (input order, 0-based), ts (epoch seconds, naive UTC), from_bank/to_bank (Int64,
    zero padding removed), from_account/to_account, amount_received/amount_paid (Float64),
    receiving_currency/payment_currency/payment_format (String), is_laundering (Int8).
    """
    schema = {name: pl.String for name in POSITIONAL}
    try:
        frame = pl.read_csv(path, has_header=False, skip_rows=1, schema=schema)
        frame = (
            frame.with_row_index("row")
            .with_columns(
                pl.col("timestamp")
                .str.strptime(pl.Datetime("us"), TS_FORMAT)
                .dt.epoch("s")
                .alias("ts"),
                pl.col("from_bank").cast(pl.Int64),
                pl.col("to_bank").cast(pl.Int64),
                pl.col("amount_received").cast(pl.Float64),
                pl.col("amount_paid").cast(pl.Float64),
                pl.col("is_laundering").cast(pl.Int8),
            )
            .drop("timestamp")
        )
    except (pl.exceptions.PolarsError, OSError) as exc:
        raise DatasetError(f"cannot read {path}: {exc}") from exc
    if frame.height == 0:
        raise DatasetError(f"{path} has no transactions")
    return frame.sort(["ts", "row"])
```

`grafin_training/data/__init__.py`:

```python

```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_load.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/data/__init__.py grafin_training/data/load.py tests/test_load.py
git commit -m "feat: canonical reader and sha256 verification for raw and ID datasets" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 6: Node ids in upstream order

Accounts are keyed by (bank, account) and numbered in first-appearance order over input rows, sender before receiver — exactly how IBM's `format_kaggle_files.py` numbers them. The test recomputes upstream's string-concatenation keys from the raw file and checks the count and the first ids.

**Files:**
- Create: `tests/test_nodes.py`
- Create: `grafin_training/data/nodes.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_nodes.py`:

```python
from __future__ import annotations

from pathlib import Path

import polars as pl

from grafin_training.data.load import read_transactions
from grafin_training.data.nodes import assign_node_ids


def test_node_ids_follow_upstream_first_appearance(fixture_paths: tuple[Path, Path]) -> None:
    raw_path, _ = fixture_paths
    frame, nodes = assign_node_ids(read_transactions(raw_path))
    assert nodes.get_column("node_id").to_list() == list(range(nodes.height))
    # upstream keys: bank string + account, in raw row order, sender before receiver
    lines = raw_path.read_text().splitlines()[1:]
    order: dict[str, int] = {}
    for line in lines:
        f = line.split(",")
        for key in (f[1] + f[2], f[3] + f[4]):
            order.setdefault(key, len(order))
    assert nodes.height == len(order)
    first = lines[0].split(",")
    row0 = frame.filter(pl.col("row") == 0)
    assert row0.get_column("from_id").item() == 0
    assert row0.get_column("to_id").item() == order[first[3] + first[4]]
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_nodes.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_nodes.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/data/nodes.py`:

```python
"""(bank, account) → contiguous node ids, numbered like the upstream formatter."""

from __future__ import annotations

import polars as pl


def assign_node_ids(frame: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Add from_id/to_id; return (frame, nodes[node_id, bank, account]).

    Ids follow first appearance in input row order, sender before receiver within a row — the
    order IBM's format_kaggle_files.py assigns them. The output frame keeps its row order.
    """
    by_row = frame.sort("row")
    keys = pl.concat(
        [
            by_row.select(
                "row",
                pl.lit(0, pl.Int8).alias("side"),
                pl.col("from_bank").alias("bank"),
                pl.col("from_account").alias("account"),
            ),
            by_row.select(
                "row",
                pl.lit(1, pl.Int8).alias("side"),
                pl.col("to_bank").alias("bank"),
                pl.col("to_account").alias("account"),
            ),
        ]
    ).sort(["row", "side"])
    nodes = (
        keys.unique(subset=["bank", "account"], keep="first", maintain_order=True)
        .select("bank", "account")
        .with_row_index("node_id")
        .with_columns(pl.col("node_id").cast(pl.Int64))
    )
    from_ids = nodes.rename({"node_id": "from_id", "bank": "from_bank", "account": "from_account"})
    to_ids = nodes.rename({"node_id": "to_id", "bank": "to_bank", "account": "to_account"})
    out = frame.join(from_ids, on=["from_bank", "from_account"], how="left", maintain_order="left")
    out = out.join(to_ids, on=["to_bank", "to_account"], how="left", maintain_order="left")
    return out, nodes
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_nodes.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/data/nodes.py tests/test_nodes.py
git commit -m "feat: (bank, account) node ids in upstream first-appearance order" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 7: Day-based splits

`paper_split` is upstream's day-boundary search (minimise the worst relative error vs 60/20/20 by transaction count). The test feeds the real HI-Small daily counts and must get train days 0–5, val 6–7, test 8–17, identical to the verbatim upstream oracle. `calibration_split` (used by Plan B) splits training days ~80/20 at a day boundary.

**Files:**
- Create: `tests/test_split.py`
- Create: `grafin_training/data/split.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_split.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from grafin_training.data.load import read_transactions
from grafin_training.data.split import calibration_split, day_index, paper_split, rows_for_days
from grafin_training.errors import ConfigError
from tests import upstream_ref

HI_SMALL_DAILY = [
    1114921,
    754449,
    207382,
    207430,
    482650,
    482089,
    482751,
    482773,
    654467,
    208325,
    396,
    281,
    184,
    121,
    46,
    46,
    23,
    11,
]


def test_paper_split_matches_upstream_on_hi_small_counts() -> None:
    day_idx = np.repeat(np.arange(len(HI_SMALL_DAILY)), HI_SMALL_DAILY).astype(np.int64)
    split = paper_split(day_idx)
    expected = upstream_ref.paper_split_days(HI_SMALL_DAILY)
    assert [list(split.train_days), list(split.val_days), list(split.test_days)] == expected
    assert split.train_days == tuple(range(6)) and split.val_days == (6, 7)


def test_paper_split_matches_upstream_on_fixture(fixture_paths: tuple[Path, Path]) -> None:
    ts = read_transactions(fixture_paths[0]).get_column("ts").to_numpy()
    day_idx = day_index(ts)
    split = paper_split(day_idx)
    expected = upstream_ref.paper_split_days(np.bincount(day_idx).tolist())
    assert [list(split.train_days), list(split.val_days), list(split.test_days)] == expected


def test_paper_split_needs_three_days() -> None:
    with pytest.raises(ConfigError):
        paper_split(np.array([0, 0, 1], dtype=np.int64))


def test_calibration_split_on_hi_small() -> None:
    day_idx = np.repeat(np.arange(len(HI_SMALL_DAILY)), HI_SMALL_DAILY).astype(np.int64)
    fit, calib = calibration_split(day_idx, tuple(range(6)))
    assert fit == (0, 1, 2, 3, 4) and calib == (5,)
    with pytest.raises(ConfigError):
        calibration_split(day_idx, (0,))


def test_rows_for_days() -> None:
    day_idx = np.array([0, 0, 1, 2, 2], dtype=np.int64)
    assert rows_for_days(day_idx, (0, 2)).tolist() == [0, 1, 3, 4]
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_split.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_split.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/data/split.py`:

```python
"""Day-based temporal splits."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from grafin_training.errors import ConfigError

SECONDS_PER_DAY = 86_400
IntArray = npt.NDArray[np.int64]


def day_index(ts: IntArray) -> IntArray:
    """Day number relative to the first transaction (upstream: (ts - min) // 86400)."""
    out: IntArray = ((ts - ts.min()) // SECONDS_PER_DAY).astype(np.int64)
    return out


@dataclass(frozen=True)
class DaySplit:
    train_days: tuple[int, ...]
    val_days: tuple[int, ...]
    test_days: tuple[int, ...]

    def to_dict(self) -> dict[str, list[int]]:
        return {
            "train_days": list(self.train_days),
            "val_days": list(self.val_days),
            "test_days": list(self.test_days),
        }


def paper_split(
    day_idx: IntArray, fractions: tuple[float, float, float] = (0.6, 0.2, 0.2)
) -> DaySplit:
    """Upstream data_loading.get_data split: choose day boundaries i < j that minimise the
    largest relative error between the split proportions (by transaction count) and `fractions`.
    Ties keep the first (i, j) in itertools.combinations order, as upstream's min() does."""
    n_days = int(day_idx.max()) + 1
    if n_days < 3:
        raise ConfigError(f"need at least 3 days of data for a 3-way split, got {n_days}")
    d_ts = np.bincount(day_idx, minlength=n_days)
    scores: dict[tuple[int, int], float] = {}
    for i, j in itertools.combinations(range(n_days), 2):
        totals = [d_ts[:i].sum(), d_ts[i:j].sum(), d_ts[j:].sum()]
        total = float(np.sum(totals))
        props = [v / total for v in totals]
        scores[(i, j)] = max(abs(v - t) / t for v, t in zip(props, fractions))
    i, j = min(scores, key=scores.__getitem__)
    return DaySplit(tuple(range(i)), tuple(range(i, j)), tuple(range(j, n_days)))


def calibration_split(
    day_idx: IntArray, train_days: tuple[int, ...], fit_fraction: float = 0.8
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Split training days into (GNN-fit days, calibration days) at the day boundary whose
    cumulative transaction share is closest to `fit_fraction`; both parts are non-empty."""
    if len(train_days) < 2:
        raise ConfigError("calibration split needs at least 2 training days")
    counts = np.bincount(day_idx, minlength=max(train_days) + 1)[list(train_days)]
    cum = np.cumsum(counts) / counts.sum()
    k = 1 + int(np.argmin(np.abs(cum[:-1] - fit_fraction)))
    return train_days[:k], train_days[k:]


def rows_for_days(day_idx: IntArray, days: tuple[int, ...]) -> IntArray:
    return np.flatnonzero(np.isin(day_idx, np.asarray(days, dtype=np.int64))).astype(np.int64)
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_split.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/data/split.py tests/test_split.py
git commit -m "feat: upstream day split and calibration split" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 8: Paper edge features and train-only normalisation

Base features are upstream's four (seconds since first transaction, amount received, receiving-currency code, payment-format code); codes are assigned in upstream's first-appearance order. On ID data the currency code is constant (all IDR) — the test pins that known fact. **Fix vs upstream:** `fit_norm` uses training rows only (upstream normalised val/test with their own statistics).

**Files:**
- Create: `tests/test_features.py`
- Create: `grafin_training/data/features.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_features.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np

from grafin_training.data.features import apply_norm, build_codebooks, fit_norm, paper_base_features
from grafin_training.data.load import read_transactions


def test_codebooks_first_appearance(fixture_paths: tuple[Path, Path]) -> None:
    frame = read_transactions(fixture_paths[0])
    books = build_codebooks(frame)
    first_row = frame.sort("row").row(0, named=True)
    assert books.currency[first_row["receiving_currency"]] == 0
    assert books.payment_format[first_row["payment_format"]] == 0
    assert sorted(books.currency.values()) == list(range(len(books.currency)))


def test_base_features(fixture_paths: tuple[Path, Path]) -> None:
    frame = read_transactions(fixture_paths[1])
    base = paper_base_features(frame, build_codebooks(frame))
    assert base.shape == (229, 4)
    assert base[0, 0] == 0 and np.all(np.diff(base[:, 0]) >= 0)
    assert np.all(base[:, 2] == 0)  # localized data: currency is constant IDR


def test_norm_is_fit_on_train_rows_only() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(100, 3))
    x[:, 2] = 5.0
    train = np.arange(60)
    stats = fit_norm(x, train)
    x2 = x.copy()
    x2[60:] *= 1000  # changing non-train rows must not move the statistics
    stats2 = fit_norm(x2, train)
    assert np.array_equal(stats.mean, stats2.mean) and np.array_equal(stats.std, stats2.std)
    assert stats.std[2] == 1.0
    out = apply_norm(x, stats)
    assert out.dtype == np.float32 and np.allclose(out[:60, :2].mean(axis=0), 0, atol=1e-6)
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_features.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_features.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/data/features.py`:

```python
"""Paper edge features, categorical codebooks and train-only normalisation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BASE_FEATURES = ("Timestamp", "Amount Received", "Received Currency", "Payment Format")


@dataclass(frozen=True)
class Codebooks:
    currency: dict[str, int]
    payment_format: dict[str, int]

    def to_dict(self) -> dict[str, dict[str, int]]:
        return {"currency": self.currency, "payment_format": self.payment_format}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Codebooks:
        return cls(dict(raw["currency"]), dict(raw["payment_format"]))


def build_codebooks(frame: pl.DataFrame) -> Codebooks:
    """Codes in first-appearance order over input rows, as upstream assigns them
    (per row: receiving currency, then payment currency; payment format)."""
    by_row = frame.sort("row")
    cur = pl.concat(
        [
            by_row.select("row", pl.lit(0).alias("side"), pl.col("receiving_currency").alias("v")),
            by_row.select("row", pl.lit(1).alias("side"), pl.col("payment_currency").alias("v")),
        ]
    ).sort(["row", "side"])
    currencies = cur.get_column("v").unique(maintain_order=True).to_list()
    formats = by_row.get_column("payment_format").unique(maintain_order=True).to_list()
    return Codebooks(
        {c: i for i, c in enumerate(currencies)}, {f: i for i, f in enumerate(formats)}
    )


def paper_base_features(frame: pl.DataFrame, codebooks: Codebooks) -> FloatArray:
    """[E, 4] in frame order: seconds since the first transaction, amount received,
    receiving-currency code, payment-format code (upstream edge_features)."""
    ts = frame.get_column("ts").to_numpy().astype(np.float64)
    amount = frame.get_column("amount_received").to_numpy().astype(np.float64)
    cur = frame.get_column("receiving_currency").replace_strict(
        codebooks.currency, return_dtype=pl.Int64
    )
    fmt = frame.get_column("payment_format").replace_strict(
        codebooks.payment_format, return_dtype=pl.Int64
    )
    return np.column_stack(
        [
            ts - ts.min(),
            amount,
            cur.to_numpy().astype(np.float64),
            fmt.to_numpy().astype(np.float64),
        ]
    )


@dataclass(frozen=True)
class NormStats:
    mean: FloatArray
    std: FloatArray

    def to_dict(self) -> dict[str, list[float]]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}


def fit_norm(x: FloatArray, rows: IntArray) -> NormStats:
    """Column mean / unbiased std over `rows` only (upstream z_norm; zero std → 1).
    Fix vs upstream: fitted on training rows and applied to every split."""
    sub = x[rows]
    mean = sub.mean(axis=0)
    std = sub.std(axis=0, ddof=1)
    return NormStats(mean, np.where(std == 0, 1.0, std))


def apply_norm(x: FloatArray, stats: NormStats) -> npt.NDArray[np.float32]:
    return ((x - stats.mean) / stats.std).astype(np.float32)
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_features.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/data/features.py tests/test_features.py
git commit -m "feat: paper edge features, codebooks, train-only z-normalisation" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 9: Ports, time deltas and PyG graphs

Upstream computes ports and time deltas with Python loops over per-node lists (hours and many GB on HI-Medium). These vectorised versions are proven equal to the verbatim upstream code on random graphs. Both are causal (depend only on earlier edges), so computing them once on the full sorted edge list gives the same values upstream computes per split. `make_graph` reproduces upstream's reverse-MP port swap quirk on purpose (see the code comment); node features are zeros because upstream z-normalises an all-ones placeholder. `paper_graphs` builds upstream's train / train+val / all graphs with seed positions.

**Files:**
- Create: `tests/test_graph_build.py`
- Create: `grafin_training/graph/build.py`
- Create: `grafin_training/graph/__init__.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_graph_build.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import torch
from torch_geometric.data import HeteroData

from grafin_training.graph.build import (
    EDGE,
    REV,
    _ports,
    make_graph,
    paper_graphs,
    port_columns,
    time_delta_columns,
)
from tests import upstream_ref


def _random_graph(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    rng = np.random.default_rng(seed)
    n, e = int(rng.integers(5, 40)), int(rng.integers(20, 300))
    src, dst = rng.integers(0, n, e), rng.integers(0, n, e)
    ts = rng.permutation(e * 3)[:e].astype(np.int64)  # unique timestamps
    return src.astype(np.int64), dst.astype(np.int64), ts, n


def _upstream(src: np.ndarray, dst: np.ndarray, ts: np.ndarray, n: int) -> np.ndarray:
    ei = torch.tensor(np.vstack([src, dst]))
    data = SimpleNamespace(
        num_nodes=n, edge_index=ei, timestamps=torch.tensor(ts, dtype=torch.float32)
    )
    a_in, a_out = upstream_ref.to_adj_nodes_with_times(data)
    e_in, e_out = upstream_ref.to_adj_edges_with_times(data)
    return np.hstack(
        [
            upstream_ref.ports(ei, a_in).numpy(),
            upstream_ref.ports(ei.flipud(), a_out).numpy(),
            upstream_ref.time_deltas(data, e_in).numpy(),
            upstream_ref.time_deltas(data, e_out).numpy(),
        ]
    )


def test_ports_and_time_deltas_match_upstream_on_random_graphs() -> None:
    for seed in range(15):
        src, dst, ts, n = _random_graph(seed)
        ours = np.hstack([port_columns(src, dst, ts), time_delta_columns(src, dst, ts)])
        np.testing.assert_array_equal(ours, _upstream(src, dst, ts, n))


def test_port_ties_break_by_edge_order() -> None:
    # node 9 receives from 1 then 2 at the same instant: edge order decides the ranks
    src = np.array([1, 2], dtype=np.int64)
    dst = np.array([9, 9], dtype=np.int64)
    ts = np.array([5, 5], dtype=np.int64)
    assert _ports(dst, src, ts).tolist() == [0.0, 1.0]


def test_hetero_graph_reproduces_upstream_port_swap_quirk() -> None:
    attr = torch.arange(12, dtype=torch.float32).view(2, 6)
    data = make_graph(
        3, torch.tensor([[0, 1], [1, 2]]), attr, torch.tensor([0, 1]), reverse_mp=True, ports=True
    )
    assert isinstance(data, HeteroData)
    expected = attr.clone()
    expected[:, [-1, -2]] = attr[:, [-2, -1]]
    assert torch.equal(data[EDGE].edge_attr, expected)
    assert torch.equal(data[REV].edge_attr, expected)
    assert torch.equal(data[REV].edge_index, torch.tensor([[1, 2], [0, 1]]))
    assert torch.equal(data["node"].x, torch.zeros(3, 1))
    assert torch.equal(attr, torch.arange(12, dtype=torch.float32).view(2, 6))  # input untouched


def test_paper_graphs_layout() -> None:
    e = 10
    rows = {"train": np.arange(0, 6), "val": np.arange(6, 8), "test": np.arange(8, 10)}
    graphs = paper_graphs(
        4,
        torch.randint(0, 4, (2, e)),
        torch.randn(e, 6),
        torch.zeros(e, dtype=torch.long),
        rows,
        reverse_mp=False,
        ports=True,
    )
    assert graphs["train"].data.num_edges == 6 and graphs["train"].seeds.tolist() == list(range(6))
    assert graphs["val"].data.num_edges == 8 and graphs["val"].seeds.tolist() == [6, 7]
    assert graphs["test"].data.num_edges == 10 and graphs["test"].seeds.tolist() == [8, 9]
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_graph_build.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_graph_build.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/graph/build.py`:

```python
"""Port numbers, time deltas and PyG graph objects (port of upstream data_util.py)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import torch
from torch_geometric.data import Data, HeteroData

EDGE = ("node", "to", "node")
REV = ("node", "rev_to", "node")
IntArray = npt.NDArray[np.int64]
F32Array = npt.NDArray[np.float32]


def _ports(center: IntArray, other: IntArray, ts: IntArray) -> F32Array:
    """For each edge: rank of `other` among `center`'s neighbours, ordered by the time each
    neighbour first appears (ties by edge order). Vectorised upstream data_util.ports."""
    e = np.arange(center.shape[0])
    order = np.lexsort((e, ts, center))
    n = int(max(center.max(), other.max())) + 1
    pair = center[order].astype(np.int64) * n + other[order].astype(np.int64)
    uniq_pairs, first_pos = np.unique(pair, return_index=True)
    pair_center = uniq_pairs // n
    rank_order = np.lexsort((first_pos, pair_center))
    sorted_center = pair_center[rank_order]
    group_start = np.searchsorted(sorted_center, sorted_center, side="left")
    ranks = np.empty(first_pos.shape[0], dtype=np.int64)
    ranks[rank_order] = np.arange(rank_order.shape[0]) - group_start
    edge_pair = center.astype(np.int64) * n + other.astype(np.int64)
    return ranks[np.searchsorted(uniq_pairs, edge_pair)].astype(np.float32)


def _time_deltas(center: IntArray, ts: IntArray) -> F32Array:
    """For each edge: time since the previous edge at the same `center` node (first edge → 0),
    ordering by (time, edge order). Vectorised upstream data_util.time_deltas."""
    e = np.arange(center.shape[0])
    order = np.lexsort((e, ts, center))
    c_s = center[order]
    t_s = ts[order].astype(np.float64)
    same = c_s[1:] == c_s[:-1]
    td_sorted = np.concatenate([[0.0], np.where(same, t_s[1:] - t_s[:-1], 0.0)])
    td = np.empty(center.shape[0], dtype=np.float64)
    td[order] = td_sorted
    return td.astype(np.float32)


def port_columns(src: IntArray, dst: IntArray, ts: IntArray) -> F32Array:
    """[E, 2]: in-port (rank of src among dst's in-neighbours), out-port (rank of dst among
    src's out-neighbours) — upstream add_ports column order."""
    return np.column_stack([_ports(dst, src, ts), _ports(src, dst, ts)])


def time_delta_columns(src: IntArray, dst: IntArray, ts: IntArray) -> F32Array:
    """[E, 2]: in-time-delta (at dst), out-time-delta (at src) — upstream add_time_deltas order."""
    return np.column_stack([_time_deltas(dst, ts), _time_deltas(src, ts)])


def make_graph(
    num_nodes: int,
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
    y: torch.Tensor,
    *,
    reverse_mp: bool,
    ports: bool,
) -> Data | HeteroData:
    """Homogeneous Data, or HeteroData with forward 'to' and reversed 'rev_to' edges."""
    # Upstream: z_norm of the all-ones placeholder node feature gives all zeros.
    x = torch.zeros((num_nodes, 1), dtype=torch.float32)
    if not reverse_mp:
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)
    attr = edge_attr.clone()
    if ports:
        # UPSTREAM QUIRK (data_util.create_hetero_obj @252b025): the rev_to port swap is done in
        # place on a tensor shared with the 'to' edge type, so BOTH edge types end up with the
        # last two columns swapped. Reproduced on purpose for paper parity.
        attr[:, [-1, -2]] = attr[:, [-2, -1]]
    data = HeteroData()
    data["node"].x = x
    data[EDGE].edge_index = edge_index
    data[REV].edge_index = edge_index.flipud()
    data[EDGE].edge_attr = attr
    data[REV].edge_attr = attr
    data[EDGE].y = y
    return data


@dataclass(frozen=True)
class SplitGraph:
    """A graph plus the positions (within it) of the edges that are trained on / scored."""

    data: Data | HeteroData
    seeds: torch.Tensor


def paper_graphs(
    num_nodes: int,
    edge_index: torch.Tensor,
    edge_attr: torch.Tensor,
    y: torch.Tensor,
    rows: dict[str, IntArray],
    *,
    reverse_mp: bool,
    ports: bool,
) -> dict[str, SplitGraph]:
    """Upstream paper protocol: train graph = train edges; val graph = train+val edges (val
    scored); test graph = all edges (test scored). `rows` holds sorted global edge positions."""
    tr, va, te = rows["train"], rows["val"], rows["test"]
    layout = {
        "train": (tr, tr),
        "val": (np.concatenate([tr, va]), va),
        "test": (np.concatenate([tr, va, te]), te),
    }
    graphs: dict[str, SplitGraph] = {}
    for name, (graph_rows, seed_rows) in layout.items():
        ordered = np.sort(graph_rows)
        idx = torch.from_numpy(ordered)
        data = make_graph(
            num_nodes,
            edge_index[:, idx],
            edge_attr[idx],
            y[idx],
            reverse_mp=reverse_mp,
            ports=ports,
        )
        seeds = torch.from_numpy(np.searchsorted(ordered, seed_rows).astype(np.int64))
        graphs[name] = SplitGraph(data, seeds)
    return graphs
```

`grafin_training/graph/__init__.py`:

```python

```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_graph_build.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/graph/__init__.py grafin_training/graph/build.py tests/test_graph_build.py
git commit -m "feat: vectorised ports/time deltas and paper split graphs" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 10: `prepare`: verified, cached dataset arrays

`prepare_dataset` verifies the file, reads it, assigns node ids, builds base features, ports and time deltas, and caches everything under `cache/<source>-<sha16>/` (meta.json written last). Four GPU jobs may prepare the same dataset at once, so each builds in a private temp dir and renames it into place; a loser discards its copy. The second test proves the cached ports/time deltas equal upstream's on the fixture.

**Files:**
- Create: `tests/test_prepare.py`
- Create: `grafin_training/data/prepare.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_prepare.py`:

```python
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from grafin_training.data.prepare import prepare_dataset
from tests import upstream_ref


def test_prepare_cache_reuse_and_stale_rebuild(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    first = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert first.meta["n_edges"] == 229 and first.num_nodes == 36
    assert first.edge_features(ports=True, tds=False).shape == (229, 6)
    assert first.edge_features(ports=True, tds=True).shape == (229, 8)
    again = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert again.cache_dir == first.cache_dir
    (first.cache_dir / "meta.json").write_text("{}")  # stale cache must be rebuilt
    rebuilt = prepare_dataset(fixture_paths[1], "id", tmp_path)
    assert rebuilt.meta["sha256"] == first.meta["sha256"]
    assert not any(p.name.startswith(".tmp-") for p in tmp_path.iterdir())


def _upstream(src: np.ndarray, dst: np.ndarray, ts: np.ndarray, n: int) -> np.ndarray:
    ei = torch.tensor(np.vstack([src, dst]))
    data = SimpleNamespace(
        num_nodes=n, edge_index=ei, timestamps=torch.tensor(ts, dtype=torch.float32)
    )
    a_in, a_out = upstream_ref.to_adj_nodes_with_times(data)
    e_in, e_out = upstream_ref.to_adj_edges_with_times(data)
    return np.hstack(
        [
            upstream_ref.ports(ei, a_in).numpy(),
            upstream_ref.ports(ei.flipud(), a_out).numpy(),
            upstream_ref.time_deltas(data, e_in).numpy(),
            upstream_ref.time_deltas(data, e_out).numpy(),
        ]
    )


def test_ports_match_upstream_on_fixture(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    p = prepare_dataset(fixture_paths[0], "raw", tmp_path)
    ours = np.hstack([p.ports, p.tds])
    np.testing.assert_array_equal(ours, _upstream(p.src, p.dst, p.ts - p.ts.min(), p.num_nodes))
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_prepare.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_prepare.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/data/prepare.py`:

```python
"""`prepare`: verify → read → node ids → codebooks → features → cache (keyed by file sha256)."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from grafin_training.data.features import Codebooks, build_codebooks, paper_base_features
from grafin_training.data.load import Source, read_transactions, verify_dataset
from grafin_training.data.nodes import assign_node_ids
from grafin_training.data.split import day_index
from grafin_training.errors import DatasetError
from grafin_training.graph.build import port_columns, time_delta_columns

log = logging.getLogger(__name__)
CACHE_VERSION = 1
_ARRAYS = ("src", "dst", "ts", "y", "day_idx", "base", "ports", "tds")


@dataclass(frozen=True)
class PreparedData:
    cache_dir: Path
    meta: dict[str, Any]
    codebooks: Codebooks
    src: npt.NDArray[np.int64]
    dst: npt.NDArray[np.int64]
    ts: npt.NDArray[np.int64]
    y: npt.NDArray[np.int64]
    day_idx: npt.NDArray[np.int64]
    base: npt.NDArray[np.float64]
    ports: npt.NDArray[np.float32]
    tds: npt.NDArray[np.float32]

    @property
    def num_nodes(self) -> int:
        return int(self.meta["n_nodes"])

    def edge_features(self, *, ports: bool, tds: bool) -> npt.NDArray[np.float64]:
        """Upstream edge_attr layout: base 4, then [in_port, out_port], then [in_td, out_td]."""
        cols: list[npt.NDArray[Any]] = [self.base]
        if ports:
            cols.append(self.ports)
        if tds:
            cols.append(self.tds)
        return np.hstack(cols).astype(np.float64)


def _load(cache_dir: Path, meta: dict[str, Any]) -> PreparedData:
    with np.load(cache_dir / "arrays.npz") as npz:
        arrays = {name: npz[name] for name in _ARRAYS}
    codebooks = Codebooks.from_dict(json.loads((cache_dir / "codebooks.json").read_text()))
    return PreparedData(cache_dir=cache_dir, meta=meta, codebooks=codebooks, **arrays)


def _valid_meta(cache_dir: Path, sha: str) -> dict[str, Any] | None:
    meta_path = cache_dir / "meta.json"
    if not meta_path.is_file():
        return None
    meta: dict[str, Any] = json.loads(meta_path.read_text())
    if meta.get("sha256") != sha or meta.get("cache_version") != CACHE_VERSION:
        return None
    return meta


def _build(path: Path, source: Source, sha: str, out: Path) -> None:
    """Write a complete cache into `out` (meta.json last)."""
    frame, nodes = assign_node_ids(read_transactions(path))
    codebooks = build_codebooks(frame)
    src = frame.get_column("from_id").to_numpy().astype(np.int64)
    dst = frame.get_column("to_id").to_numpy().astype(np.int64)
    ts = frame.get_column("ts").to_numpy().astype(np.int64)
    y = frame.get_column("is_laundering").to_numpy().astype(np.int64)
    day_idx = day_index(ts)
    out.mkdir(parents=True)
    np.savez(
        out / "arrays.npz",
        src=src,
        dst=dst,
        ts=ts,
        y=y,
        day_idx=day_idx,
        base=paper_base_features(frame, codebooks),
        ports=port_columns(src, dst, ts),
        tds=time_delta_columns(src, dst, ts),
    )
    nodes.write_parquet(out / "nodes.parquet")
    (out / "codebooks.json").write_text(json.dumps(codebooks.to_dict(), indent=2))
    meta = {
        "cache_version": CACHE_VERSION,
        "dataset": path.stem,
        "path": str(path),
        "source": source,
        "sha256": sha,
        "n_edges": int(src.shape[0]),
        "n_nodes": int(nodes.height),
        "n_days": int(day_idx.max()) + 1,
        "laundering": int(y.sum()),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))


def prepare_dataset(path: Path, source: Source, cache_root: Path) -> PreparedData:
    """Verify the dataset and return its cached arrays, building the cache if needed.

    Safe for parallel jobs: each builder writes a private temp dir and renames it into place;
    a builder that loses the race discards its copy and loads the winner's."""
    sha = verify_dataset(path, source)
    cache_dir = cache_root / f"{source}-{sha[:16]}"
    meta = _valid_meta(cache_dir, sha)
    if meta is not None:
        log.info("prepare: reusing cache %s", cache_dir)
        return _load(cache_dir, meta)
    if cache_dir.exists():  # stale or incomplete cache from an older version
        shutil.rmtree(cache_dir, ignore_errors=True)
    log.info("prepare: reading %s", path)
    tmp = cache_root / f".tmp-{os.getpid()}-{cache_dir.name}"
    shutil.rmtree(tmp, ignore_errors=True)
    _build(path, source, sha, tmp)
    try:
        os.rename(tmp, cache_dir)
    except OSError:  # another job finished first
        shutil.rmtree(tmp, ignore_errors=True)
    meta = _valid_meta(cache_dir, sha)
    if meta is None:
        raise DatasetError(f"cache at {cache_dir} is incomplete after build")
    return _load(cache_dir, meta)
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_prepare.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/data/prepare.py tests/test_prepare.py
git commit -m "feat: prepare step with race-safe dataset cache" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 11: Loaders, ego IDs and seed masks

Port of upstream `train_util`: `LinkNeighborLoader` per split graph, `AddEgoIds` marking the endpoints of each batch's seed edges, and `seed_mask` selecting the seed edges among the sampled ones via `e_id` (equivalent to upstream's prepended edge-id column). Upstream semantics are kept: a seed edge not sampled into its own batch is skipped, and the number of seeds is returned so coverage can be logged.

**Files:**
- Create: `tests/test_loaders.py`
- Create: `grafin_training/graph/loaders.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_loaders.py`:

```python
from __future__ import annotations

import numpy as np
import torch

from grafin_training.graph.build import EDGE, paper_graphs
from grafin_training.graph.loaders import AddEgoIds, make_loader, seed_mask


def test_loader_ego_ids_and_seed_mask() -> None:
    torch.manual_seed(0)
    e = 40
    ei = torch.randint(0, 12, (2, e))
    rows = {"train": np.arange(0, 30), "val": np.arange(30, 35), "test": np.arange(35, 40)}
    graphs = paper_graphs(
        12,
        ei,
        torch.randn(e, 6),
        torch.zeros(e, dtype=torch.long),
        rows,
        reverse_mp=True,
        ports=True,
    )
    loader = make_loader(graphs["val"], num_neighs=(50, 50), batch_size=5, shuffle=False, ego=True)
    batch = next(iter(loader))
    assert batch["node"].x.shape[1] == 2  # placeholder + ego column
    ego_nodes = torch.unique(batch[EDGE].edge_label_index.view(-1))
    assert torch.all(batch["node"].x[ego_nodes, 1] == 1)
    mask, n_seeds = seed_mask(batch, graphs["val"].seeds)
    assert n_seeds == 5
    assert set(batch[EDGE].e_id[mask].tolist()) <= set(graphs["val"].seeds.tolist())
    assert int(mask.sum()) == 5  # with generous fan-out every seed edge is sampled


def test_add_ego_ids_homogeneous() -> None:
    from torch_geometric.data import Data

    data = Data(x=torch.zeros(4, 1), edge_label_index=torch.tensor([[0], [2]]))
    out = AddEgoIds()(data)
    assert out.x[:, 1].tolist() == [1.0, 0.0, 1.0, 0.0]
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_loaders.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_loaders.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/graph/loaders.py`:

```python
"""Link-neighbour loaders, ego IDs and seed-edge masks (port of upstream train_util.py)."""

from __future__ import annotations

from typing import Any

import torch
from torch_geometric.data import Data, HeteroData
from torch_geometric.loader import LinkNeighborLoader
from torch_geometric.transforms import BaseTransform

from grafin_training.graph.build import EDGE, SplitGraph


class AddEgoIds(BaseTransform):  # type: ignore[misc]
    """Append a 0/1 column to node features marking the endpoints of the batch's seed edges."""

    def forward(self, data: Any) -> Any:
        hetero = isinstance(data, HeteroData)
        x = data["node"].x if hetero else data.x
        label_index = data[EDGE].edge_label_index if hetero else data.edge_label_index
        ids = torch.zeros((x.shape[0], 1), device=x.device)
        ids[torch.unique(label_index.view(-1)).to(x.device)] = 1
        if hetero:
            data["node"].x = torch.cat([x, ids], dim=1)
        else:
            data.x = torch.cat([x, ids], dim=1)
        return data


def make_loader(
    graph: SplitGraph, *, num_neighs: tuple[int, ...], batch_size: int, shuffle: bool, ego: bool
) -> LinkNeighborLoader:
    data = graph.data
    transform = AddEgoIds() if ego else None
    if isinstance(data, HeteroData):
        return LinkNeighborLoader(
            data,
            num_neighbors=list(num_neighs),
            edge_label_index=(EDGE, data[EDGE].edge_index[:, graph.seeds]),
            edge_label=data[EDGE].y[graph.seeds],
            batch_size=batch_size,
            shuffle=shuffle,
            transform=transform,
        )
    return LinkNeighborLoader(
        data,
        num_neighbors=list(num_neighs),
        edge_label_index=data.edge_index[:, graph.seeds],
        edge_label=data.y[graph.seeds],
        batch_size=batch_size,
        shuffle=shuffle,
        transform=transform,
    )


def seed_mask(batch: Data | HeteroData, seeds: torch.Tensor) -> tuple[torch.Tensor, int]:
    """(mask over the batch's sampled forward edges selecting its seed edges, number of seeds).

    Upstream semantics: a seed edge that was not sampled into its own batch is skipped."""
    store = batch[EDGE] if isinstance(batch, HeteroData) else batch
    batch_seeds = seeds[store.input_id.cpu()]
    return torch.isin(store.e_id.cpu(), batch_seeds), int(batch_seeds.numel())
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_loaders.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/graph/loaders.py tests/test_loaders.py
git commit -m "feat: link-neighbour loaders, ego IDs and seed masks" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 12: Run directories and failure-tolerant MLflow

The run directory is the source of truth (config, env, data facts, metrics, checkpoints, log). MLflow 3's file store is in maintenance mode, so tracking uses SQLite at `mlruns/mlflow.db`; any MLflow error is logged once and disables tracking instead of failing a multi-hour run (four jobs share one SQLite file).

**Files:**
- Create: `tests/test_tracking.py`
- Create: `grafin_training/tracking.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tracking.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import torch

from grafin_training.errors import ConfigError
from grafin_training.tracking import RunDir, Tracker, environment_info, flatten, make_run_id


def test_run_id_and_run_dir(tmp_path: Path) -> None:
    rid = make_run_id("HI-Small_Trans", "paper", 2, datetime(2026, 10, 17, 3, 4, 5, tzinfo=UTC))
    assert rid == "20261017-030405-HI-Small_Trans-paper-s2"
    run = RunDir.create(tmp_path, rid)
    run.write_json("x.json", {"a": 1})
    assert run.read_json("x.json") == {"a": 1}
    with pytest.raises(ConfigError, match="already exists"):
        RunDir.create(tmp_path, rid)
    with pytest.raises(ConfigError, match="no run to resume"):
        RunDir.open(tmp_path, "missing")


def test_flatten_and_env() -> None:
    assert flatten({"a": {"b": 1, "c": {"d": 2}}, "e": 3}) == {"a.b": 1, "a.c.d": 2, "e": 3}
    env = environment_info(torch.device("cpu"))
    assert {"git_sha", "git_dirty", "torch", "torch_geometric", "device"} <= set(env)


def test_tracker_logs_to_sqlite_and_never_raises(tmp_path: Path) -> None:
    uri = f"sqlite:///{tmp_path / 'mlruns' / 'mlflow.db'}"
    tracker = Tracker(uri, "run-a", {"gnn": {"lr": 0.1}}, {"protocol": "paper"})
    tracker.log_metrics({"f1_val": 0.5}, step=0)
    tracker.finish("FINISHED")
    assert (tmp_path / "mlruns" / "mlflow.db").is_file()
    broken = Tracker("notascheme://nowhere", "run-b", {}, {})  # must not raise
    broken.log_metrics({"x": 1.0})
    broken.finish("FINISHED")
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_tracking.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_tracking.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/tracking.py`:

```python
"""Run directories (source of truth) and failure-tolerant MLflow logging."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
import torch_geometric

from grafin_training.errors import ConfigError

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MLFLOW_URI = f"sqlite:///{REPO_ROOT / 'mlruns' / 'mlflow.db'}"
EXPERIMENT = "grafin-training"


def make_run_id(dataset: str, protocol: str, seed: int, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{dataset}-{protocol}-s{seed}"


class RunDir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.checkpoints = path / "checkpoints"

    @classmethod
    def create(cls, root: Path, run_id: str) -> RunDir:
        path = root / run_id
        if path.exists():
            raise ConfigError(f"run directory already exists: {path}")
        (path / "checkpoints").mkdir(parents=True)
        return cls(path)

    @classmethod
    def open(cls, root: Path, run_id: str) -> RunDir:
        path = root / run_id
        if not (path / "config.json").is_file():
            raise ConfigError(f"no run to resume at {path}")
        return cls(path)

    def write_json(self, name: str, obj: Any) -> None:
        tmp = self.path / f".{name}.tmp"
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
        os.replace(tmp, self.path / name)

    def read_json(self, name: str) -> Any:
        return json.loads((self.path / name).read_text())


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def environment_info(device: torch.device) -> dict[str, Any]:
    return {
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": _git("status", "--porcelain") not in ("", "unknown"),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_geometric": torch_geometric.__version__,
        "cuda": torch.version.cuda,
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "host": platform.node(),
    }


def flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in obj.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = value
    return out


class Tracker:
    """MLflow logging that never fails a run: any MLflow error is logged once and disables it."""

    def __init__(
        self, uri: str | None, run_name: str, params: dict[str, Any], tags: dict[str, str]
    ):
        self._mlflow: Any = None
        if uri is None:
            return
        try:
            import mlflow

            if uri.startswith("sqlite:///"):
                Path(uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            mlflow.set_tracking_uri(uri)
            experiment = mlflow.get_experiment_by_name(EXPERIMENT)
            if experiment is None:
                artifacts = Path(uri.removeprefix("sqlite:///")).parent / "artifacts"
                experiment_id = mlflow.create_experiment(
                    EXPERIMENT, artifact_location=artifacts.as_uri()
                )
            else:
                experiment_id = experiment.experiment_id
            mlflow.start_run(run_name=run_name, experiment_id=experiment_id, tags=tags)
            mlflow.log_params({k: str(v)[:500] for k, v in flatten(params).items()})
            self._mlflow = mlflow
        except Exception as exc:  # noqa: BLE001 - tracking must never fail training
            log.warning("MLflow disabled: %s", exc)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.log_metrics(metrics, step=step)
        except Exception as exc:  # noqa: BLE001
            log.warning("MLflow disabled: %s", exc)
            self._mlflow = None

    def finish(self, status: str) -> None:
        if self._mlflow is None:
            return
        try:
            self._mlflow.end_run(status=status)
        except Exception as exc:  # noqa: BLE001
            log.warning("MLflow end_run failed: %s", exc)
        self._mlflow = None
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_tracking.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/tracking.py tests/test_tracking.py
git commit -m "feat: run directories and failure-tolerant MLflow tracking" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 13: GNN training loop (paper protocol)

`train/paper.py` assembles the paper protocol (upstream split, train-only normalisation, three graphs). `train/gnn.py` ports upstream training: degree histogram from the first training batch, `to_hetero(..., aggr='mean')` for reverse MP, weighted cross-entropy, F1 at argmax. Fixes and additions: best-validation checkpoint kept; test split scored only when validation improves (the only test number reported); CPU-tensor checkpoints loaded with `map_location`; `last.pt` with optimizer, scaler and all RNG states so `--resume` continues bit-identically (neighbour sampling draws from the torch RNG — the resume test proves it); NaN loss raises `TrainingDivergedError` leaving the last good checkpoint untouched; optional CUDA AMP (off for parity).

**Files:**
- Create: `tests/test_train.py`
- Create: `grafin_training/train/gnn.py`
- Create: `grafin_training/train/paper.py`
- Create: `grafin_training/train/__init__.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_train.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from grafin_training.config import GnnConfig, load_gnn_config
from grafin_training.data.prepare import prepare_dataset
from grafin_training.errors import TrainingDivergedError
from grafin_training.graph.build import SplitGraph
from grafin_training.tracking import RunDir, Tracker
from grafin_training.train.gnn import load_checkpoint, set_seed, train_gnn
from grafin_training.train.paper import paper_inputs

PAPER = Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml"


def _setup(
    fixture_paths: tuple[Path, Path], tmp_path: Path, epochs: int
) -> tuple[dict[str, SplitGraph], GnnConfig]:
    cfg = load_gnn_config(
        PAPER, {"train.epochs": epochs, "train.batch_size": 32, "train.num_neighs": [10, 10]}
    )
    prepared = prepare_dataset(fixture_paths[0], "raw", tmp_path / "cache")
    graphs, _ = paper_inputs(prepared, cfg)
    return graphs, cfg


def _train(graphs: dict[str, SplitGraph], cfg: GnnConfig, run: RunDir, resume: bool = False):  # type: ignore[no-untyped-def]
    if not resume:
        set_seed(1)
    return train_gnn(
        graphs, cfg, torch.device("cpu"), run, Tracker(None, "t", {}, {}), resume=resume
    )


def test_train_two_epochs_writes_checkpoints(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=2)
    run = RunDir.create(tmp_path / "runs", "r1")
    result = _train(graphs, cfg, run)
    assert [r.epoch for r in result.history] == [0, 1]
    assert 0 <= result.best_epoch <= 1
    assert all(np.isfinite(r.loss) for r in result.history)
    best = load_checkpoint(run.checkpoints / "best.pt")
    assert all(t.device.type == "cpu" for t in best["model"].values())
    assert best["epoch"] == result.best_epoch


def test_resume_reproduces_uninterrupted_run(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg3 = _setup(fixture_paths, tmp_path, epochs=3)
    straight = _train(graphs, cfg3, RunDir.create(tmp_path / "runs", "straight"))

    _, cfg1 = _setup(fixture_paths, tmp_path, epochs=1)
    run = RunDir.create(tmp_path / "runs", "interrupted")
    _train(graphs, cfg1, run)  # "crash" after epoch 0
    resumed = _train(graphs, cfg3, run, resume=True)

    assert [r.loss for r in resumed.history] == [r.loss for r in straight.history]
    assert [r.val_f1 for r in resumed.history] == [r.val_f1 for r in straight.history]


def test_nan_loss_aborts_and_keeps_last_good_checkpoint(
    fixture_paths: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=2)
    run = RunDir.create(tmp_path / "runs", "nan")
    _train(
        graphs,
        load_gnn_config(
            PAPER, {"train.epochs": 1, "train.batch_size": 32, "train.num_neighs": [10, 10]}
        ),
        run,
    )
    before = (run.checkpoints / "last.pt").read_bytes()

    def nan_loss(self: torch.nn.Module, *args: object, **kwargs: object) -> torch.Tensor:
        return torch.tensor(float("nan"), requires_grad=True)

    monkeypatch.setattr(torch.nn.CrossEntropyLoss, "forward", nan_loss)
    with pytest.raises(TrainingDivergedError):
        _train(graphs, cfg, run, resume=True)
    assert (run.checkpoints / "last.pt").read_bytes() == before


def test_test_split_scored_only_when_validation_improves(
    fixture_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    graphs, cfg = _setup(fixture_paths, tmp_path, epochs=4)
    result = _train(graphs, cfg, RunDir.create(tmp_path / "runs", "lazy-test"))
    best = -1.0
    for record in result.history:
        improved = record.val_f1 > best
        assert (record.test_f1 is not None) == improved
        best = max(best, record.val_f1)
    best_record = next(r for r in result.history if r.epoch == result.best_epoch)
    assert result.test_f1_at_best == best_record.test_f1
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_train.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_train.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/train/gnn.py`:

```python
"""GNN training loop (port of upstream training.py / train_util.py) with best-val checkpointing,
resume, CPU-tensor checkpoints and a NaN guard."""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import torch
from sklearn.metrics import f1_score
from torch.amp.grad_scaler import GradScaler
from torch_geometric.data import Data, HeteroData
from torch_geometric.nn import to_hetero
from torch_geometric.utils import degree

from grafin_training.config import GnnConfig
from grafin_training.errors import TrainingDivergedError
from grafin_training.graph.build import EDGE, REV, SplitGraph
from grafin_training.graph.loaders import make_loader, seed_mask
from grafin_training.models.multignn import PNA
from grafin_training.tracking import RunDir, Tracker

log = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    """Upstream util.set_seed."""
    np.random.seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    os.environ["PYTHONHASHSEED"] = str(seed)


def build_model(sample_batch: Data | HeteroData, cfg: GnnConfig) -> torch.nn.Module:
    """Upstream training.get_model for PNA: degree histogram from the first training batch."""
    hetero = isinstance(sample_batch, HeteroData)
    n_feats = (sample_batch["node"].x if hetero else sample_batch.x).shape[1]
    e_dim = (sample_batch[EDGE].edge_attr if hetero else sample_batch.edge_attr).shape[1]
    if hetero:
        index = torch.cat((sample_batch[EDGE].edge_index[1], sample_batch[REV].edge_index[1]), 0)
    else:
        index = sample_batch.edge_index[1]
    deg = torch.bincount(degree(index, dtype=torch.long), minlength=1)
    model: torch.nn.Module = PNA(
        num_features=n_feats,
        num_gnn_layers=cfg.model.n_gnn_layers,
        n_classes=2,
        n_hidden=round(cfg.model.n_hidden),
        edge_updates=cfg.model.edge_updates,
        edge_dim=e_dim,
        dropout=cfg.model.dropout,
        deg=deg,
        final_dropout=cfg.model.final_dropout,
    )
    if hetero:
        model = to_hetero(model, sample_batch.metadata(), aggr="mean")
    return model


def forward_edges(
    model: torch.nn.Module, batch: Data | HeteroData
) -> tuple[torch.Tensor, torch.Tensor]:
    """(logits, labels) for the batch's forward edges."""
    if isinstance(batch, HeteroData):
        out = model(batch.x_dict, batch.edge_index_dict, batch.edge_attr_dict)[EDGE]
        return out, batch[EDGE].y
    return model(batch.x, batch.edge_index, batch.edge_attr), batch.y


@dataclass
class Scores:
    prob: npt.NDArray[np.float32]
    y: npt.NDArray[np.int64]
    coverage: float

    @property
    def f1(self) -> float:
        return float(f1_score(self.y, self.prob > 0.5, zero_division=0))


@torch.no_grad()
def predict(
    model: torch.nn.Module,
    graph: SplitGraph,
    cfg: GnnConfig,
    device: torch.device,
    max_batches: int | None = None,
) -> Scores:
    """P(laundering) for the seed edges that were sampled (paper protocol)."""
    model.eval()
    loader = make_loader(
        graph,
        num_neighs=cfg.train.num_neighs,
        batch_size=cfg.train.batch_size,
        shuffle=False,
        ego=cfg.flags.ego,
    )
    probs: list[torch.Tensor] = []
    ys: list[torch.Tensor] = []
    seen = total = 0
    for k, batch in enumerate(loader):
        if max_batches is not None and k >= max_batches:
            break
        mask, n_seeds = seed_mask(batch, graph.seeds)
        total += n_seeds
        seen += int(mask.sum())
        logits, y = forward_edges(model, batch.to(device))
        mask = mask.to(device)
        probs.append(torch.softmax(logits[mask].float(), dim=-1)[:, 1].cpu())
        ys.append(y[mask].cpu())
    prob = torch.cat(probs).numpy().astype(np.float32) if probs else np.zeros(0, np.float32)
    y_all = torch.cat(ys).numpy().astype(np.int64) if ys else np.zeros(0, np.int64)
    return Scores(prob, y_all, seen / total if total else 0.0)


@dataclass
class EpochRecord:
    epoch: int
    loss: float
    train_f1: float
    val_f1: float
    test_f1: float | None  # scored only when validation F1 improves (the reported number)
    val_coverage: float
    test_coverage: float | None
    seconds: float


@dataclass
class TrainState:
    next_epoch: int = 0
    best_epoch: int = -1
    best_val_f1: float = -1.0
    history: list[EpochRecord] = field(default_factory=list)


@dataclass(frozen=True)
class TrainResult:
    best_epoch: int
    best_val_f1: float
    test_f1_at_best: float
    history: list[EpochRecord]
    peak_gpu_mem_mb: float | None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["history"] = [asdict(r) for r in self.history]
        return out


def _to_cpu(obj: Any) -> Any:
    if isinstance(obj, torch.Tensor):
        return obj.detach().cpu()
    if isinstance(obj, dict):
        return {k: _to_cpu(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_cpu(v) for v in obj]
    return obj


def _rng_state() -> dict[str, Any]:
    return {
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        "numpy": np.random.get_state(),
        "python": random.getstate(),
    }


def _restore_rng(state: dict[str, Any]) -> None:
    torch.set_rng_state(state["torch"])
    if state["cuda"] is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["cuda"])
    np.random.set_state(state["numpy"])
    random.setstate(state["python"])


def save_checkpoint(path: Any, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    torch.save(_to_cpu(payload), tmp)
    os.replace(tmp, path)


def load_checkpoint(path: Any) -> dict[str, Any]:
    ckpt: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=False)
    return ckpt


def train_gnn(
    graphs: dict[str, SplitGraph],
    cfg: GnnConfig,
    device: torch.device,
    run: RunDir,
    tracker: Tracker,
    *,
    resume: bool = False,
    max_batches: int | None = None,
) -> TrainResult:
    """Train on graphs['train'], select the epoch by graphs['val'] F1, report graphs['test'] F1.
    Call set_seed() first: the sample batch and all shuffles/sampling draw from the torch RNG."""
    tr_loader = make_loader(
        graphs["train"],
        num_neighs=cfg.train.num_neighs,
        batch_size=cfg.train.batch_size,
        shuffle=True,
        ego=cfg.flags.ego,
    )
    model = build_model(next(iter(tr_loader)), cfg).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.train.lr)
    use_amp = cfg.train.amp and device.type == "cuda"
    scaler = GradScaler("cuda", enabled=use_amp)
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor([cfg.train.w_ce1, cfg.train.w_ce2], dtype=torch.float32).to(device)
    )
    state = TrainState()
    last_path = run.checkpoints / "last.pt"
    best_path = run.checkpoints / "best.pt"
    if resume:
        ckpt = load_checkpoint(last_path)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scaler.load_state_dict(ckpt["scaler"])
        state = TrainState(
            next_epoch=ckpt["epoch"] + 1,
            best_epoch=ckpt["best_epoch"],
            best_val_f1=ckpt["best_val_f1"],
            history=[EpochRecord(**r) for r in ckpt["history"]],
        )
        _restore_rng(ckpt["rng"])
        log.info("resumed at epoch %d", state.next_epoch)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    for epoch in range(state.next_epoch, cfg.train.epochs):
        start = time.perf_counter()
        model.train()
        total_loss = 0.0
        n_examples = 0
        preds: list[torch.Tensor] = []
        truths: list[torch.Tensor] = []
        for k, batch in enumerate(tr_loader):
            if max_batches is not None and k >= max_batches:
                break
            mask, _ = seed_mask(batch, graphs["train"].seeds)
            if not bool(mask.any()):
                continue
            optimizer.zero_grad()
            batch = batch.to(device)
            mask = mask.to(device)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits, y = forward_edges(model, batch)
                pred = logits[mask]
                truth = y[mask]
                loss = loss_fn(pred.float(), truth)
            if not torch.isfinite(loss):
                raise TrainingDivergedError(
                    f"non-finite loss at epoch {epoch} batch {k}; last good checkpoint: {last_path}"
                )
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_loss += float(loss) * pred.shape[0]
            n_examples += pred.shape[0]
            preds.append(pred.argmax(dim=-1).cpu())
            truths.append(truth.cpu())
        train_f1 = float(f1_score(torch.cat(truths), torch.cat(preds), zero_division=0))
        val = predict(model, graphs["val"], cfg, device, max_batches)
        improved = val.f1 > state.best_val_f1
        test = predict(model, graphs["test"], cfg, device, max_batches) if improved else None
        record = EpochRecord(
            epoch=epoch,
            loss=total_loss / max(n_examples, 1),
            train_f1=train_f1,
            val_f1=val.f1,
            test_f1=test.f1 if test else None,
            val_coverage=val.coverage,
            test_coverage=test.coverage if test else None,
            seconds=time.perf_counter() - start,
        )
        state.history.append(record)
        log.info(
            "epoch %d loss %.4f train_f1 %.4f val_f1 %.4f test_f1 %s (%.0fs)",
            epoch,
            record.loss,
            train_f1,
            val.f1,
            f"{test.f1:.4f}" if test else "-",
            record.seconds,
        )
        metrics = {"loss": record.loss, "f1_train": train_f1, "f1_val": val.f1}
        if test:
            metrics["f1_test"] = test.f1
        tracker.log_metrics(metrics, step=epoch)
        if improved:
            state.best_epoch, state.best_val_f1 = epoch, val.f1
            save_checkpoint(
                best_path, {"model": model.state_dict(), "epoch": epoch, "val_f1": val.f1}
            )
        save_checkpoint(
            last_path,
            {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "epoch": epoch,
                "best_epoch": state.best_epoch,
                "best_val_f1": state.best_val_f1,
                "history": [asdict(r) for r in state.history],
                "rng": _rng_state(),
            },
        )

    best = next((r for r in state.history if r.epoch == state.best_epoch), None)
    peak = torch.cuda.max_memory_allocated(device) / 2**20 if device.type == "cuda" else None
    return TrainResult(
        best_epoch=state.best_epoch,
        best_val_f1=state.best_val_f1,
        test_f1_at_best=best.test_f1 if best and best.test_f1 is not None else float("nan"),
        history=state.history,
        peak_gpu_mem_mb=peak,
    )
```

`grafin_training/train/paper.py`:

```python
"""Paper protocol inputs: upstream day split, train-only normalisation, three split graphs."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from grafin_training.config import GnnConfig
from grafin_training.data.features import apply_norm, fit_norm
from grafin_training.data.prepare import PreparedData
from grafin_training.data.split import paper_split, rows_for_days
from grafin_training.graph.build import SplitGraph, paper_graphs


def paper_inputs(
    prepared: PreparedData, cfg: GnnConfig
) -> tuple[dict[str, SplitGraph], dict[str, Any]]:
    """Graphs for train / val / test plus the facts recorded in the run's data.json."""
    split = paper_split(prepared.day_idx, cfg.split.fractions)
    rows = {
        "train": rows_for_days(prepared.day_idx, split.train_days),
        "val": rows_for_days(prepared.day_idx, split.val_days),
        "test": rows_for_days(prepared.day_idx, split.test_days),
    }
    feats = prepared.edge_features(ports=cfg.flags.ports, tds=cfg.flags.tds)
    stats = fit_norm(feats, rows["train"])
    graphs = paper_graphs(
        prepared.num_nodes,
        torch.from_numpy(np.vstack([prepared.src, prepared.dst])),
        torch.from_numpy(apply_norm(feats, stats)),
        torch.from_numpy(prepared.y),
        rows,
        reverse_mp=cfg.flags.reverse_mp,
        ports=cfg.flags.ports,
    )
    data_info = {
        "meta": prepared.meta,
        "split": split.to_dict(),
        "counts": {k: int(v.shape[0]) for k, v in rows.items()},
        "laundering": {k: int(prepared.y[v].sum()) for k, v in rows.items()},
        "norm": stats.to_dict(),
    }
    return graphs, data_info
```

`grafin_training/train/__init__.py`:

```python

```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_train.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/train/__init__.py grafin_training/train/gnn.py grafin_training/train/paper.py tests/test_train.py
git commit -m "feat: Multi-GNN training loop with best-val checkpoints, resume, NaN guard" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 14: `grafin-train` CLI and run comparison

Subcommands `prepare`, `gnn` (new run or `--resume RUN_ID`, which reloads the saved config and refuses if the dataset hash changed) and `compare` (markdown table plus mean ± std of test F1 per dataset/source/protocol). Every `GrafinTrainError` maps to its exit code.

**Files:**
- Create: `tests/test_cli.py`
- Create: `grafin_training/report.py`
- Create: `grafin_training/cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from grafin_training.cli import main

PAPER = str(Path(__file__).resolve().parents[1] / "configs" / "paper_pna.toml")


def test_cli_prepare_then_gnn_then_compare(
    fixture_paths: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = str(fixture_paths[0])
    cache = str(tmp_path / "cache")
    assert main(["prepare", "--data", raw, "--source", "raw", "--cache-dir", cache]) == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta["n_edges"] == 229 and meta["laundering"] == 13
    assert main(["prepare", "--data", raw, "--source", "raw", "--cache-dir", cache]) == 0  # cached

    code = main(
        [
            "gnn",
            "--data",
            raw,
            "--source",
            "raw",
            "--config",
            PAPER,
            "--epochs",
            "2",
            "--batch-size",
            "32",
            "--num-neighs",
            "10",
            "10",
            "--device",
            "cpu",
            "--run-id",
            "smoke",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--cache-dir",
            cache,
            "--no-mlflow",
        ]
    )
    assert code == 0
    run = tmp_path / "runs" / "smoke"
    for name in ("config.json", "env.json", "data.json", "metrics.json", "log.txt"):
        assert (run / name).is_file(), name
    data = json.loads((run / "data.json").read_text())
    assert sum(data["counts"].values()) == 229
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["protocol"] == "paper" and len(metrics["history"]) == 2

    capsys.readouterr()
    assert main(["compare", "--runs-dir", str(tmp_path / "runs")]) == 0
    out = capsys.readouterr().out
    assert "| smoke |" in out and "HI-Fixture_Trans" in out


def test_cli_exit_codes(fixture_paths: tuple[Path, Path], tmp_path: Path) -> None:
    common = [
        "--runs-dir",
        str(tmp_path / "runs"),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--no-mlflow",
    ]
    missing = ["gnn", "--data", str(tmp_path / "nope.csv"), "--source", "raw", "--device", "cpu"]
    assert main(missing + common) == 2
    bad_cfg = tmp_path / "bad.toml"
    bad_cfg.write_text("[model]\nname='gin'\n")
    assert (
        main(
            [
                "gnn",
                "--data",
                str(fixture_paths[0]),
                "--source",
                "raw",
                "--config",
                str(bad_cfg),
                "--device",
                "cpu",
                *common,
            ]
        )
        == 3
    )
    assert (
        main(
            [
                "gnn",
                "--data",
                str(fixture_paths[0]),
                "--source",
                "bogus",
                "--device",
                "cpu",
                *common,
            ]
        )
        == 3
    )
    if not torch.cuda.is_available():
        assert (
            main(
                [
                    "gnn",
                    "--data",
                    str(fixture_paths[0]),
                    "--source",
                    "raw",
                    "--device",
                    "cuda",
                    *common,
                ]
            )
            == 5
        )
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for the module this task creates (collection error in `tests/test_cli.py`).

- [ ] **Step 3: Write the implementation**

`grafin_training/report.py`:

```python
"""`compare`: markdown table of finished runs plus mean ± std per (dataset, source, protocol)."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


def collect_runs(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in sorted(p for p in root.iterdir() if (p / "metrics.json").is_file()):
        config = json.loads((run / "config.json").read_text())
        data = json.loads((run / "data.json").read_text())
        metrics = json.loads((run / "metrics.json").read_text())
        best: dict[str, Any] = next(
            (r for r in metrics["history"] if r["epoch"] == metrics["best_epoch"]), {}
        )
        rows.append(
            {
                "run_id": run.name,
                "dataset": data["meta"]["dataset"],
                "source": data["meta"]["source"],
                "protocol": config["protocol"],
                "seed": config["seed"],
                "epochs": len(metrics["history"]),
                "best_epoch": metrics["best_epoch"],
                "val_f1": metrics["best_val_f1"],
                "test_f1": metrics["test_f1_at_best"],
                "test_coverage": best.get("test_coverage") or float("nan"),
            }
        )
    return rows


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| run | dataset | source | protocol | seed | epochs | best epoch | val F1 | test F1 | test coverage |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['run_id']} | {r['dataset']} | {r['source']} | {r['protocol']} | {r['seed']} "
            f"| {r['epochs']} | {r['best_epoch']} | {100 * r['val_f1']:.2f} "
            f"| {100 * r['test_f1']:.2f} | {100 * r['test_coverage']:.1f}% |"
        )
    groups: dict[tuple[str, str, str], list[float]] = {}
    for r in rows:
        groups.setdefault((r["dataset"], r["source"], r["protocol"]), []).append(100 * r["test_f1"])
    lines += [
        "",
        "| dataset | source | protocol | runs | test F1 mean ± std |",
        "|---|---|---|---|---|",
    ]
    for (dataset, source, protocol), values in sorted(groups.items()):
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        lines.append(
            f"| {dataset} | {source} | {protocol} | {len(values)} "
            f"| {statistics.mean(values):.2f} ± {std:.2f} |"
        )
    return "\n".join(lines)
```

`grafin_training/cli.py`:

```python
"""`grafin-train` command line: prepare | gnn | compare."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from grafin_training.config import load_gnn_config, parse_gnn_config
from grafin_training.data.load import as_source
from grafin_training.data.prepare import prepare_dataset
from grafin_training.device import DEVICE_CHOICES, resolve_device
from grafin_training.errors import ConfigError, DatasetError, GrafinTrainError
from grafin_training.report import collect_runs, render_markdown
from grafin_training.tracking import (
    DEFAULT_MLFLOW_URI,
    RunDir,
    Tracker,
    environment_info,
    make_run_id,
)
from grafin_training.train.gnn import set_seed, train_gnn
from grafin_training.train.paper import paper_inputs

log = logging.getLogger("grafin_training")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grafin-train")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="verify, read and cache a transactions CSV")
    prep.add_argument("--data", required=True, type=Path, help="transactions CSV")
    prep.add_argument("--source", required=True, help="raw | id")
    prep.add_argument("--cache-dir", type=Path, default=Path("cache"))
    prep.set_defaults(func=cmd_prepare)

    gnn = sub.add_parser("gnn", help="train the Multi-GNN")
    gnn.add_argument("--data", type=Path, help="transactions CSV (not needed with --resume)")
    gnn.add_argument("--source", help="raw | id (not needed with --resume)")
    gnn.add_argument("--config", type=Path, default=Path("configs/paper_pna.toml"))
    gnn.add_argument("--protocol", choices=["paper"], default="paper")
    gnn.add_argument("--seed", type=int, default=1)
    gnn.add_argument("--device", choices=DEVICE_CHOICES, default="auto")
    gnn.add_argument("--epochs", type=int)
    gnn.add_argument("--batch-size", type=int)
    gnn.add_argument("--num-neighs", type=int, nargs="+")
    gnn.add_argument("--max-batches", type=int, help="cap batches per loader (smoke tests)")
    gnn.add_argument("--runs-dir", type=Path, default=Path("runs"))
    gnn.add_argument("--cache-dir", type=Path, default=Path("cache"))
    gnn.add_argument(
        "--run-id", help="name for a new run (default: timestamp-dataset-protocol-seed)"
    )
    gnn.add_argument("--resume", metavar="RUN_ID", help="continue an interrupted run")
    gnn.add_argument("--mlflow-uri", default=DEFAULT_MLFLOW_URI)
    gnn.add_argument("--no-mlflow", action="store_true")
    gnn.set_defaults(func=cmd_gnn)

    cmp = sub.add_parser("compare", help="markdown table of finished runs")
    cmp.add_argument("--runs-dir", type=Path, default=Path("runs"))
    cmp.set_defaults(func=cmd_compare)
    return parser


def cmd_prepare(args: argparse.Namespace) -> int:
    prepared = prepare_dataset(args.data, as_source(args.source), args.cache_dir)
    print(json.dumps({"cache_dir": str(prepared.cache_dir), **prepared.meta}, indent=2))
    return 0


def cmd_gnn(args: argparse.Namespace) -> int:
    device = resolve_device(args.device)
    if args.resume:
        run = RunDir.open(args.runs_dir, args.resume)
        saved = run.read_json("config.json")
        cfg = parse_gnn_config(saved["gnn"])
        seed, max_batches = saved["seed"], saved["max_batches"]
        data_path, source = Path(saved["data"]["path"]), as_source(saved["data"]["source"])
    else:
        if args.data is None or args.source is None:
            raise ConfigError("--data and --source are required unless --resume is given")
        overrides: dict[str, Any] = {}
        if args.epochs is not None:
            overrides["train.epochs"] = args.epochs
        if args.batch_size is not None:
            overrides["train.batch_size"] = args.batch_size
        if args.num_neighs is not None:
            overrides["train.num_neighs"] = list(args.num_neighs)
        cfg = load_gnn_config(args.config, overrides)
        seed, max_batches = args.seed, args.max_batches
        data_path, source = args.data, as_source(args.source)

    prepared = prepare_dataset(data_path, source, args.cache_dir)
    if args.resume and prepared.meta["sha256"] != saved["data"]["sha256"]:
        raise DatasetError("dataset changed since the run started; refusing to resume")
    graphs, data_info = paper_inputs(prepared, cfg)

    config = {
        "gnn": cfg.to_dict(),
        "seed": seed,
        "protocol": args.protocol,
        "max_batches": max_batches,
        "data": {"path": str(data_path), "source": source, "sha256": prepared.meta["sha256"]},
    }
    if not args.resume:
        run_id = args.run_id or make_run_id(prepared.meta["dataset"], args.protocol, seed)
        run = RunDir.create(args.runs_dir, run_id)
        run.write_json("config.json", config)
    run.write_json("env.json", environment_info(device))
    run.write_json("data.json", data_info)
    handler = logging.FileHandler(run.path / "log.txt")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)

    tracker = Tracker(
        None if args.no_mlflow else args.mlflow_uri,
        run_name=run.path.name,
        params=config,
        tags={"run_dir": str(run.path.resolve()), "protocol": args.protocol},
    )
    set_seed(seed)
    try:
        result = train_gnn(
            graphs, cfg, device, run, tracker, resume=bool(args.resume), max_batches=max_batches
        )
    except BaseException:
        tracker.finish("FAILED")
        raise
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
    run.write_json("metrics.json", {"protocol": args.protocol, **result.to_dict()})
    tracker.log_metrics(
        {"best_val_f1": result.best_val_f1, "test_f1_at_best": result.test_f1_at_best}
    )
    tracker.finish("FINISHED")
    print(run.path)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    if not args.runs_dir.is_dir():
        raise ConfigError(f"no runs directory at {args.runs_dir}")
    print(render_markdown(collect_runs(args.runs_dir)))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    try:
        return int(args.func(args))
    except GrafinTrainError as exc:
        log.error("%s", exc)
        return exc.exit_code


def run() -> None:
    sys.exit(main())
```

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_cli.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add grafin_training/cli.py grafin_training/report.py tests/test_cli.py
git commit -m "feat: grafin-train CLI (prepare, gnn, compare)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 15: GCP ops scripts, job files and README

Operator scripts for the 4×T4 VM: create (Deep Learning VM image with the NVIDIA driver), set up (uv + CUDA 12.4 wheels, GPU check, data pull), GCS sync, and `run_parallel.sh` (line *i* of a jobs file runs on GPU *i*; non-zero exit if any job fails; bash-3 compatible so it can be tested on the Mac). `probe.jobs` measures seconds/batch and GPU memory before committing a wave; `wave1_parity.jobs` is the parity + currency-check wave. Nothing here calls GCP during tests.

**Files:**
- Create: `ops/vm.env.example`
- Create: `ops/_env.sh`
- Create: `ops/vm_create.sh`
- Create: `ops/vm_setup.sh`
- Create: `ops/sync.sh`
- Create: `ops/run_parallel.sh`
- Create: `ops/jobs/probe.jobs`
- Create: `ops/jobs/wave1_parity.jobs`
- Create: `README.md`

- [ ] **Step 1: Write the implementation**

`ops/vm.env.example`:

```bash
# Copy to ops/vm.env (gitignored) and fill in. Sourced by every ops/*.sh script.
GRAFIN_GCP_PROJECT=your-project-id
GRAFIN_GCP_ZONE=asia-southeast2-a          # pick a zone with T4 quota: gcloud compute accelerator-types list --filter=name=nvidia-tesla-t4
GRAFIN_VM_NAME=grafin-train
GRAFIN_VM_TYPE=n1-highmem-16               # 104 GB RAM: 4 parallel HI-Medium jobs. n1-highmem-8 (52 GB) is enough for HI-Small.
GRAFIN_GPU_COUNT=4
GRAFIN_IMAGE_FAMILY=common-cu124-ubuntu-2204-py310   # list: see ops/vm_create.sh
GRAFIN_DISK_GB=300
GRAFIN_GCS_BUCKET=your-bucket-name
GRAFIN_EXTRA=cu124
```

`ops/_env.sh`:

```bash
# shellcheck shell=bash
# Shared by ops scripts: load ops/vm.env and fail on unset variables.
set -euo pipefail
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$OPS_DIR/.." && pwd)"
if [[ -f "$OPS_DIR/vm.env" ]]; then
  # shellcheck disable=SC1091
  source "$OPS_DIR/vm.env"
fi
require() {
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      echo "error: $name is not set (copy ops/vm.env.example to ops/vm.env)" >&2
      exit 3
    fi
  done
}
```

`ops/vm_create.sh`:

```bash
#!/usr/bin/env bash
# Create the training VM (run on your laptop). Deep Learning VM images ship the NVIDIA driver.
# List current CUDA 12 image families if the default is retired:
#   gcloud compute images list --project deeplearning-platform-release --no-standard-images \
#     --filter="family~cu12" --format="value(family)" | sort -u
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCP_PROJECT GRAFIN_GCP_ZONE GRAFIN_VM_NAME GRAFIN_VM_TYPE GRAFIN_GPU_COUNT \
  GRAFIN_IMAGE_FAMILY GRAFIN_DISK_GB
gcloud compute instances create "$GRAFIN_VM_NAME" \
  --project "$GRAFIN_GCP_PROJECT" \
  --zone "$GRAFIN_GCP_ZONE" \
  --machine-type "$GRAFIN_VM_TYPE" \
  --accelerator "type=nvidia-tesla-t4,count=$GRAFIN_GPU_COUNT" \
  --maintenance-policy TERMINATE \
  --image-family "$GRAFIN_IMAGE_FAMILY" \
  --image-project deeplearning-platform-release \
  --boot-disk-size "${GRAFIN_DISK_GB}GB" \
  --metadata install-nvidia-driver=True \
  --scopes cloud-platform
echo "created. next: gcloud compute ssh $GRAFIN_VM_NAME --zone $GRAFIN_GCP_ZONE, clone the repo, run ops/vm_setup.sh"
echo "STOP THE VM WHEN IDLE: gcloud compute instances stop $GRAFIN_VM_NAME --zone $GRAFIN_GCP_ZONE"
```

`ops/vm_setup.sh`:

```bash
#!/usr/bin/env bash
# Run ON the VM inside the cloned repo: checks GPUs, installs uv + CUDA deps, pulls data.
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCS_BUCKET GRAFIN_EXTRA
nvidia-smi -L
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$REPO_DIR"
uv python install 3.11
uv sync --frozen --extra "$GRAFIN_EXTRA"
uv run --extra "$GRAFIN_EXTRA" python -c \
  "import torch, torch_geometric.typing as t; n = torch.cuda.device_count(); assert n > 0 and t.WITH_PYG_LIB; print(f'cuda ok: {n} GPU(s)')"
"$OPS_DIR/sync.sh" pull-data
```

`ops/sync.sh`:

```bash
#!/usr/bin/env bash
# Data and results <-> gs://$GRAFIN_GCS_BUCKET. Data lives in ../grafin-ai-data next to the repo.
#   push-data     laptop -> bucket: raw/HI-Small, HI-Small-ID, HI-Medium-ID
#   pull-data     bucket -> VM
#   push-results  runs/ mlruns/ bundles/ -> bucket
#   pull-results  bucket -> laptop
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCS_BUCKET
DATA_DIR="$(cd "$REPO_DIR/.." && pwd)/grafin-ai-data"
BUCKET="gs://$GRAFIN_GCS_BUCKET"
DATASETS=(raw/HI-Small HI-Small-ID HI-Medium-ID)
rsync_dir() {
  if [[ "$2" != gs://* ]]; then mkdir -p "$2"; fi
  gcloud storage rsync --recursive "$1" "$2"
}
case "${1:-}" in
  push-data)
    for d in "${DATASETS[@]}"; do rsync_dir "$DATA_DIR/$d" "$BUCKET/data/$d"; done ;;
  pull-data)
    for d in "${DATASETS[@]}"; do rsync_dir "$BUCKET/data/$d" "$DATA_DIR/$d"; done ;;
  push-results)
    for d in runs mlruns bundles; do
      if [[ -d "$REPO_DIR/$d" ]]; then rsync_dir "$REPO_DIR/$d" "$BUCKET/$d"; fi
    done ;;
  pull-results)
    for d in runs mlruns bundles; do rsync_dir "$BUCKET/$d" "$REPO_DIR/$d" || true; done ;;
  *)
    echo "usage: $0 push-data|pull-data|push-results|pull-results" >&2; exit 3 ;;
esac
```

`ops/run_parallel.sh`:

```bash
#!/usr/bin/env bash
# Run one grafin-train job per GPU: line i of JOBS_FILE runs on GPU i (CUDA_VISIBLE_DEVICES=i).
# Lines are grafin-train arguments; blank lines and '#' comments are ignored.
# Exits non-zero if any job fails. Logs: logs/<jobs-name>-gpu<i>.log
#   usage: ops/run_parallel.sh ops/jobs/wave1_parity.jobs
source "$(dirname "$0")/_env.sh"
JOBS_FILE="${1:?usage: $0 JOBS_FILE}"
EXTRA="${GRAFIN_EXTRA:-cu124}"
N_GPUS="${N_GPUS:-$(nvidia-smi -L | wc -l)}"
JOBS=()
while IFS= read -r line; do
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  JOBS+=("$line")
done <"$JOBS_FILE"
if (( ${#JOBS[@]} > N_GPUS )); then
  echo "error: ${#JOBS[@]} jobs but only $N_GPUS GPUs" >&2; exit 3
fi
cd "$REPO_DIR"
mkdir -p logs
name="$(basename "$JOBS_FILE" .jobs)"
pids=()
for i in "${!JOBS[@]}"; do
  log="logs/${name}-gpu${i}.log"
  # shellcheck disable=SC2086 # job lines are intentionally word-split into arguments
  CUDA_VISIBLE_DEVICES="$i" nohup uv run --extra "$EXTRA" grafin-train ${JOBS[$i]} >"$log" 2>&1 &
  pids+=("$!")
  echo "gpu$i pid $!: grafin-train ${JOBS[$i]}  (log: $log)"
done
failed=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    echo "job on gpu$i FAILED (see logs/${name}-gpu${i}.log)" >&2
    failed=1
  fi
done
exit "$failed"
```

`ops/jobs/probe.jobs`:

```text
# One short job to measure seconds/batch and GPU memory before committing to a wave.
gnn --data ../grafin-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv --source id --seed 1 --device cuda --epochs 1 --max-batches 20 --run-id probe-small-id --no-mlflow
```

`ops/jobs/wave1_parity.jobs`:

```text
# Wave 1 — paper protocol on HI-Small: parity (raw, criterion 1) and currency check (ID, criterion 2).
gnn --data ../grafin-ai-data/raw/HI-Small/HI-Small_Trans.csv --source raw --seed 1 --device cuda
gnn --data ../grafin-ai-data/raw/HI-Small/HI-Small_Trans.csv --source raw --seed 2 --device cuda
gnn --data ../grafin-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv --source id --seed 1 --device cuda
gnn --data ../grafin-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv --source id --seed 2 --device cuda
```

`README.md`:

````markdown
# grafin-ai-training

Training repo for the Grafin AI fraud scorer. It is a faithful port of
[IBM/Multi-GNN](https://github.com/IBM/Multi-GNN) (Egressy et al., AAAI 2024) with the bugs found
in our earlier fork fixed. It trains on the Indonesian-localized IBM AML data produced by
`grafin-ai-dataset`.

> **Status — Plan A (foundation + paper protocol).** It can reproduce the paper's Multi-PNA+EU
> numbers and compare raw vs localized data. Plan B adds the causal protocol, the scorer heads
> (XGBoost / LightGBM / CatBoost / MLP), ONNX export and the model bundle for `grafin-ai-scoring`.

Design: [docs/superpowers/specs/2026-10-17-training-repo-design.md](docs/superpowers/specs/2026-10-17-training-repo-design.md)

## Quickstart (Mac, CPU)

```bash
make install        # uv sync (arm64 Python 3.11 is pinned in .python-version)
make check          # ruff + mypy --strict + pytest
make smoke          # synthetic fixture end to end, ~10 s
make smoke-small    # real HI-Small-ID, 3 batches per loader, ~5 min
```

Datasets are expected next to the repo in `../grafin-ai-data` (produced by `grafin-ai-dataset`):

| `--source` | file | integrity check |
|---|---|---|
| `raw` | `raw/HI-Small/HI-Small_Trans.csv` | `SHA256SUMS` in the same folder |
| `id` | `HI-Small-ID/HI-Small_Trans_sorted.csv`, `HI-Medium-ID/HI-Medium_Trans_sorted.csv` | `MANIFEST.json` in the same folder |

## Commands

```bash
grafin-train prepare --data FILE --source raw|id          # verify + cache (cache/<source>-<sha16>/)
grafin-train gnn --data FILE --source raw|id --seed 1 --device cuda [--epochs N] [--batch-size N] [--num-neighs A B]
grafin-train gnn --resume RUN_ID                          # continue an interrupted run
grafin-train compare                                      # markdown table of runs/ (mean ± std per dataset)
```

Each run writes `runs/<run-id>/` with `config.json`, `env.json` (git SHA, versions, device),
`data.json` (split days, counts, normalization stats), `metrics.json`, `log.txt` and
`checkpoints/{best,last}.pt`. The run directory is the source of truth. MLflow (SQLite at
`mlruns/mlflow.db`) mirrors the parameters and metrics:
`uvx mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db`.

Exit codes: `0` ok · `1` unexpected or training diverged · `2` dataset missing or hash mismatch ·
`3` bad config or arguments · `4` export check failed (Plan B) · `5` CUDA requested but missing.

## GPU runbook (GCP, 4×T4)

1. `cp ops/vm.env.example ops/vm.env` and fill in the project, zone, bucket and VM type.
   n1-highmem-8 is enough for HI-Small; use n1-highmem-16 for 4 parallel HI-Medium jobs.
2. Laptop: `ops/sync.sh push-data`, then `ops/vm_create.sh`.
3. VM: clone the repo next to an empty `grafin-ai-data/`, copy `ops/vm.env`, run `ops/vm_setup.sh`
   (checks GPUs, installs uv + CUDA 12.4 wheels, pulls data).
4. Probe first: `ops/run_parallel.sh ops/jobs/probe.jobs`, then read `seconds` and
   `peak_gpu_mem_mb` in `runs/probe-small-id/metrics.json`. If a T4 runs out of memory, lower
   `--batch-size`.
5. Wave 1: `ops/run_parallel.sh ops/jobs/wave1_parity.jobs` (one job per GPU). Use `tmux` so the
   jobs survive SSH disconnects.
6. `ops/sync.sh push-results` on the VM, `ops/sync.sh pull-results` on the laptop, then
   `make compare`. **Stop the VM when idle.**

Linux always needs an extra: `make install EXTRA=cu124` (GPU) or `EXTRA=cpu` (CI).

## Fidelity to the paper

- `grafin_training/models/multignn.py` is upstream `models.py` byte for byte (a test checks its sha256).
- The split, ports, time deltas, ego IDs, reverse message passing and hyper-parameters match
  upstream. Tests compare against verbatim upstream code in `tests/upstream_ref.py`.
- One upstream quirk is reproduced on purpose: with reverse MP, the port swap meant for
  `rev_to` edges also lands on `to` edges.
- Deliberate fixes:
  - normalization uses training statistics only;
  - checkpoints are device-independent;
  - the best-validation checkpoint is kept;
  - the old fork's `--bidirectional_mp` is removed.
- The test split is scored only in epochs where validation F1 improves, which is the only number
  reported.

## Results

| Run set | Target | Result |
|---|---|---|
| Multi-PNA+EU, raw HI-Small, paper protocol (seeds 1, 2) | 68.16 ± 2.65 → pass if mean in [62.86, 73.46] | pending (Wave 1) |
| Same on HI-Small-ID (currency-loss check) | report the difference vs raw | pending (Wave 1) |

Licensed Apache-2.0; see `NOTICE` for the IBM attribution.
````

- [ ] **Step 2: Run** `chmod +x ops/*.sh` (no output expected)

- [ ] **Step 3: Run** `for f in ops/*.sh; do bash -n "$f"; done` (no output expected)

- [ ] **Step 4: Verify**

Run: `make check && make smoke`
Expected: ruff + mypy clean, all tests pass (42), smoke prints a compare table with one HI-Fixture_Trans paper run

- [ ] **Step 5: Commit**

```bash
git add README.md ops/_env.sh ops/jobs/probe.jobs ops/jobs/wave1_parity.jobs ops/run_parallel.sh ops/sync.sh ops/vm.env.example ops/vm_create.sh ops/vm_setup.sh
git commit -m "feat: GCP 4xT4 ops scripts, wave-1 job files, README runbook" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

### Task 16: Verify on real HI-Small and the parallel runner

**Files:** none (verification only).

- [ ] **Step 1: Parallel runner with two racing jobs (CPU, Mac)**

```bash
uv run python tests/fixture.py .smoke/fx >/dev/null
cat > .smoke/test.jobs <<'EOF'
gnn --data .smoke/fx/raw/HI-Fixture_Trans.csv --source raw --seed 1 --device cpu --epochs 1 --batch-size 32 --num-neighs 10 10 --runs-dir .smoke/pruns --cache-dir .smoke/pcache --no-mlflow
gnn --data .smoke/fx/raw/HI-Fixture_Trans.csv --source raw --seed 2 --device cpu --epochs 1 --batch-size 32 --num-neighs 10 10 --runs-dir .smoke/pruns --cache-dir .smoke/pcache --no-mlflow
EOF
N_GPUS=2 GRAFIN_EXTRA=cpu ops/run_parallel.sh .smoke/test.jobs; echo "exit=$?"
ls .smoke/pcache .smoke/pruns
echo "gnn --data nope.csv --source raw --device cpu --no-mlflow" > .smoke/bad.jobs
N_GPUS=1 GRAFIN_EXTRA=cpu ops/run_parallel.sh .smoke/bad.jobs; echo "exit=$?"
rm -rf .smoke logs && uv sync
```

Expected: first `exit=0`, exactly one `raw-<sha16>` cache dir and two run dirs (seeds 1 and 2);
second run prints `job on gpu0 FAILED` and `exit=1`. (`uv sync` restores the default environment
after `--extra cpu`.)

- [ ] **Step 2: Real HI-Small-ID smoke (paper settings, 3 batches per loader)**

Run: `make smoke-small`
Expected: finishes in ~5 minutes on an M2 with exit 0; log shows
`epoch 0 loss … val_f1 … test_f1 …`; `runs/` (inside `.smoke/runs`) contains `metrics.json`;
`data.json` shows split `train_days 0-5, val_days [6, 7], test_days 8-17` and counts
`train 3248921, val 965524, test 863900`. Peak memory ≈ 10 GB (batch subgraphs at
8192 × [100, 100]). Then `rm -rf .smoke`.

- [ ] **Step 3: Raw HI-Small prepare sanity**

Run: `uv run grafin-train prepare --data ../grafin-ai-data/raw/HI-Small/HI-Small_Trans.csv --source raw`
Expected: `n_edges 5078345`, `n_nodes 515088`, `n_days 18`, `laundering 5177`, ~15 s.

- [ ] **Step 4: Final gate**

Run: `make check` → ruff clean, mypy `Success: no issues found`, `42 passed`.
No commit needed unless a fix was required (then commit it with a `fix:` message).
