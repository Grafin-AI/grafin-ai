# grafin-ai-training — Design

**Status:** approved in brainstorming 2026-10-17, awaiting written-spec review
**Sub-project:** 2 of 4 (1 dataset ✅ · **2 training** · 3 Insight Narrator · 4 platform wiring); typology injection is spec #2 of the dataset repo and comes *after* this.
**Repo:** `repositories/grafin-ai-training` (new, local git, no remote). Replaces `workspace/grafin-ai-fraud-scorer-model`, which stays untouched as a historical reference.

## 1. Purpose

Turn the Multi-GNN fork into a correct, reproducible training repo that:

1. proves the port is faithful (F1 parity with the published paper on raw IBM HI-Small),
2. measures what the Indonesian localization cost the model (raw vs HI-Small-ID),
3. trains on HI-Medium-ID, compares a GNN against five scorer heads under a leakage-free *causal* protocol, picks a winner on validation and reports test once,
4. exports a versioned **model bundle** (ONNX + feature spec + daily account-embedding snapshots) that `grafin-ai-scoring` can serve on CPU.

Non-goals are listed in §12.

## 2. Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Repo name | `grafin-ai-training` (matches `grafin-ai-scoring`, `-ingest`, `-dataset`, `-sim`) |
| Code approach | **B** — new uv package; IBM `models.py` vendored **verbatim**; everything around it rebuilt as small tested modules |
| History | Fresh repo (old fork had two "first commit"s). Keep IBM Apache-2.0 `LICENSE` + a `NOTICE` crediting IBM/Multi-GNN. Old checkpoints are not carried over (trained on un-localized data, CUDA-pickled). |
| Compute | Develop/smoke on the Mac (M2, 16 GB, CPU/MPS) with HI-Small; full runs on a **GCP VM with 4× NVIDIA T4** (16 GB each). One run per GPU, up to 4 in parallel. No DDP. |
| Deliverable model | **Both, pick on validation**: paper GNN baseline + scorer heads on its embeddings |
| Serving | **Embedding table + head**: GNN runs offline producing per-account embeddings (daily refresh); scorer does lookup + head on CPU |
| Scorer heads | XGBoost, LightGBM, CatBoost, MLP (paper head architecture), plus a **transaction-features-only LightGBM** baseline. RF / ExtraTrees / HistGBDT are optional, not in the default study. |
| Head export | **ONNX** (scorer depends only on `onnxruntime`) |
| Tracking | **MLflow** file store `./mlruns`, synced to GCS; every run also writes a self-contained run directory |
| Ordering vs typology injection | Build + validate this repo on un-injected data first (clean paper parity), inject typologies (dataset spec #2), then re-run the study with one command |

## 3. Reference facts

**Upstream:** `github.com/IBM/Multi-GNN` at commit `252b025` ("Fixed major bug with reverse MP"). `models.py` sha256 `00ef7142e81d3080114142106867e6ef3002d5a01ff5474e9f75cab957fcefe7`. (The user's fork's `models.py` differs — `7d988dd4…` — because of the removed `--bidirectional_mp` change; we vendor upstream.)

**Paper:** Egressy et al., *Provably Powerful Graph Neural Networks for Directed Multigraphs*, AAAI 2024 (arXiv 2306.11586), Table 2, minority-class F1 %, mean ± std over 5 seeds, temporal 60/20/20 split:

| Model | Small HI | Medium HI |
|---|---|---|
| XGBoost + graph features | 63.23 ± 0.17 | 65.70 ± 0.26 |
| PNA | 56.77 ± 2.41 | 59.71 ± 1.91 |
| Multi-PNA | 64.59 ± 3.60 | 65.67 ± 2.66 |
| **Multi-PNA+EU** | **68.16 ± 2.65** | **66.48 ± 1.63** |

"Multi-" = reverse message passing + port numbering + ego IDs; "+EU" = edge updates. Upstream flags: `--model pna --emlps --reverse_mp --ports --ego`. Upstream PNA hyper-parameters (`model_settings.json`): `lr 6.116e-4, n_hidden 20, n_gnn_layers 2, n_mlp_layers 1, w_ce1 1.0004, w_ce2 7.0776, dropout 0.0834, final_dropout 0.2881`; loader `batch_size 8192`, `num_neighs [100, 100]`.

**Datasets** (from `grafin-ai-dataset`, in `grafin-ai-data/`):

| Dataset | Path | Rows | Days | Note |
|---|---|---|---|---|
| raw HI-Small | `raw/HI-Small/HI-Small_Trans.csv` | 5,078,345 | 18 | original currencies, zero-padded bank strings, **not time-sorted** |
| HI-Small-ID | `HI-Small-ID/HI-Small_Trans_sorted.csv` | 5,078,345 | 18 | IDR, sorted (ts, raw_row), int bank codes, `MANIFEST.json` |
| HI-Medium-ID | `HI-Medium-ID/HI-Medium_Trans_sorted.csv` | 31,898,238 | 28 | as above; ~2.08 M accounts |

Both formats share the same 11 positional columns (the 2nd account column is named `Account` in raw, `To Account` in ID).

**Known data issue — currency feature is constant in HI-*-ID.** The paper's four edge features are `Timestamp, Amount Received, Received Currency, Payment Format`. Localization converted every currency to IDR, so `Received Currency` carries no information there (amounts still differ by original FX rate). Success criterion 2 measures the cost; any fix belongs in `grafin-ai-dataset`, not here.

**Known data issue — HI-Small and HI-Medium have disjoint accounts.** The model is trained on Medium; the platform demo replays Small. This works because node input features are constant (all 1s): embeddings are a function of transaction structure, not identity, so the Medium-trained GNN can embed the Small graph. This also yields an honest unseen-dataset number (criterion 4).

## 4. Repository layout

```
grafin-ai-training/
├── pyproject.toml            uv, hatchling, ruff (E4,E7,E9,F,I), mypy --strict (vendored models excluded)
├── Makefile                  install lint typecheck test check smoke smoke-small + ops targets
├── LICENSE  NOTICE  README.md
├── configs/
│   ├── paper_pna.toml        upstream PNA hyper-parameters + flags (§3)
│   └── study_medium.toml     causal study: heads, Optuna budget, thresholds policy
├── grafin_training/
│   ├── cli.py                `grafin-train` entry point
│   ├── config.py             typed config (TOML → frozen dataclasses), validation → exit 3
│   ├── errors.py             exit-code taxonomy (§10)
│   ├── device.py             cpu|mps|cuda resolution; `--device cuda` without CUDA → exit 5
│   ├── data/
│   │   ├── load.py           Polars reader for `raw` and `id` sources → canonical edge frame
│   │   ├── nodes.py          (bank, account) → contiguous int ids
│   │   ├── split.py          paper day-split (verbatim algorithm) + calibration split
│   │   └── features.py       paper edge features; head transaction features; codebooks; train-only norm stats
│   ├── graph/
│   │   ├── build.py          PyG Data/HeteroData, ports, time-deltas, reverse MP (from upstream data_util.py)
│   │   └── loaders.py        LinkNeighborLoader factories, AddEgoIds (from upstream train_util.py)
│   ├── models/
│   │   ├── multignn.py       upstream models.py VERBATIM (sha256-locked)
│   │   └── node_states.py    reads final-layer node states from a vendored model without editing it
│   ├── train/gnn.py          training loop: AMP, resume, best-val checkpoint, NaN guard
│   ├── embed.py              embedding snapshots frozen at `as_of`
│   ├── heads/
│   │   ├── registry.py       head name → builder (xgboost, lightgbm, catboost, mlp, txonly; optional rf, et, hgb)
│   │   ├── tune.py           Optuna, equal budget per head
│   │   └── onnx_export.py    native → ONNX + parity check
│   ├── evaluate.py           paper & causal protocols, threshold policy, metrics, test-once guard
│   ├── bundle.py             build / verify model bundle (§8)
│   ├── tracking.py           run directory + MLflow logging
│   └── report.py             `compare` table across runs (markdown)
├── ops/
│   ├── vm_create.sh          documented `gcloud compute instances create` (4×T4, ≥ 52 GB RAM, e.g. n1-highmem-8)
│   ├── vm_setup.sh           driver check, uv sync --extra cuda, data pull from GCS
│   ├── run_parallel.sh       one job per GPU via CUDA_VISIBLE_DEVICES, per-GPU logs, non-zero if any job fails
│   └── sync.sh               data ↓ / mlruns + bundles ↑ (gsutil rsync)
├── tests/                    CPU-only, synthetic fixture graph (§11)
└── docs/superpowers/{specs,plans}/
```

Python 3.11. Torch + PyG pinned to a combination that has CPU/MPS wheels on macOS arm64 **and** CUDA 12.x wheels on Linux (the CUDA build is a uv extra/index, chosen by `make install CUDA=1`). The neighbor sampler backend (`pyg-lib` or `torch-sparse`) must be available on both; the plan pins and verifies this in Task 1 before anything else.

## 5. Data flow

```
CSV (raw | id) ──prepare──► cache/<dataset-hash>/  (edges.parquet, nodes.parquet, split.json, codebooks.json)
                               │
                 gnn (paper | causal mode) ──► runs/<run-id>/checkpoints/best.pt
                               │
          embed --refresh daily ──► runs/<run-id>/embeddings/<as_of>.parquet
                               │
                 heads (tune + fit on calibration days) ──► runs/<run-id>/heads/<name>/
                               │
                 evaluate (validation; select winner; test once) ──► runs/<run-id>/metrics.json
                               │
                 export ──► bundles/<version>/  ──sync──► gs://<bucket>/bundles/<version>/
```

- `prepare` is cached by the input file's sha256 (for ID data, cross-checked against `MANIFEST.json`; mismatch → exit 2).
- **Node ids**: key = (from_bank, from_account) / (to_bank, to_account). For raw data the bank strings are compared after int normalization (the dataset repo verified 0 merges, so node count equals upstream's string-concatenation keys; a test asserts the node count on raw HI-Small equals upstream's).
- **Ordering**: rows are sorted by (timestamp, input row index) — stable, so raw (unsorted) and ID (pre-sorted) agree.
- **Categorical codes for paper features** (currency, payment format) are assigned in first-appearance order in the input file, as upstream does, then z-normalized as upstream does.
- **Timestamps** are parsed as naive UTC (upstream used local time; the only difference is DST-free seconds, irrelevant after `ts − min(ts)`).

## 6. Features

**Paper edge features (GNN only, verbatim semantics):** `Timestamp` (seconds since data start), `Amount Received`, `Received Currency` code, `Payment Format` code; plus ports / time-deltas / ego IDs per flags. **Fix vs upstream:** z-normalization statistics are computed on the **training rows only** and applied to all splits (upstream normalized each split with its own statistics).

**Head transaction features (all heads, and the transaction-only baseline):**

| Feature | Definition |
|---|---|
| `log_amount` | `ln(1 + Amount Received in IDR)` (raw source: in original currency) |
| `channel` | Payment Format code from a frozen codebook; unseen value → reserved code `0` |
| `hour`, `dow` | hour of day, day of week of the transaction timestamp |
| `same_bank` | from_bank == to_bank |
| `self_transfer` | (from_bank, from_account) == (to_bank, to_account) |

**Embedding features (all heads except transaction-only):** `emb_src[0..D-1]`, `emb_dst[0..D-1]`, `is_new_src`, `is_new_dst`. D = GNN `n_hidden` (20 with the paper config). Accounts absent from the snapshot get a zero vector and `is_new_* = 1`.

**Node state definition.** The embedding is the **final GNN layer's node state, before the edge-gather ReLU** (in upstream PNA: `x` after the last conv/BatchNorm/residual, before `x[edge_index.T]...relu()`). For reverse-MP (HeteroData) it is `x['node']`. `node_states.py` reproduces the vendored `forward()` up to that point; a test asserts that `node_states` + the vendored head reproduces `model(...)` exactly on the fixture.

## 7. Training and evaluation protocols

### 7.1 Splits

- **Paper split:** the upstream day-based 60/20/20 algorithm (choose day boundaries i < j minimizing the max relative error of the split proportions by transaction count), reproduced verbatim.
- **Calibration split (causal mode only):** within the training days, the last day boundary whose cumulative count is closest to 80 % of training transactions splits them into **GNN-fit days** (first ~80 %) and **calibration days** (last ~20 %). If it would leave zero calibration days, exit 3.

### 7.2 Two protocols

| | Paper protocol | Causal protocol |
|---|---|---|
| What a scored edge may see | upstream: train graph / train+val graph / full graph (later same-split edges included) | edges strictly **before the start of its day**, plus that day's batch being scored |
| GNN training rows | all training days | GNN-fit days |
| GNN early stopping | validation F1 | calibration-days F1 (paper protocol — cheap, only picks the epoch) |
| Used for | **only** parity (criterion 1) and the currency check (criterion 2) | candidate selection, thresholds, final test number |

**Causal scoring per candidate:**
- **GNN (reported, not shippable in the chosen serving design):** for each evaluated day *d*, run the GNN on graph(edges < d) ∪ {day-*d* edges in the batch} and take its own prediction. Same-day edges inside the batch are visible to it — this is what a GNN-in-scorer would see; documented, not hidden.
- **Embedding heads:** snapshot `as_of = start of day d` built from edges < d; lookup + head. No same-day information.
- **Transaction-only baseline:** transaction features only.

### 7.3 Heads

- Fitted on **calibration days**, each row's embeddings taken from the snapshot at the start of that row's day (so the GNN never trained on the rows the head learns from, and features match serving).
- **Class imbalance:** every head uses the same positive weight = negatives / positives on the calibration rows (XGBoost `scale_pos_weight`, LightGBM `scale_pos_weight`, CatBoost `class_weights`, MLP weighted CE).
- **Tuning:** Optuna TPE, **25 trials per head** (configurable), objective = average precision. Trials train on calibration days except the last one and score on the last calibration day. Validation rows are never read during tuning (asserted). Final head is refit on all calibration days with the best params; boosted heads use early stopping on the last calibration day.
- **MLP head** = upstream head architecture (`Linear(in,50)–ReLU–Dropout–Linear(50,25)–ReLU–Dropout–Linear(25,2)`) trained from scratch on the head feature vector (it cannot reuse the GNN's own head: that head expects edge-updated edge states).
- **Hardware:** XGBoost and CatBoost on GPU when available; LightGBM and MLP on CPU/GPU as configured.

### 7.4 Thresholds, selection, test

- Per candidate, on validation: **blocked** = threshold maximizing F1; **flagged** = largest threshold with recall ≥ 0.90 (configurable); if flagged > blocked, flagged = blocked.
- **Winner** = shippable candidate (embedding heads + transaction-only baseline) with the highest **mean validation F1 across seeds**. The plain GNN is reported alongside.
- **Test** is evaluated **once per causal study** after selection (paper-protocol runs keep the upstream convention of reporting test at the best-validation epoch — they select nothing that ships) (guard file `runs/<study>/TEST_EVALUATED`; a second attempt → exit 3 unless `--force-retest`, which is logged). All candidates' test numbers are reported; the winner's validation and test F1 are shown side by side.
- **Metrics:** minority-class F1, precision, recall at `blocked`; PR-AUC; ROC-AUC; new-account rate on validation/test; per-channel F1 (informational).

### 7.5 Embedding refresh

`--refresh daily` (default): one snapshot per evaluated day (and per calibration day for head fitting); `--refresh once`: a single snapshot at the split boundary. Each snapshot = one full-graph inference pass (expected ~5–15 min on a T4 for HI-Medium); snapshot time and peak GPU memory are logged.

### 7.6 Study on 4×T4

- **Wave 1 — parity (HI-Small, paper protocol):** raw × seeds {1,2}, HI-Small-ID × seeds {1,2}. One run per GPU.
- **Wave 2 — causal study (HI-Medium-ID):** causal GNN + heads × seeds {1,2}; paper-protocol HI-Medium-ID × seed 1 (reference vs 66.48); 1 GPU spare.
- Then **transfer:** embed HI-Small-ID with the winning Medium GNN (daily refresh) and causally evaluate the shipped head on it.

## 8. Model bundle (contract with `grafin-ai-scoring`)

```
bundles/<version>/                 version = <yyyy-mm-dd>-<dataset>-<head>-<git7>
├── manifest.json
├── model.onnx                     input "features" float32 [N, F]  →  output "score" float32 [N] (P(laundering))
├── feature_spec.json
└── embeddings/<as_of>.parquet     columns: bank_code:int64, account:str, e0..e{D-1}:float32
```

**manifest.json**: `bundle_version`, `created_at`, `git_sha`, `dataset` + its `MANIFEST.json` sha256, `head`, `embedding_dim`, `snapshots` (sorted as_of list), `thresholds` {`flagged`, `blocked`}, `metrics` (validation + test for every candidate incl. GNN and transaction-only), `onnx_opset`, `files` {path: sha256}.

**feature_spec.json**: ordered feature list (§6) with, per feature, its source request field(s), transform, codebook (channel), and normalization stats (used only when the MLP head wins). The scorer derives features from this file, never hard-coded.

**Snapshot selection rule (scorer):** use the latest snapshot whose `as_of ≤ start of the transaction's day` (dataset time). Production = newest snapshot; demo replay reproduces the daily refresh without future leakage.

**Commands:**
- `grafin-train export --study <id>` builds the bundle from the winning head of the best-validation seed.
- `grafin-train embed --bundle <version> --data <dataset> --refresh daily` appends snapshots for another dataset (used for the HI-Small demo; also the "Embedding Refresh" loop from the pitch).
- `--dtype float16` stores snapshots in half precision; the export check reports the F1 delta.

**Export self-checks (any failure → exit 4):** ONNX vs native max |Δscore| ≤ 1e-5 on 10 000 validation rows; all embedding values finite; every file hash matches the manifest; end-to-end replay — raw validation transactions → feature_spec → snapshot lookup → ONNX — reproduces the evaluator's validation scores within 1e-5.

**Requirements recorded for sub-project 4 (not built here):** scorer request must add `from_bank`, `to_bank`; `amount` in IDR; `event_time` must be dataset time (snapshot selection, hour/dow); `fraud_score` = ONNX output, `status` from thresholds; `typology` stays `null` until the explainer sub-project.

## 9. Tracking and ops

- Every run writes `runs/<run-id>/`: `config.toml` (resolved), `env.json` (git sha, dirty flag, torch/PyG/CUDA versions, device), `data.json` (dataset hash, split days, counts), `metrics.json`, `checkpoints/`, `embeddings/`, `heads/`, `log.txt`. The run directory alone is enough to reproduce/inspect a run.
- MLflow (file store `./mlruns`): params, per-epoch metrics, final metrics, artifacts by reference. `ops/sync.sh` rsyncs `mlruns/`, `runs/`, `bundles/` to `gs://$GRAFIN_GCS_BUCKET/` and data down from it. `mlflow ui` locally after sync.
- `grafin-train compare --study <id>` prints a markdown table of all candidates × seeds (validation, test, thresholds).
- `ops/vm_create.sh` documents the VM (4×T4, ≥ 52 GB RAM, ≥ 200 GB disk); no terraform.

## 10. Error handling

| Exit | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected error |
| 2 | dataset missing, or hash ≠ `MANIFEST.json` |
| 3 | config error (unknown head, bad fractions, `--at` outside data range, empty calibration split, test re-evaluation without `--force-retest`) |
| 4 | export self-check failed |
| 5 | `--device cuda` requested but CUDA unavailable (never silently fall back to CPU on the VM) |

GNN training aborts on a NaN loss, keeping the last good checkpoint. Resume (`--resume`) restores model, optimizer, scaler, epoch, RNG states and best-val bookkeeping. Checkpoints store CPU tensors (`state_dict` moved to CPU) and are loaded with `map_location`.

## 11. Testing

All tests run on CPU in seconds using a synthetic fixture (~200 edges, 6 days, planted fan-in and cycle laundering) written in both `raw` and `id` formats.

- **Leakage (highest priority):** changing any edge with timestamp ≥ T leaves the snapshot at T bit-identical; norm stats ignore val/test rows; tuning never reads validation rows; the test-once guard works.
- **Fidelity:** vendored `models/multignn.py` sha256 equals upstream; `node_states` + vendored head == `model.forward`; split algorithm reproduces the upstream implementation on the fixture and on recorded HI-Small day counts; node count on the fixture equals the upstream string-concatenation key count; raw and id sources yield identical graphs on the fixture.
- **Device/resume:** checkpoint saved then loaded on CPU; interrupted-and-resumed training yields the same losses as an uninterrupted run (same seed, CPU).
- **Heads/export:** each head's ONNX matches native within 1e-5; bundle round-trip reproduces evaluator scores; manifest hashes verify; unknown channel maps to the reserved code.
- **CLI/errors:** each exit code has a test.
- **Smoke:** `make smoke` runs prepare → gnn (2 epochs) → embed → heads (2 trials) → evaluate → export on the fixture (in CI). `make smoke-small` runs the same on HI-Small-ID locally (CPU/MPS, reduced epochs/trials) before any GPU spend.
- Quality gate: `ruff`, `mypy --strict` (vendored model file excluded), `pytest` all clean.

## 12. Out of scope

Explainer / fraud type / risk factors (next spec); scorer and backend changes (sub-project 4); typology injection (dataset spec #2); terraform for the VM; multi-GPU training of a single model (DDP); federated learning and the pitch's `vector128`; the paper's "XGBoost + graph features" baseline (needs IBM Snap ML's graph-feature preprocessor) — cited for reference only.

## 13. Success criteria

1. **Parity:** paper-protocol Multi-PNA+EU on **raw HI-Small**, mean test F1 over seeds {1,2} within the paper's 68.16 ± 2×2.65, i.e. **[62.86, 73.46]**.
2. **Currency check:** raw vs HI-Small-ID paper-protocol F1 difference measured and written to the README results table, whatever its size.
3. **Causal study on HI-Medium-ID** complete: all shippable candidates + plain GNN evaluated, winner chosen on validation, test reported once.
4. **Bundle** exported for HI-Medium-ID with HI-Small-ID demo snapshots; all export self-checks pass; transfer F1 on HI-Small-ID reported.
5. ruff + mypy --strict + tests clean; README with Mac quickstart, VM runbook and results table.

## 14. Risks

| Risk | Mitigation |
|---|---|
| Torch/PyG/sampler wheels differ between macOS arm64 and CUDA Linux | Plan Task 1 pins and verifies both before writing features; CPU path is what CI uses |
| T4 16 GB OOM at `batch 8192 × [100,100]` on Medium | configurable batch/neighbors, AMP, peak-memory logging; parity runs use upstream values on Small |
| Daily-refresh cost on Medium | `--refresh once` fallback; snapshot timing logged |
| Parity misses the band | compare against the upstream code run unmodified on the same machine (scratchpad clone) to separate port bugs from seed variance before changing anything |
| Constant currency feature lowers F1 on ID data | measured by criterion 2; fix lives in `grafin-ai-dataset` |
| Embedding snapshot volume (Small: 518 k × 20 × 4 B ≈ 41 MB/day) | small at D = 20; `float16` option |

## 15. Implementation notes (added 2026-10-17 during planning; verified by probes)

- **Two plans.** Plan A = foundation + paper protocol (enough for Wave 1 parity on the VM). Plan B = causal protocol, embedding snapshots, heads, ONNX, bundle, transfer. Plan A is self-contained and shippable on its own.
- **Pinned stack (verified to lock for macOS arm64 + Linux CPU + Linux CUDA 12.4):** Python 3.11, `torch==2.5.1`, `torch_geometric==2.6.1`, `pyg-lib==0.4.0` (direct wheel URLs per platform: `+pt25` macOS universal2, `+pt25cpu` / `+pt25cu124` Linux), `polars==2.0.0`, numpy 2.x. Linux needs `--extra cpu` (CI) or `--extra cu124` (VM). uv must use an **arm64** interpreter on the Mac (an x86_64 3.11 is also installed for the datatable/Rosetta formatter) — `.python-version` pins `cpython-3.11-macos-aarch64-none`.
- **MLflow:** the file store is in maintenance mode in MLflow 3 (raises unless `MLFLOW_ALLOW_FILE_STORE=true`), so tracking uses `sqlite:///mlruns/mlflow.db` with artifacts in `mlruns/artifacts`; `mlflow-skinny` + explicit `sqlalchemy`/`alembic`. MLflow failures never fail a run (run directory is the source of truth). UI: `uvx mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db`.
- **Run directory writes `config.json`** (not TOML) — no extra dependency.
- **Upstream quirk reproduced on purpose:** in `create_hetero_obj` the `rev_to` port swap is done in place on a tensor shared with the forward edge type, so **both** edge types get the last two columns swapped (probe-confirmed). Kept for parity, documented in code.
- **Upstream detail reproduced:** node features are a constant 1 that `z_norm` turns into **all zeros**; with ego IDs the model input is `[0, ego]`.
- **Seed edges not sampled into their own batch are skipped** by upstream's training/evaluation (except for its Small_J/Q datasets). Paper protocol reproduces this and logs **seed coverage**; the causal protocol (Plan B) scores every seed edge.
- **Best epoch** = highest validation F1 over all epochs (upstream ignored epoch 0 for best-model bookkeeping; negligible).
- **Ports / time-deltas** are computed once on the full sorted edge list with a vectorised implementation proven equal to upstream's loops on the fixture. Both are causal (depend only on earlier edges), so values match upstream's per-split computation.
- **Node state extraction** (Plan B) uses forward hooks on `node_emb[.node]` and `batch_norms.{i}[.node]` and recomputes `x_i = (x_{i-1} + relu(bn_i)) / 2` — probe-verified to reproduce exactly what the vendored head consumes (homo and `to_hetero`).
- **Neighbour sampling is reproducible** from the torch RNG (pyg-lib sampler), so resume restores RNG states and continues identically.
- **HI-Small paper split** (raw and ID identical): daily counts `[1114921, 754449, 207382, 207430, 482650, 482089, 482751, 482773, 654467, 208325, 396, 281, 184, 121, 46, 46, 23, 11]` → train days 0–5, val 6–7, test 8–17.
- **VM RAM:** 52 GB is enough for Wave 1 (HI-Small). Four parallel **HI-Medium** jobs need ≈ 15 GB each → use **n1-highmem-16 (104 GB)** for Wave 2, or run Medium jobs two at a time.
