DATASET ?= small
KAGGLE_JSON ?= $(or $(GARDA_KAGGLE_JSON),$(HOME)/.kaggle/kaggle.json)

.PHONY: install lint typecheck test check fetch localize validate all

install:
	uv sync

lint:
	uv run ruff check .

typecheck:
	uv run mypy garda_ai_dataset

test:
	uv run pytest -q

check: lint typecheck test

fetch:
	uv run garda-dataset fetch --dataset $(DATASET) --kaggle-json "$(KAGGLE_JSON)"

localize:
	uv run garda-dataset localize --dataset $(DATASET)

validate:
	uv run garda-dataset validate --dataset $(DATASET)

all:
	uv run garda-dataset all --dataset $(DATASET) --kaggle-json "$(KAGGLE_JSON)"
