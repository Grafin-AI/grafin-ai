# grafin-ai-scoring

Stateless fraud-scoring service for the Grafin AI platform. Exposes a token-gated batch
`POST /v1/score` that returns `{fraud_score, typology, status}` per transaction. No database,
no Redis — the response is a pure function of the request.

## Run
```
uv sync
GRAFIN_SCORING_TOKEN=dev uv run uvicorn grafin_ai_scoring.api.app:app --reload
```

## Test / lint / type-check
```
GRAFIN_SCORING_TOKEN=t uv run pytest -q
uv run ruff check .
uv run mypy grafin_ai_scoring
```

Config (env, `GRAFIN_` prefix): `SCORING_TOKEN` (required), `SCORER`
(`label_replay` default | `precomputed` | `ml`), `SCORES_PATH`, `SEED`, `FN_RATE`, `FP_RATE`,
`LOG_LEVEL`.

`SCORER=precomputed` serves model scores exported by `grafin-train export-scores`
(`scores.csv`: `transaction_id,fraud_score,prob,status,typology`) from `SCORES_PATH`. The file is
loaded once at startup (missing file = startup error); `is_laundering` is not used, and unknown
ids score `0.0` / `approved` (counted and logged every 1000 misses, never an error). Ops: `/healthz`, `/readyz`, `/metrics`.
Contract + design: `docs/superpowers/specs/2026-06-25-scoring-service-design.md`.
