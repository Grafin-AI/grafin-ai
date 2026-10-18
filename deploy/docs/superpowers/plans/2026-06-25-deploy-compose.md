# Deploy — Local Compose Rework (Phase 6 ①)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rework `grafin-ai-deploy/docker-compose.yml` into the new local-dev stack: drop the deleted pipeline `etl`/`replay`, add `scoring` + the `ingest` one-shot seed + the backend's ingest env, and put `sim` and Prometheus/Grafana behind opt-in profiles.

**Architecture:** The stack is local-dev only. Boot order: `postgres`/`redis` healthy → `backend` (its entrypoint runs `alembic upgrade head` + seeds admin, then serves → becomes healthy) → `ingest` one-shot (seeds reference data; depends on `backend: service_healthy`, so the schema exists) → `frontend`. `scoring` runs alongside (backend calls it on `/ingest`). `sim` (profile `sim`) streams into the stack; Prometheus/Grafana (profile `observability`) are off by default.

**Tech Stack:** Docker Compose. No app-code changes — this is deploy config only.

**Spec:** `docs/superpowers/specs/2026-06-25-deploy-split-design.md`

**Guardrail — no cycles:** `backend` must NOT depend on `ingest` (ingest depends on backend being healthy). Reference-data ordering is enforced on the `sim` side instead (`sim` depends on `ingest` completed).

---

## Task 1: Rewrite `docker-compose.yml`

**Files:**
- Modify: `grafin-ai-deploy/docker-compose.yml`

- [ ] **Step 1: Replace the file with the new service set**

```yaml
name: grafin-ai

x-db-url: &db_url postgresql+asyncpg://${POSTGRES_USER:-grafin}:${POSTGRES_PASSWORD:-grafin}@postgres:5432/${POSTGRES_DB:-grafin}

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-grafin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-grafin}
      POSTGRES_DB: ${POSTGRES_DB:-grafin}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-grafin}"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  scoring:
    build: { context: ../grafin-ai-scoring }
    environment:
      GRAFIN_SCORING_TOKEN: ${GRAFIN_SCORING_TOKEN:?set GRAFIN_SCORING_TOKEN}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else sys.exit(1)"]
      interval: 5s
      timeout: 3s
      retries: 10
    # internal only — not published to the host

  backend:
    build: { context: ../grafin-ai-backend }
    environment:
      GRAFIN_DATABASE_URL: *db_url
      GRAFIN_REDIS_URL: redis://redis:6379/0
      GRAFIN_JWT_SECRET: ${GRAFIN_JWT_SECRET:?set a >=32 char secret}
      GRAFIN_ENV: ${GRAFIN_ENV:-production}
      GRAFIN_SCORING_URL: http://scoring:8000
      GRAFIN_SCORING_TOKEN: ${GRAFIN_SCORING_TOKEN:?set GRAFIN_SCORING_TOKEN}
      GRAFIN_INGEST_TOKEN: ${GRAFIN_INGEST_TOKEN:?set GRAFIN_INGEST_TOKEN (>=16 chars)}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
      scoring: { condition: service_started }
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else sys.exit(1)"]
      interval: 5s
      timeout: 3s
      retries: 20
    ports: ["8000:8000"]

  ingest:
    build: { context: ../grafin-ai-ingest }
    environment:
      GRAFIN_DATABASE_URL: *db_url
      GRAFIN_DATA_DIR: /data
    volumes:
      - ${GRAFIN_DATA_HOST_DIR:-../grafin-ai-data/HI-Small}:/data:ro
    depends_on:
      backend: { condition: service_healthy }   # backend entrypoint ran alembic upgrade -> schema exists
    restart: "no"

  frontend:
    build: { context: ../grafin-ai-dashboard-web }
    depends_on: [backend]
    ports: ["8080:8080"]

  sim:
    build: { context: ../grafin-ai-sim }
    profiles: ["sim"]
    environment:
      GRAFIN_INGEST_URL: http://backend:8000/api/v1/ingest
      GRAFIN_INGEST_TOKEN: ${GRAFIN_INGEST_TOKEN:?set GRAFIN_INGEST_TOKEN (>=16 chars)}
      GRAFIN_DATA_DIR: /data
    volumes:
      - ${GRAFIN_DATA_HOST_DIR:-../grafin-ai-data/HI-Small}:/data:ro
    depends_on:
      backend: { condition: service_healthy }
      scoring: { condition: service_started }
      ingest: { condition: service_completed_successfully }

  prometheus:
    image: prom/prometheus:latest
    profiles: ["observability"]
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports: ["9090:9090"]

  grafana:
    image: grafana/grafana:latest
    profiles: ["observability"]
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on: [prometheus]
    ports: ["3000:3000"]

volumes:
  pgdata:
```

- [ ] **Step 2: Validate the compose file**

