#!/usr/bin/env bash
# Create the training VM (run on your laptop). Deep Learning VM images ship the NVIDIA driver.
# List current CUDA 12 image families if the default is retired:
#   gcloud compute images list --project deeplearning-platform-release --no-standard-images \
#     --filter="family~cu12" --format="value(family)" | sort -u
source "$(dirname "$0")/_env.sh"
require GARDA_GCP_PROJECT GARDA_GCP_ZONE GARDA_VM_NAME GARDA_VM_TYPE GARDA_GPU_COUNT \
  GARDA_IMAGE_FAMILY GARDA_DISK_GB
gcloud compute instances create "$GARDA_VM_NAME" \
  --project "$GARDA_GCP_PROJECT" \
  --zone "$GARDA_GCP_ZONE" \
  --machine-type "$GARDA_VM_TYPE" \
  --accelerator "type=nvidia-tesla-t4,count=$GARDA_GPU_COUNT" \
  --maintenance-policy TERMINATE \
  --image-family "$GARDA_IMAGE_FAMILY" \
  --image-project deeplearning-platform-release \
  --boot-disk-size "${GARDA_DISK_GB}GB" \
  --metadata install-nvidia-driver=True \
  --scopes cloud-platform
echo "created. next: gcloud compute ssh $GARDA_VM_NAME --zone $GARDA_GCP_ZONE, clone the repo, run ops/vm_setup.sh"
echo "STOP THE VM WHEN IDLE: gcloud compute instances stop $GARDA_VM_NAME --zone $GARDA_GCP_ZONE"
