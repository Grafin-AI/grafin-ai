# garda-ai-training — common tasks. Linux needs EXTRA=cpu (CI) or EXTRA=cu124 (GPU VM).
EXTRA ?=
SYNC_FLAGS = $(if $(EXTRA),--extra $(EXTRA),)
# `uv run` re-syncs the environment: pass the same extra so CUDA/CPU torch is kept.
RUN = uv run $(SYNC_FLAGS)
DATA_ROOT ?= ../garda-ai-data
SMOKE_DIR ?= .smoke

.PHONY: install lint typecheck test check smoke smoke-small compare clean-smoke

install:
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
	$(RUN) garda-train gnn --data $(SMOKE_DIR)/fixture/raw/HI-Fixture_Trans.csv --source raw \
		--epochs 2 --batch-size 32 --num-neighs 10 10 --device cpu \
		--runs-dir $(SMOKE_DIR)/runs --cache-dir $(SMOKE_DIR)/cache --no-mlflow
	$(RUN) garda-train compare --runs-dir $(SMOKE_DIR)/runs

# Real HI-Small-ID, paper settings, 3 batches per loader (CPU, ~4-6 min on an M2).
smoke-small:
	$(RUN) garda-train gnn --data $(DATA_ROOT)/HI-Small-ID/HI-Small_Trans_sorted.csv --source id \
		--epochs 1 --max-batches 3 --device cpu --runs-dir $(SMOKE_DIR)/runs \
		--cache-dir cache --no-mlflow

compare:
	$(RUN) garda-train compare --runs-dir runs

clean-smoke:
	rm -rf $(SMOKE_DIR)
