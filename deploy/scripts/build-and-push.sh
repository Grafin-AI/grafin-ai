#!/usr/bin/env bash
# Build all four service images for the VM's architecture and push them to
# Artifact Registry. Run from a checkout of this monorepo.
#
#   ./scripts/build-and-push.sh asia-southeast2-docker.pkg.dev/my-project/grafin v1
#
# CRITICAL: GCE VMs are linux/amd64. An Apple Silicon Mac builds linux/arm64 by
# default, and those images will fail on the VM with "exec format error" — so we
# force --platform linux/amd64 here. Cross-building under emulation is slower
# than a native build; if it drags, use Cloud Build instead (see the runbook).
set -euo pipefail

REGISTRY="${1:?usage: build-and-push.sh <registry> [tag]}"
TAG="${2:-latest}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

declare -a SERVICES=(
  "backend:grafin-ai-backend"
  "scoring:grafin-ai-scoring"
  "ingest:grafin-ai-ingest"
  "dashboard-web:grafin-ai-frontend"
)

command -v docker >/dev/null || { echo "ERROR: docker not found"; exit 1; }
docker buildx version >/dev/null 2>&1 || { echo "ERROR: docker buildx required for --platform builds"; exit 1; }

for entry in "${SERVICES[@]}"; do
  src="${entry%%:*}"; name="${entry##*:}"
  [ -d "$ROOT/$src" ] || { echo "ERROR: $ROOT/$src not found"; exit 1; }
  echo "==> $name  (from $src)"
  docker buildx build \
    --platform linux/amd64 \
    -t "$REGISTRY/$name:$TAG" \
    -t "$REGISTRY/$name:latest" \
    --push \
    "$ROOT/$src"
done

echo
echo "pushed to $REGISTRY  (tag: $TAG, plus :latest)"
