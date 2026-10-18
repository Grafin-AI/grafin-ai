#!/usr/bin/env bash
# Laptop -> VM without GCS: copy the committed code (git archive of HEAD) and the HI-Small data
# into $GRAFIN_VM_DIR on the VM (owner-only: umask 077, chmod 700 on the folder and on $HOME).
#   usage: ops/vm_push.sh [code|data|all]   (default: all)
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCP_PROJECT GRAFIN_GCP_ZONE GRAFIN_VM_NAME GRAFIN_VM_DIR
WHAT="${1:-all}"
D="$GRAFIN_VM_DIR"
DATA_DIR="$(cd "$REPO_DIR/.." && pwd)/grafin-ai-data"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
VM=(--project "$GRAFIN_GCP_PROJECT" --zone "$GRAFIN_GCP_ZONE" ${GCLOUD_FLAGS[@]+"${GCLOUD_FLAGS[@]}"})
remote() { gcloud compute ssh "$GRAFIN_VM_NAME" "${VM[@]}" --command "umask 077; $1"; }
remote "chmod 700 \"\$HOME\" && mkdir -p '$D/grafin-ai-training' '$D/grafin-ai-data/raw' && chmod -R go-rwx '$D'"
if [[ "$WHAT" == code || "$WHAT" == all ]]; then
  git -C "$REPO_DIR" archive --format=tar.gz -o "$TMP/code.tar.gz" HEAD
  cp "$OPS_DIR/vm.env" "$TMP/vm.env"
  gcloud compute scp "${VM[@]}" "$TMP/code.tar.gz" "$TMP/vm.env" "$GRAFIN_VM_NAME:$D/"
  remote "cd '$D/grafin-ai-training' && tar xzf ../code.tar.gz && mv ../vm.env ops/vm.env && rm ../code.tar.gz && chmod +x ops/*.sh && chmod -R go-rwx '$D'"
fi
if [[ "$WHAT" == data || "$WHAT" == all ]]; then
  gcloud compute scp --recurse "${VM[@]}" "$DATA_DIR/HI-Small-ID" "$GRAFIN_VM_NAME:$D/grafin-ai-data/"
  gcloud compute scp --recurse "${VM[@]}" "$DATA_DIR/raw/HI-Small" "$GRAFIN_VM_NAME:$D/grafin-ai-data/raw/"
  remote "chmod -R go-rwx '$D'"
fi
echo "pushed ($WHAT) to $D. On the VM: cd '$D/grafin-ai-training' && ops/vm_setup.sh"
