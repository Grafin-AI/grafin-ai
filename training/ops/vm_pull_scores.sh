#!/usr/bin/env bash
# VM -> laptop: copy a run's results back after `grafin-train score --run RUN_ID` on the VM.
#   usage: ops/vm_pull_scores.sh RUN_ID
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCP_PROJECT GRAFIN_GCP_ZONE GRAFIN_VM_NAME GRAFIN_VM_DIR
RUN_ID="${1:?usage: $0 RUN_ID}"
VM=(--project "$GRAFIN_GCP_PROJECT" --zone "$GRAFIN_GCP_ZONE" ${GCLOUD_FLAGS[@]+"${GCLOUD_FLAGS[@]}"})
mkdir -p "$REPO_DIR/runs/$RUN_ID"
for f in config.json data.json metrics.json env.json scores; do
  gcloud compute scp --recurse "${VM[@]}" \
    "$GRAFIN_VM_NAME:$GRAFIN_VM_DIR/grafin-ai-training/runs/$RUN_ID/$f" "$REPO_DIR/runs/$RUN_ID/"
done
echo "pulled to runs/$RUN_ID"
