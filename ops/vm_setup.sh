#!/usr/bin/env bash
# Run ON the VM inside the cloned repo: checks GPUs, installs uv + CUDA deps, pulls data.
source "$(dirname "$0")/_env.sh"
require GARDA_GCS_BUCKET GARDA_EXTRA
nvidia-smi -L
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$REPO_DIR"
uv python install 3.11
uv sync --frozen --extra "$GARDA_EXTRA"
uv run --extra "$GARDA_EXTRA" python -c \
  "import torch, torch_geometric.typing as t; n = torch.cuda.device_count(); assert n > 0 and t.WITH_PYG_LIB; print(f'cuda ok: {n} GPU(s)')"
"$OPS_DIR/sync.sh" pull-data
