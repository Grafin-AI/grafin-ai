"""Export a run's scores as the CSV the platform's scoring service reads (stdlib csv, no
pyarrow): `transaction_id,fraud_score,prob,status,typology`.

`typology` is empty for approved rows; for flagged/blocked rows it names the network pattern
around the transaction (train/typology.py: graph structure only, never the labels).

`fraud_score` is a monotone piecewise-linear rescale of `prob` that puts the model's thresholds
on the dashboard's fixed colour bands: [0, flagged) -> [0, 0.4), [flagged, blocked) ->
[0.4, 0.7), [blocked, 1] -> [0.7, 1]. Bands follow the statuses, so colour and status agree."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import polars as pl

from grafin_training.data.prepare import PreparedData
from grafin_training.errors import ConfigError, ExportCheckError
from grafin_training.tracking import RunDir
from grafin_training.train.score import APPROVED, BLOCKED, FLAGGED, Thresholds, statuses
from grafin_training.train.typology import TYPOLOGIES, typologies

SPLITS = ("val", "test")
CSV_COLUMNS = ["transaction_id", "fraud_score", "prob", "status", "typology"]
FLAG_SCORE, BLOCK_SCORE = 0.4, 0.7
# Rounded scores stay inside their band (e.g. 0.69999 must not print as 0.7000).
_BAND_MAX = {APPROVED: 0.3999, FLAGGED: 0.6999, BLOCKED: 1.0}


def _frac(num: npt.NDArray[np.float64], den: float) -> npt.NDArray[np.float64]:
    """num / den clipped to [0, 1]; 0 when the band is empty (den <= 0)."""
    if den <= 0:
        return np.zeros_like(num)
    return np.clip(num / den, 0.0, 1.0)


def rescale(prob: npt.NDArray[Any], th: Thresholds) -> npt.NDArray[np.float64]:
    """fraud_score in [0, 1], 4 decimals, monotone in prob, band given by statuses(prob, th)."""
    status = statuses(prob, th)
    p = np.asarray(prob, dtype=np.float64)
    lo, hi = th.flagged, th.blocked
    score = np.empty_like(p)
    m = status == APPROVED
    score[m] = FLAG_SCORE * _frac(p[m], lo)
    m = status == FLAGGED
    score[m] = FLAG_SCORE + (BLOCK_SCORE - FLAG_SCORE) * _frac(p[m] - lo, hi - lo)
    m = status == BLOCKED
    if hi >= 1.0:
        score[m] = 1.0
    else:
        score[m] = BLOCK_SCORE + (1.0 - BLOCK_SCORE) * _frac(p[m] - hi, 1.0 - hi)
    score = np.clip(np.round(score, 4), 0.0, 1.0)
    for name, cap in _BAND_MAX.items():
        m = status == name
        score[m] = np.minimum(score[m], cap)
    return score


def breakpoints(th: Thresholds) -> list[dict[str, float]]:
    return [
        {"prob": 0.0, "fraud_score": 0.0},
        {"prob": th.flagged, "fraud_score": FLAG_SCORE},
        {"prob": th.blocked, "fraud_score": BLOCK_SCORE},
        {"prob": 1.0, "fraud_score": 1.0},
    ]


def row_typologies(
    prepared: PreparedData, transaction_id: npt.NDArray[np.int64], status: npt.NDArray[np.str_]
) -> npt.NDArray[np.str_]:
    """Typology per row ("" when approved); transaction_id is the 1-based input-file row."""
    edge_of_row = np.empty(prepared.row.shape[0], dtype=np.int64)
    edge_of_row[prepared.row] = np.arange(prepared.row.shape[0], dtype=np.int64)
    out = np.full(transaction_id.shape[0], "", dtype=object)
    hit = np.flatnonzero(status != APPROVED)
    edges = edge_of_row[transaction_id[hit] - 1]
    out[hit] = typologies(prepared.src, prepared.dst, prepared.ts, edges)
    return out.astype(np.str_)


def export_scores(run: RunDir, splits: list[str], prepared: PreparedData) -> dict[str, Any]:
    """Write scores/scores.csv and scores/export_meta.json; returns the meta."""
    bad = sorted(set(splits) - set(SPLITS))
    if bad or not splits:
        raise ConfigError(f"--splits must be a subset of {list(SPLITS)}, got {splits}")
    out = run.path / "scores"
    parquet = out / "scores.parquet"
    if not parquet.is_file():
        raise ConfigError(f"no scores at {parquet}; run `grafin-train score` first")
    raw = run.read_json("scores/thresholds.json")
    th = Thresholds(float(raw["blocked"]), float(raw["flagged"]), float(raw["flag_recall_target"]))

    frame = (
        pl.read_parquet(parquet, columns=["transaction_id", "split", "prob", "status"])
        .filter(pl.col("split").is_in(splits))
        .sort("transaction_id")
    )
    prob = frame["prob"].to_numpy()
    status = frame["status"].to_numpy().astype(np.str_)
    derived = statuses(prob, th)
    if not np.array_equal(derived, status):
        n = int((derived != status).sum())
        raise ExportCheckError(f"{n} statuses differ from thresholds.json; re-run score")
    score = rescale(prob, th)
    typology = row_typologies(prepared, frame["transaction_id"].to_numpy(), status)
    csv = pl.DataFrame(
        {
            "transaction_id": frame["transaction_id"],
            "fraud_score": np.char.mod("%.4f", score),
            "prob": np.char.mod("%.6f", prob.astype(np.float64)),
            "status": status,
            "typology": typology,
        }
    )
    tmp = out / ".scores.csv.tmp"
    csv.write_csv(tmp)
    tmp.replace(out / "scores.csv")

    meta = {
        "run_id": run.path.name,
        "splits": [s for s in SPLITS if s in splits],
        "n_rows": csv.height,
        "status_counts": {s: int((status == s).sum()) for s in (APPROVED, FLAGGED, BLOCKED)},
        "thresholds": raw,
        "rescale_breakpoints": breakpoints(th),
        "typology_counts": {t: int((typology == t).sum()) for t in TYPOLOGIES},
        "dataset_sha256": run.read_json("config.json")["data"]["sha256"],
        "columns": CSV_COLUMNS,
    }
    RunDir(out).write_json("export_meta.json", meta)
    return meta
