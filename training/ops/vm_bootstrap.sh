#!/usr/bin/env bash
# Runs ON the VM from the unpacked bundle (see ops/vm_bundle.sh). Expects ~/kaggle.json.
set -euo pipefail
G="$HOME/grafin"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$G/grafin-ai-dataset"
uv sync
# fetch + localize + validate HI-Small (no legacy accounts file on the VM; only the
# transactions file matters for training and it does not depend on it)
uv run grafin-dataset all --dataset small --data-root "$G/grafin-ai-data" \
  --kaggle-json "$HOME/kaggle.json" --no-legacy
got="$(sha256sum "$G/grafin-ai-data/HI-Small-ID/HI-Small_Trans_sorted.csv" | cut -d' ' -f1)"
want="$(cat "$G/expected_small_sha256")"
if [[ "$got" != "$want" ]]; then
  echo "MISMATCH: VM HI-Small-ID $got != laptop $want — scores would not line up; stop." >&2
  exit 1
fi
echo "HI-Small-ID identical to the laptop copy"
cd "$G/grafin-ai-training"
chmod +x ops/*.sh
ops/vm_setup.sh
