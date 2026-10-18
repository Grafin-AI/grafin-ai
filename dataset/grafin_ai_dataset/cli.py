"""`grafin-dataset fetch|localize|validate|all --dataset small|medium`."""

import argparse
import os
import sys
from pathlib import Path

from grafin_ai_dataset.errors import DatasetError, ValidationFailed
from grafin_ai_dataset.fetch import run_fetch
from grafin_ai_dataset.localize import run_localize
from grafin_ai_dataset.mappings import Mappings, load_mappings
from grafin_ai_dataset.paths import SIZES, DatasetPaths, dataset_paths
from grafin_ai_dataset.validate import validate_dataset

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT.parent / "grafin-ai-data"
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
        prog="grafin-dataset", description="Localize the IBM AML HI datasets for Indonesia."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--dataset", choices=sorted(SIZES), required=True)
        cmd.add_argument(
            "--data-root",
            type=Path,
            default=Path(os.environ.get("GRAFIN_DATA_ROOT", str(DEFAULT_DATA_ROOT))),
        )
        if name in ("fetch", "all"):
            cmd.add_argument(
                "--kaggle-json",
                type=Path,
                default=Path(os.environ.get("GRAFIN_KAGGLE_JSON", str(DEFAULT_KAGGLE_JSON))),
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
