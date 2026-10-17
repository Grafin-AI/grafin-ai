# garda-ai-training

Training repo for the Garda AI fraud scorer. It is a faithful port of
[IBM/Multi-GNN](https://github.com/IBM/Multi-GNN) (Egressy et al., AAAI 2024) with the bugs found
in our earlier fork fixed. It trains on the Indonesian-localized IBM AML data produced by
`garda-ai-dataset`.

> **Status — Plan A (foundation + paper protocol).** It can reproduce the paper's Multi-PNA+EU
> numbers and compare raw vs localized data. Plan B adds the causal protocol, the scorer heads
> (XGBoost / LightGBM / CatBoost / MLP), ONNX export and the model bundle for `garda-ai-scoring`.

Design: [docs/superpowers/specs/2026-10-17-training-repo-design.md](docs/superpowers/specs/2026-10-17-training-repo-design.md)

## Quickstart (Mac, CPU)

```bash
make install        # uv sync (arm64 Python 3.11 is pinned in .python-version)
make check          # ruff + mypy --strict + pytest
make smoke          # synthetic fixture end to end, ~10 s
make smoke-small    # real HI-Small-ID, 3 batches per loader, ~5 min
```

Datasets are expected next to the repo in `../garda-ai-data` (produced by `garda-ai-dataset`):

| `--source` | file | integrity check |
|---|---|---|
| `raw` | `raw/HI-Small/HI-Small_Trans.csv` | `SHA256SUMS` in the same folder |
| `id` | `HI-Small-ID/HI-Small_Trans_sorted.csv`, `HI-Medium-ID/HI-Medium_Trans_sorted.csv` | `MANIFEST.json` in the same folder |

## Commands

```bash
garda-train prepare --data FILE --source raw|id          # verify + cache (cache/<source>-<sha16>/)
garda-train gnn --data FILE --source raw|id --seed 1 --device cuda [--epochs N] [--batch-size N] [--num-neighs A B]
garda-train gnn --resume RUN_ID                          # continue an interrupted run
garda-train compare                                      # markdown table of runs/ (mean ± std per dataset)
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
3. VM: clone the repo next to an empty `garda-ai-data/`, copy `ops/vm.env`, run `ops/vm_setup.sh`
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

- `garda_training/models/multignn.py` is upstream `models.py` byte for byte (a test checks its sha256).
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
