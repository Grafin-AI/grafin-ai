#!/bin/sh
set -e
echo "running migrations..."
uv run alembic upgrade head
echo "seeding admin + sim_state..."
uv run python -m garda_ai_backend.seed || true
echo "starting api..."
exec uv run uvicorn garda_ai_backend.main:app --host 0.0.0.0 --port 8000
