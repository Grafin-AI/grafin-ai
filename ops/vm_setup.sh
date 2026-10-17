#!/usr/bin/env bash
# Run ON the VM inside the cloned repo: checks GPUs, installs uv + CUDA deps, pulls data.
source "$(dirname "$0")/_env.sh"
require GARDA_EXTRA
umask 077
nvidia-smi -L
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
cd "$REPO_DIR"
uv python install 3.11
# uv's own cache/python live under $HOME (~/.cache/uv, ~/.local/share/uv): private after chmod 700 $HOME
uv sync --frozen --extra "$GARDA_EXTRA"
uv run --extra "$GARDA_EXTRA" python -c \
  "import torch, torch_geometric.typing as t; n = torch.cuda.device_count(); assert n > 0 and t.WITH_PYG_LIB; print(f'cuda ok: {n} GPU(s)')"
if [[ -n "${GARDA_GCS_BUCKET:-}" ]]; then
  "$OPS_DIR/sync.sh" pull-data
else
  echo "GARDA_GCS_BUCKET empty: expecting data pushed with ops/vm_push.sh"
fi
ls ../garda-ai-data/*/ 2>/dev/null || echo "warning: ../garda-ai-data is empty"
