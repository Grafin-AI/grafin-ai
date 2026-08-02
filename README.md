# garda-ai-scoring

Stateless fraud-scoring service for the Garda AI platform. Exposes a token-gated batch
`POST /v1/score` that returns `{fraud_score, typology, status}` per transaction. No database,
no Redis — the response is a pure function of the request.

## Run
```
uv sync
GARDA_SCORING_TOKEN=dev uv run uvicorn garda_ai_scoring.api.app:app --reload
```

## Test / lint / type-check
```
GARDA_SCORING_TOKEN=t uv run pytest -q
uv run ruff check .
uv run mypy garda_ai_scoring
```

Config (env, `GARDA_` prefix): `SCORING_TOKEN` (required), `SCORER` (`label_replay`|`ml`),
`SEED`, `FN_RATE`, `FP_RATE`, `LOG_LEVEL`. Ops: `/healthz`, `/readyz`, `/metrics`.
Contract + design: `docs/superpowers/specs/2026-06-25-scoring-service-design.md`.
