#!/usr/bin/env bash
# For a VM you can only reach through the browser SSH console (no gcloud scp from this laptop).
# Builds ONE small upload: training code + grafin-ai-dataset code + a setup script (no data).
# On the VM the setup script downloads IBM HI-Small from Kaggle and re-localizes it; localization
# is deterministic, so the transactions file must hash to the same sha256 as your laptop copy.
#
#   laptop:  ops/vm_bundle.sh            -> grafin-bundle.tar.gz in the repo root
#   console: "Upload file" grafin-bundle.tar.gz and your kaggle.json, then
#            tar xzf grafin-bundle.tar.gz -C ~ && bash ~/grafin/vm_bootstrap.sh
source "$(dirname "$0")/_env.sh"
ROOT="$(cd "$REPO_DIR/.." && pwd)"
OUT="$REPO_DIR/grafin-bundle.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/grafin/grafin-ai-training" "$TMP/grafin/grafin-ai-dataset"
git -C "$REPO_DIR" archive HEAD | tar x -C "$TMP/grafin/grafin-ai-training"
git -C "$ROOT/grafin-ai-dataset" archive HEAD | tar x -C "$TMP/grafin/grafin-ai-dataset"
if [[ -f "$OPS_DIR/vm.env" ]]; then cp "$OPS_DIR/vm.env" "$TMP/grafin/grafin-ai-training/ops/vm.env"; fi
python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['outputs']['HI-Small_Trans_sorted.csv'])" \
  "$ROOT/grafin-ai-data/HI-Small-ID/MANIFEST.json" >"$TMP/grafin/expected_small_sha256"
cp "$OPS_DIR/vm_bootstrap.sh" "$TMP/grafin/vm_bootstrap.sh"
tar czf "$OUT" -C "$TMP" grafin
ls -lh "$OUT"
