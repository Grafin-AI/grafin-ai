# Experiment tracking (MLflow)

Run directories under `runs/<run-id>/` stay the source of truth. MLflow mirrors them into a
local SQLite store (`mlruns/mlflow.db`, artifacts in `mlruns/artifacts/`, both git-ignored).
MLflow 3.x refuses the old `file:./mlruns` store, so SQLite is the default.

```bash
uv run garda-train mlflow-log --run small-id-s2            # default: $MLFLOW_TRACKING_URI or sqlite:///mlruns/mlflow.db
uv run garda-train mlflow-log --run small-id-s2 --tracking-uri sqlite:////abs/path/mlflow.db
uvx mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db   # http://127.0.0.1:5000
```

Experiment `grafin-ai-multignn`, MLflow run name = run id. Re-logging a run replaces the
earlier MLflow run of the same name, so metric histories are never duplicated.

What gets logged:

- **params**: `config.json` flattened (`gnn.train.lr`, `gnn.model.n_hidden`, ...), split counts and
  laundering counts from `data.json`, graph size, `threshold.*`
- **per-epoch metrics** (step = epoch, from `metrics.json` history): `loss`, `train_f1`,
  `val_f1`, `test_f1`, `val_coverage`, `test_coverage`, `seconds`
- **final metrics**: `best_epoch`, `best_val_f1`, `test_f1_at_best`, peak GPU/host memory;
  `final_{val,test}_{f1,pr_auc,roc_auc,precision,recall,recall_at_flagged,n,positives}` and
  status counts from `scores/score_metrics.json`; `threshold_flagged`/`threshold_blocked`;
  `typology_*` counts and `export_status_*` from `scores/export_meta.json`
- **tags**: `dataset`, `model` (Multi-GNN PNA), `run_id`, `git_commit` (training SHA, or HEAD
  when the run recorded none), `logged_from_commit`, `stop_reason`, `env.*`
- **artifacts**: `config.json`, `data.json`, `env.json`, `metrics.json`, `scores/score_metrics.json`,
  `scores/thresholds.json`, `scores/export_meta.json`, `typology_counts.json`. Not logged:
  `scores.csv`, `scores.parquet`, checkpoints.

## Logged runs

| run | dataset | best epoch | val F1 | test F1 | test PR-AUC | test ROC-AUC | test precision | test recall | recall @ flagged | flagged thr | blocked thr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| small-id-s2 (deployed) | HI-Small_Trans_sorted (id) | 11 | 0.6047 | 0.6717 | 0.6218 | 0.9838 | 0.7508 | 0.6077 | 0.8206 | 0.1225 | 0.5869 |

20 epochs of history (stopped on patience); export typologies: Anomali Jaringan (GNN) 23244,
Pengumpulan Dana (Fan-in) 1420, Penyebaran Dana (Fan-out) 570, Siklus Dana (Cycle) 483,
Velositas Tinggi 114, Penampung-Penyebar (Gather-Scatter) 10. `small-raw-s1` is not in this
checkout's `runs/`, so it is not logged; `garda-train mlflow-log --run small-raw-s1` adds it.

To share the store, upload the whole `mlruns/` directory (about 1 MB), for example
`gcloud storage cp -r mlruns gs://<bucket>/mlruns`.
