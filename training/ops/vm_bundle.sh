#!/usr/bin/env bash
# For a VM you can only reach through the browser SSH console (no gcloud scp from this laptop).
# Builds ONE small upload: training code + garda-ai-dataset code + a setup script (no data).
# On the VM the setup script downloads IBM HI-Small from Kaggle and re-localizes it; localization
# is deterministic, so the transactions file must hash to the same sha256 as your laptop copy.
#
#   laptop:  ops/vm_bundle.sh            -> garda-bundle.tar.gz in the repo root
#   console: "Upload file" garda-bundle.tar.gz and your kaggle.json, then
#            tar xzf garda-bundle.tar.gz -C ~ && bash ~/garda/vm_bootstrap.sh
source "$(dirname "$0")/_env.sh"
ROOT="$(cd "$REPO_DIR/.." && pwd)"
OUT="$REPO_DIR/garda-bundle.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/garda/garda-ai-training" "$TMP/garda/garda-ai-dataset"
git -C "$REPO_DIR" archive HEAD | tar x -C "$TMP/garda/garda-ai-training"
git -C "$ROOT/garda-ai-dataset" archive HEAD | tar x -C "$TMP/garda/garda-ai-dataset"
if [[ -f "$OPS_DIR/vm.env" ]]; then cp "$OPS_DIR/vm.env" "$TMP/garda/garda-ai-training/ops/vm.env"; fi
python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['outputs']['HI-Small_Trans_sorted.csv'])" \
  "$ROOT/garda-ai-data/HI-Small-ID/MANIFEST.json" >"$TMP/garda/expected_small_sha256"
cp "$OPS_DIR/vm_bootstrap.sh" "$TMP/garda/vm_bootstrap.sh"
tar czf "$OUT" -C "$TMP" garda
ls -lh "$OUT"
