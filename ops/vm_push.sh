#!/usr/bin/env bash
# Laptop -> VM without GCS: copy the committed code (git archive of HEAD) and the HI-Small data.
# Lands in ~/garda/garda-ai-training and ~/garda/garda-ai-data on the VM.
#   usage: ops/vm_push.sh [code|data|all]   (default: all)
source "$(dirname "$0")/_env.sh"
require GARDA_GCP_PROJECT GARDA_GCP_ZONE GARDA_VM_NAME
WHAT="${1:-all}"
DATA_DIR="$(cd "$REPO_DIR/.." && pwd)/garda-ai-data"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VM=(--project "$GARDA_GCP_PROJECT" --zone "$GARDA_GCP_ZONE" ${GCLOUD_FLAGS[@]+"${GCLOUD_FLAGS[@]}"})
gcloud compute ssh "$GARDA_VM_NAME" "${VM[@]}" --command "mkdir -p ~/garda/garda-ai-training ~/garda/garda-ai-data/raw"
if [[ "$WHAT" == code || "$WHAT" == all ]]; then
  git -C "$REPO_DIR" archive --format=tar.gz -o "$TMP/code.tar.gz" HEAD
  cp "$OPS_DIR/vm.env" "$TMP/vm.env"
  gcloud compute scp "${VM[@]}" "$TMP/code.tar.gz" "$TMP/vm.env" "$GARDA_VM_NAME":~/garda/
  gcloud compute ssh "$GARDA_VM_NAME" "${VM[@]}" --command \
    "cd ~/garda/garda-ai-training && tar xzf ../code.tar.gz && mv ../vm.env ops/vm.env && chmod +x ops/*.sh"
fi
if [[ "$WHAT" == data || "$WHAT" == all ]]; then
  gcloud compute scp --recurse "${VM[@]}" "$DATA_DIR/HI-Small-ID" "$GARDA_VM_NAME":~/garda/garda-ai-data/
  gcloud compute scp --recurse "${VM[@]}" "$DATA_DIR/raw/HI-Small" "$GARDA_VM_NAME":~/garda/garda-ai-data/raw/
fi
echo "pushed ($WHAT). On the VM: cd ~/garda/garda-ai-training && ops/vm_setup.sh"
