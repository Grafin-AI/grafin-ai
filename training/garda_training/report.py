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
