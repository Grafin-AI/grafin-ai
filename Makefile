.PHONY: up down logs seed-secret config sim obs dataset-sort

DATA_DIR ?= ../garda-ai-data/HI-Small

config:
	docker compose config >/dev/null && echo "compose OK"

up:
	@test -f .env || (echo "copy .env.example to .env and set the secrets/tokens" && exit 1)
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# Stream the local simulation producer into the running stack (Ctrl-C to stop).
sim:
	docker compose --profile sim up --build sim

# Bring up Prometheus + Grafana alongside the stack.
obs:
	docker compose --profile observability up -d

seed-secret:
	@head -c 48 /dev/urandom | base64

# Build the chronologically sorted replay source the simulator reads.
# The raw HI-Small parts are grouped by account, not by time (~48% of rows step
# backwards), which breaks gap-based pacing and the backend's max(event_time) clock.
# Timestamps are `YYYY/MM/DD HH:MM`, zero-padded and leading, so a lexicographic
# sort is chronological. Takes ~20s, writes ~433MB. Safe to re-run (idempotent).
dataset-sort:
	@test -f "$(DATA_DIR)/HI-Small_Trans_part1.csv" || \
		(echo "ERROR: $(DATA_DIR)/HI-Small_Trans_part1.csv not found (override with DATA_DIR=...)" && exit 1)
	head -1 "$(DATA_DIR)/HI-Small_Trans_part1.csv" > "$(DATA_DIR)/HI-Small_Trans_sorted.csv"
	tail -q -n +2 "$(DATA_DIR)/HI-Small_Trans_part1.csv" "$(DATA_DIR)/HI-Small_Trans_part2.csv" \
		| LC_ALL=C sort >> "$(DATA_DIR)/HI-Small_Trans_sorted.csv"
	@echo "wrote $(DATA_DIR)/HI-Small_Trans_sorted.csv ($$(( $$(wc -l < "$(DATA_DIR)/HI-Small_Trans_sorted.csv") - 1 )) rows)"
