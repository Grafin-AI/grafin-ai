.PHONY: up down logs seed-secret config

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
