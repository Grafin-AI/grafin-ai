# Garda AI — Deploy

One-command local stack: Postgres, Redis, backend (migrate+seed+serve), ETL (one-shot
CSV load), replay worker, frontend (nginx), Prometheus, Grafana.

## Prerequisites
- Docker + Docker Compose
- The dataset at `../garda-ai-data/HI-Small/` (set `GARDA_DATA_HOST_DIR` otherwise)
- A `repositories/.dockerignore` at the workspace root (the pipeline build context).
  If missing, create it with: `.venv`, `node_modules`, `.git`, `garda-ai-data`, `build`, `dist`.

## Run
```bash
cp .env.example .env
make seed-secret   # paste into GARDA_JWT_SECRET in .env
make up
```
Boot order is enforced by health checks + `depends_on`:
postgres/redis → backend (runs `alembic upgrade head` + seeds admin/sim_state) →
etl (loads ~5M transactions, runs once) → replay (streams scored events to Redis).

## URLs
- Dashboard: http://localhost:8080  (login: `admin@garda.local` / `admin`)
- API + docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## Simulation clock
The replay worker walks the loaded transactions on an accelerated clock and pushes scored
events to the dashboard. Control it from the **Simulation page** (admin-only sidebar item) or
the API — the dashboard itself stays a clean monitoring UI with no sim controls:
```bash
# resume + set 20x for a livelier demo
curl -s -X POST localhost:8000/api/v1/sim/control -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"running":true,"speed":20}'
```
- `GARDA_RESET_CLOCK=false` (the default): on (re)start the worker **bootstraps the clock only
  on a fresh run** and otherwise **resumes** from the persisted `sim_now`. A restart never
  wipes already-surfaced events. The worker also survives a transient tick error (logs and
  continues) rather than dying.
- To replay the whole dataset again from `t0` on demand: **`make demo-reset`** (stops the
  worker, wipes `transaction_events`/`alerts`, rewinds the clock, restarts).

## Notes
- First run loads the full dataset — the `etl` service can take minutes; `replay` waits
  for it (`service_completed_successfully`).
- Change `admin@garda.local`'s password before any non-demo use.
- After changing service code, redeploy just that service: `docker compose up -d --build <svc>`
  (e.g. `backend`, `frontend`, `replay`), then hard-refresh the browser to drop the old bundle.
- Login uses a plain string email (not strict `EmailStr`), so the reserved `.local` demo
  domain is accepted. The dashboard aggregates poll every ~4s and the live monitor streams via
  WebSocket with a REST resync fallback, so the UI tracks the advancing simulation.
