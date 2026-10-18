# grafin-ai-training — common tasks. Linux needs EXTRA=cpu (CI) or EXTRA=cu124 (GPU VM).
EXTRA ?=
SYNC_FLAGS = $(if $(EXTRA),--extra $(EXTRA),)
# `uv run` re-syncs the environment: pass the same extra so CUDA/CPU torch is kept.
RUN = uv run $(SYNC_FLAGS)
DATA_ROOT ?= ../grafin-ai-data
SMOKE_DIR ?= .smoke

.PHONY: install lint typecheck test check smoke smoke-small compare clean-smoke

install:
# Apple silicon: this Mac also has an x86_64 (Rosetta) Python 3.11, which uv would otherwise pick.
ifeq ($(shell uname -s)-$(shell uname -m),Darwin-arm64)
	@test -x .venv/bin/python || uv venv --python cpython-3.11-macos-aarch64-none
endif
	uv sync $(SYNC_FLAGS)

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest -q

check: lint typecheck test

# End-to-end on the synthetic fixture (CPU, ~10 s).
smoke: clean-smoke
	$(RUN) python tests/fixture.py $(SMOKE_DIR)/fixture
	$(RUN) grafin-train gnn --data $(SMOKE_DIR)/fixture/raw/HI-Fixture_Trans.csv --source raw \
		--epochs 2 --batch-size 32 --num-neighs 10 10 --device cpu \
		--runs-dir $(SMOKE_DIR)/runs --cache-dir $(SMOKE_DIR)/cache --no-mlflow
	$(RUN) grafin-train compare --runs-dir $(SMOKE_DIR)/runs

# Real HI-Small-ID, paper settings, 3 batches per loader (CPU, ~4-6 min on an M2).
smoke-small:
	$(RUN) grafin-train gnn --data $(DATA_ROOT)/HI-Small-ID/HI-Small_Trans_sorted.csv --source id \
		--epochs 1 --max-batches 3 --device cpu --runs-dir $(SMOKE_DIR)/runs \
		--cache-dir cache --no-mlflow

compare:
	$(RUN) grafin-train compare --runs-dir runs

clean-smoke:
	rm -rf $(SMOKE_DIR)
