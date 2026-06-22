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

## Notes
- First run loads the full dataset — the `etl` service can take minutes; `replay` waits
  for it (`service_completed_successfully`).
- Change `admin@garda.local`'s password before any non-demo use.
