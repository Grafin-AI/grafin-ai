#!/usr/bin/env bash
# Create the training VM (run on your laptop). Deep Learning VM images ship the NVIDIA driver.
# List current CUDA 12 image families if the default is retired:
#   gcloud compute images list --project deeplearning-platform-release --no-standard-images \
#     --filter="family~cu12" --format="value(family)" | sort -u
source "$(dirname "$0")/_env.sh"
require GRAFIN_GCP_PROJECT GRAFIN_GCP_ZONE GRAFIN_VM_NAME GRAFIN_VM_TYPE GRAFIN_GPU_COUNT \
  GRAFIN_IMAGE_FAMILY GRAFIN_DISK_GB
gcloud compute instances create "$GRAFIN_VM_NAME" \
  --project "$GRAFIN_GCP_PROJECT" \
  --zone "$GRAFIN_GCP_ZONE" \
  --machine-type "$GRAFIN_VM_TYPE" \
  --accelerator "type=nvidia-tesla-t4,count=$GRAFIN_GPU_COUNT" \
  --maintenance-policy TERMINATE \
  --image-family "$GRAFIN_IMAGE_FAMILY" \
  --image-project deeplearning-platform-release \
  --boot-disk-size "${GRAFIN_DISK_GB}GB" \
  --metadata install-nvidia-driver=True \
  --scopes cloud-platform
echo "created. next: gcloud compute ssh $GRAFIN_VM_NAME --zone $GRAFIN_GCP_ZONE, clone the repo, run ops/vm_setup.sh"
echo "STOP THE VM WHEN IDLE: gcloud compute instances stop $GRAFIN_VM_NAME --zone $GRAFIN_GCP_ZONE"
