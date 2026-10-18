.PHONY: up down reset logs seed-secret config sim obs dataset-sort demo-history demo-test demo-seed \
	demo-live tunnel admin-password

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
# Raw HI-Small only: ../garda-ai-data/HI-Small-ID already ships HI-Small_Trans_sorted.csv.
dataset-sort:
	@test -f "$(DATA_DIR)/HI-Small_Trans_part1.csv" || \
		(echo "ERROR: $(DATA_DIR)/HI-Small_Trans_part1.csv not found (override with DATA_DIR=...)" && exit 1)
	head -1 "$(DATA_DIR)/HI-Small_Trans_part1.csv" > "$(DATA_DIR)/HI-Small_Trans_sorted.csv"
	tail -q -n +2 "$(DATA_DIR)/HI-Small_Trans_part1.csv" "$(DATA_DIR)/HI-Small_Trans_part2.csv" \
		| LC_ALL=C sort >> "$(DATA_DIR)/HI-Small_Trans_sorted.csv"
	@echo "wrote $(DATA_DIR)/HI-Small_Trans_sorted.csv ($$(( $$(wc -l < "$(DATA_DIR)/HI-Small_Trans_sorted.csv") - 1 )) rows)"

# --- Demo replay -------------------------------------------------------------
# HI-Small-ID spans 2025-09-04..09-21 (5,078,345 rows; sim ordinal = 1-based CSV row).
# The model's split (day index from 2025-09-04): validation days 2025-09-10..09-11
# (ordinals 3,248,922..4,214,445), test days from 2025-09-12 (ordinal 4,214,446).
# Precomputed scores cover exactly val + test, so history starts at the first val row.
DEMO_HISTORY_SKIP  ?= 3248921
DEMO_HISTORY_LIMIT ?= 965524
DEMO_TEST_SKIP     ?= 4214445
DEMO_TEST_SPEED    ?= 60

# 1) Seed the validation days as history, unpaced (MAX_GAP_S=0), ~10 min at the
#    ~2,400 txn/s the stack sustains with BATCH_SIZE=1000.
demo-history:
	docker compose --profile sim run --rm --build \
	  -e GARDA_SKIP=$(DEMO_HISTORY_SKIP) -e GARDA_LIMIT=$(DEMO_HISTORY_LIMIT) \
	  -e GARDA_MAX_GAP_S=0 -e GARDA_BATCH_SIZE=1000 sim

# 2) Replay the test period live from 2025-09-12, right where demo-history stopped:
#    1 dataset-hour per wall-minute at speed 60. Ctrl-C to stop.
demo-test:
	docker compose --profile sim run --rm --build \
	  -e GARDA_SKIP=$(DEMO_TEST_SKIP) -e GARDA_SPEED=$(DEMO_TEST_SPEED) \
	  -e GARDA_BATCH_SIZE=100 sim

# Old names, kept for muscle memory.
demo-seed: demo-history
demo-live: demo-test

# Wipe the stack INCLUDING the Postgres volume. Required when switching datasets
# (GARDA_DATA_HOST_DIR) or scorers: ingest/sim rows from the old one stay otherwise.
reset:
	docker compose --profile sim --profile observability down -v

# --- Public access -----------------------------------------------------------
# Change a dashboard password (default admin@garda.local). Do this BEFORE sharing a
# public URL: the seeded admin/admin would otherwise work for anyone who finds it.
admin-password:
	@./scripts/set-admin-password.sh $(EMAIL)

# Expose the dashboard on the internet via ngrok. Only the frontend is tunnelled:
# its nginx proxies /api and /api/v1/ws to the backend inside the compose network,
# and the app uses relative URLs, so the browser upgrades to https/wss on its own.
# The backend is never exposed.
#
# Do NOT add ngrok basic-auth: the app sends `Authorization: Bearer <jwt>` on every
# API call, and basic-auth checks that same header, so every request after login
# would be rejected with a 401.
#
# One-time: ngrok config add-authtoken <token from dashboard.ngrok.com>
# Optional: NGROK_URL=<your free static domain> keeps the same URL across restarts.
tunnel:
	@command -v ngrok >/dev/null || { echo "install ngrok first: brew install ngrok"; exit 1; }
	@PORT=$$(sed -n 's/^FRONTEND_HOST_PORT=//p' .env 2>/dev/null); \
	  curl -s -o /dev/null --max-time 3 http://localhost:$${PORT:-3000} \
	    || { echo "dashboard not reachable on :$${PORT:-3000} (start it with: make up)"; exit 1; }; \
	  echo "tunnelling http://localhost:$${PORT:-3000}"; \
	  ngrok http $${PORT:-3000} $(if $(NGROK_URL),--url $(NGROK_URL),)
