# shellcheck shell=bash
# Shared by ops scripts: load ops/vm.env and fail on unset variables.
set -euo pipefail
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$OPS_DIR/.." && pwd)"
if [[ -f "$OPS_DIR/vm.env" ]]; then
  # shellcheck disable=SC1091
  source "$OPS_DIR/vm.env"
fi
require() {
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      echo "error: $name is not set (copy ops/vm.env.example to ops/vm.env)" >&2
      exit 3
    fi
  done
}
