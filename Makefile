.PHONY: up down logs seed-secret config demo-reset

config:
	docker compose config >/dev/null && echo "compose OK"

up:
	@test -f .env || (echo "copy .env.example to .env and set GARDA_JWT_SECRET" && exit 1)
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

seed-secret:
	@head -c 48 /dev/urandom | base64

# Deliberate demo reset: stop the worker, wipe surfaced events/alerts + rewind the
# clock to the data start, then restart so the whole dataset streams again from t0.
demo-reset:
	docker compose stop replay
	docker compose run --rm replay uv run garda-replay-reset
	docker compose start replay
	@echo "reset done — replay restarted from the beginning"
