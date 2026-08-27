.PHONY: up down logs seed-secret config sim obs dataset-sort demo-seed demo-live

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

# --- Demo replay -------------------------------------------------------------
# The first ~1.87M rows are IBM's account-initialization block (73% self-transfers,
# near-zero laundering) plus the dense Sep 1-2 ramp — poor demo material. History
# starts at 2025-09-03 and covers six days (Wed..Mon), which fills 6 of the 7
# heatmap rows and gives the 24h volume chart a full 24/24 hourly buckets. The
# 7th row (Tue) fills in live, because demo-live streams 2025-09-09.
DEMO_SEED_SKIP  ?= 1869370
DEMO_SEED_LIMIT ?= 2345075
DEMO_LIVE_SKIP  ?= 4214445
DEMO_LIVE_SPEED ?= 60

# 1) Pre-populate six days of history, unpaced (MAX_GAP_S=0). ~16 min at the
#    ~2,400 txn/s the stack sustains with BATCH_SIZE=1000.
demo-seed:
	docker compose --profile sim run --rm --build \
	  -e GARDA_SKIP=$(DEMO_SEED_SKIP) -e GARDA_LIMIT=$(DEMO_SEED_LIMIT) \
	  -e GARDA_MAX_GAP_S=0 -e GARDA_BATCH_SIZE=1000 sim

# 2) Stream live from exactly where the seed stopped (2025-09-09): 1 dataset-hour
#    per wall-minute,
#    so a new bucket appears on the chart every minute. Ctrl-C to stop.
demo-live:
	docker compose --profile sim run --rm --build \
	  -e GARDA_SKIP=$(DEMO_LIVE_SKIP) -e GARDA_SPEED=$(DEMO_LIVE_SPEED) \
	  -e GARDA_BATCH_SIZE=100 sim
