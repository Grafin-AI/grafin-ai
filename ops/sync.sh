#!/usr/bin/env bash
# Data and results <-> gs://$GARDA_GCS_BUCKET. Data lives in ../garda-ai-data next to the repo.
#   push-data     laptop -> bucket: raw/HI-Small, HI-Small-ID, HI-Medium-ID
#   pull-data     bucket -> VM
#   push-results  runs/ mlruns/ bundles/ -> bucket
#   pull-results  bucket -> laptop
source "$(dirname "$0")/_env.sh"
require GARDA_GCS_BUCKET
DATA_DIR="$(cd "$REPO_DIR/.." && pwd)/garda-ai-data"
BUCKET="gs://$GARDA_GCS_BUCKET"
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
