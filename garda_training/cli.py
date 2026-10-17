"""`garda-train` command line: prepare | gnn | compare."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from garda_training.config import load_gnn_config, parse_gnn_config
from garda_training.data.load import as_source
from garda_training.data.prepare import prepare_dataset
from garda_training.device import DEVICE_CHOICES, resolve_device
from garda_training.errors import ConfigError, DatasetError, GardaTrainError
from garda_training.report import collect_runs, render_markdown
from garda_training.tracking import (
    DEFAULT_MLFLOW_URI,
    RunDir,
    Tracker,
    environment_info,
    make_run_id,
)
from garda_training.train.gnn import set_seed, train_gnn
from garda_training.train.paper import paper_inputs

log = logging.getLogger("garda_training")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="garda-train")
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
    gnn.add_argument("--patience", type=int, help="early stopping (epochs); 0 = off")
    gnn.add_argument("--max-hours", type=float, help="wall-clock budget for this run; 0 = off")
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
        if args.patience is not None:
            overrides["train.patience"] = args.patience
        if args.max_hours is not None:
            overrides["train.max_hours"] = args.max_hours
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
    except GardaTrainError as exc:
        log.error("%s", exc)
        return exc.exit_code


def run() -> None:
    sys.exit(main())