Run: `cd grafin-ai-deploy && cp -n .env.example .env 2>/dev/null; GRAFIN_JWT_SECRET=x GRAFIN_SCORING_TOKEN=y GRAFIN_INGEST_TOKEN=0123456789abcdef docker compose config >/dev/null && echo "compose OK"`
Expected: `compose OK` (no `etl`/`replay`; `sim`/`prometheus`/`grafana` present but profile-gated).

- [ ] **Step 3: Confirm the profile gating**

Run: `docker compose config --services | sort` (default) then `docker compose --profile sim --profile observability config --services | sort`
Expected: default lists `backend backend ingest frontend postgres redis scoring` (no sim/prom/grafana); with both profiles it also lists `grafana prometheus sim`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: rework compose for the new service set (drop pipeline, add scoring+ingest, profiles)"
```

---

## Task 2: Update `.env.example` and `prometheus.yml`

**Files:**
- Modify: `grafin-ai-deploy/.env.example`, `grafin-ai-deploy/observability/prometheus.yml`

- [ ] **Step 1: Rewrite `.env.example`**

```bash
POSTGRES_USER=grafin
POSTGRES_PASSWORD=grafin
POSTGRES_DB=grafin
GRAFIN_JWT_SECRET=change-me-to-a-long-random-secret-of-at-least-32-bytes
GRAFIN_ENV=production
# Machine tokens (distinct from user JWTs). Ingest token must be >= 16 chars.
GRAFIN_SCORING_TOKEN=change-me-scoring-token
GRAFIN_INGEST_TOKEN=change-me-ingest-token-at-least-16-chars
# Absolute or relative path (from this compose file) to the dataset dir
GRAFIN_DATA_HOST_DIR=../grafin-ai-data/HI-Small
```

- [ ] **Step 2: Update `observability/prometheus.yml` (add scoring, drop the stale replay note)**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: grafin-backend
    metrics_path: /metrics
    static_configs:
      - targets: ['backend:8000']
  - job_name: grafin-scoring
    metrics_path: /metrics
    static_configs:
      - targets: ['scoring:8000']
```

- [ ] **Step 3: Commit**

```bash
git add .env.example observability/prometheus.yml
git commit -m "chore: add scoring/ingest tokens to env example; scrape scoring metrics"
```

---

## Task 3: Update the `Makefile`

**Files:**
- Modify: `grafin-ai-deploy/Makefile`

- [ ] **Step 1: Rewrite the Makefile (drop `demo-reset` which used the deleted replay; add `sim`/`obs` helpers)**

```makefile
.PHONY: up down logs seed-secret config sim obs

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
```

- [ ] **Step 2: Verify**

Run: `cd grafin-ai-deploy && make config`
Expected: `compose OK`. Confirm `demo-reset` is gone: `grep -c demo-reset Makefile` → `0`.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: Makefile — drop replay demo-reset, add sim/obs profile helpers"
```

---

## Task 4: Live smoke test (best-effort) + residue check

**Files:** none

- [ ] **Step 1: Confirm no pipeline residue in deploy config**

Run: `cd grafin-ai-deploy && grep -rniE "etl|replay|pipeline|grafin-ai-pipeline|grafin-etl|grafin-replay|sim_state" docker-compose.yml Makefile .env.example observability/ || echo "clean"`
Expected: `clean`.

- [ ] **Step 2: Best-effort stack bring-up (if Docker is available and the images build)**

Run:
```bash
cd grafin-ai-deploy
printf 'GRAFIN_JWT_SECRET=%s\nGRAFIN_SCORING_TOKEN=devscoringtoken\nGRAFIN_INGEST_TOKEN=devingesttoken16plus\n' "$(head -c 48 /dev/urandom | base64)" >> .env 2>/dev/null || true
docker compose up -d --build postgres redis scoring backend frontend
```
Then wait for backend healthy and check the ingest one-shot completed:
```bash
docker compose ps
docker compose logs ingest --tail=20
```
Expected: `backend` healthy; `ingest` exited 0 having logged `seed.done` (banks/entities/accounts counts). If the environment cannot build images (no network / no Docker), SKIP this step and note it — `docker compose config` (Task 1) is the required gate; the live bring-up is best-effort.

- [ ] **Step 3: Tear down**

Run: `docker compose down -v` (only if Step 2 ran).

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "chore: compose smoke-test fixups" || echo "nothing to commit"
```

---

## Definition of Done

- `docker compose config` valid; default services = postgres/redis/scoring/backend/ingest/frontend; `sim` + `prometheus`/`grafana` are profile-gated (`sim`, `observability`).
- No `etl`/`replay`/pipeline references anywhere in the deploy config.
- `.env.example` documents `GRAFIN_SCORING_TOKEN` + `GRAFIN_INGEST_TOKEN`; prometheus scrapes backend + scoring.
- `Makefile` has no `demo-reset`; `make config` prints `compose OK`; `make sim`/`make obs` work.
- (Best-effort) a default `up` brings the stack healthy and the ingest seed completes.
- All commits authored as Thariq Iskandar Zulkarnain M P with the `Co-Authored-By: Claude` trailer.
```
