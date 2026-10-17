# garda-ai-backend

FastAPI + SQLAlchemy (async) + Postgres + Redis backend for the Garda AI AML dashboard.
Architecture docs: [`docs/c4/`](docs/c4/).

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn garda_ai_backend.main:app --reload
uv run pytest -q          # needs Docker (testcontainers: Postgres 16, Redis 7)
uv run ruff check garda_ai_backend
```

## Key endpoints (all require a user bearer token)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/transactions/{id}` | Detail with `from_*`/`to_*` bank, account, entity. Entity names masked unless admin + `?unmasked=true`. No `is_laundering`. |
| GET | `/api/v1/transactions/{id}/explanation` | `TransactionExplanation`: `source` (`llm`\|`rules`), `model`, `pattern_matching`, `behavior_analysis`, `network_analysis`, `recommendation` (starts with PROSES/TINJAU/TUNDA/BLOKIR), `risk_factors[{code,label,detail}]`, `evidence{}`, `generated_at`. Cached in Redis `expl:{id}` for 24h. |
| GET | `/api/v1/users/{entity_id}/profile` | Direct lookup by entity id. |
| GET | `/api/v1/system/health` | `model_accuracy_simulated`, `model_name`. |

Explanation evidence only uses data in the 24h window ending at the transaction's
`event_time` and never reads the ground-truth label. The LLM is never called on the
ingest path.

## Environment (prefix `GARDA_`)

Required: `DATABASE_URL`, `SCORING_URL`, `SCORING_TOKEN`, `INGEST_TOKEN` (>=16 chars);
`JWT_SECRET` (>=32 chars outside development). Optional:

| Variable | Default | Purpose |
|---|---|---|
| `GARDA_MODEL_NAME` | empty | Real model behind scoring; when set, health reports `model_accuracy_simulated=false`. |
| `GARDA_LLM_PROVIDER` | `none` | `none` \| `anthropic` \| `gemini` \| `ollama`. `none` = deterministic rules narrative. |
| `GARDA_LLM_API_KEY` | empty | Provider key (anthropic, gemini). Never logged. |
| `GARDA_LLM_MODEL` | per provider | `claude-sonnet-5-5` / `gemini-2.5-flash` / `llama3.1:8b` |
| `GARDA_LLM_BASE_URL` | per provider | `https://api.anthropic.com` / `https://generativelanguage.googleapis.com` / `http://host.docker.internal:11434` |
| `GARDA_LLM_TIMEOUT_S` | `20` | Per-call timeout; on timeout/error/invalid JSON the rules narrative is returned. |
