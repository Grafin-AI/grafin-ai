# grafin-ai-backend

FastAPI + SQLAlchemy (async) + Postgres + Redis backend for the Grafin AI AML dashboard.
Architecture docs: [`docs/c4/`](docs/c4/).

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn grafin_ai_backend.main:app --reload
uv run pytest -q          # needs Docker (testcontainers: Postgres 16, Redis 7)
uv run ruff check grafin_ai_backend
```

## Key endpoints (all require a user bearer token)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/transactions/{id}` | Detail with `from_*`/`to_*` bank, account, entity. Entity names masked unless admin + `?unmasked=true`. No `is_laundering`. |
| GET | `/api/v1/transactions/{id}/explanation` | Stored `TransactionExplanation` (Postgres `transaction_explanations`). 404 `explanation_not_generated` if the transaction has none yet; 404 `transaction not found` otherwise. Never calls the LLM. |
| POST | `/api/v1/transactions/{id}/explanation` | Generate: returns the stored row if any (no LLM call); else LLM -> stored (`persisted: true`, first concurrent writer wins) or rules fallback (`source: "rules"`, `persisted: false`, not stored). Fields: `source`, `model`, `pattern_matching`, `behavior_analysis`, `network_analysis`, `recommendation` (starts with PROSES/TINJAU/TUNDA/BLOKIR), `reason_code` (`GA-*`), `confidence` (`Tinggi`/`Sedang`/`Rendah`), `references[{id,title}]` (curated KB in `services/explain/knowledge.py`), `risk_factors[{code,label,detail}]`, `evidence{}`, `generated_at`, `persisted`, `str_draft`. |
| POST | `/api/v1/transactions/{id}/str-draft` | LTKM draft (`StrDraft`: `nomor_draf`, `pihak{pengirim,penerima}{nama,rekening,bank}`, `kronologi`, `indikator[]`, `analisis`, `rekomendasi`, `catatan`). 409 `explanation_required` without a persisted explanation; stored draft returned as-is; LLM failure -> 502 `str_generation_failed` (nothing stored). Names stored masked; raw only for admin + `?unmasked=true`. |
| GET | `/api/v1/transactions/{id}/network` | Accounts within 2 hops of sender/receiver, edges with `event_time` in [t-24h, t]; capped at 60 nodes / 150 edges (focal edge, then focal-touching edges, then `fraud_score` desc; `truncated` flags a cut). Node `label` is the masked account id unless admin + `?unmasked=true`. |
| GET | `/api/v1/analytics/institutions` | Radar Regulator (simulated federation): `institutions[{bank,transactions,flagged,blocked,flagged_rate}]` for the top 12 sending banks by volume (rest as `Lainnya`; `flagged_rate` = (flagged+blocked)/transactions) and `flows[{from_bank,to_bank,flagged_count,amount}]` of flagged+blocked transactions between those groups. |
| GET | `/api/v1/users/{entity_id}/profile` | Direct lookup by entity id. |
| GET | `/api/v1/system/health` | `model_accuracy_simulated`, `model_name`. |

Explanation evidence only uses data in the 24h window ending at the transaction's
`event_time` and never reads the ground-truth label. The LLM is never called on the
ingest path.

## Environment (prefix `GRAFIN_`)

Required: `DATABASE_URL`, `SCORING_URL`, `SCORING_TOKEN`, `INGEST_TOKEN` (>=16 chars);
`JWT_SECRET` (>=32 chars outside development). Optional:

| Variable | Default | Purpose |
|---|---|---|
| `GRAFIN_MODEL_NAME` | empty | Real model behind scoring; when set, health reports `model_accuracy_simulated=false`. |
| `GRAFIN_LLM_PROVIDER` | `none` | `none` \| `anthropic` \| `gemini` \| `ollama`. `none` = deterministic rules narrative. |
| `GRAFIN_LLM_API_KEY` | empty | Provider key (anthropic, gemini). Never logged. |
| `GRAFIN_LLM_MODEL` | per provider | `claude-sonnet-5-5` / `gemini-3.8-flash` / `llama3.1:8b` |
| `GRAFIN_LLM_BASE_URL` | per provider | `https://api.anthropic.com` / `https://generativelanguage.googleapis.com` / `http://host.docker.internal:11434` |
| `GRAFIN_LLM_TIMEOUT_S` | `20` | Per-call timeout; on timeout/error/invalid JSON the rules narrative is returned. |
| `GRAFIN_LLM_TOOLS` | `true` | Gemini only: the model may call `get_policy_references(reason_code)` / `get_transaction_evidence(transaction_id)` (served locally from the KB and the already-computed evidence, max 3 rounds) before answering in JSON; any tool-loop failure falls back to the single call. Tool names logged as `explain_tool_calls`. |
| `GRAFIN_EXPLANATION_STORE` | `postgres` | `postgres` \| `firestore`. Where LLM explanations and LTKM drafts are stored (see Firestore). |
| `GRAFIN_FIRESTORE_PROJECT` | empty | GCP project for Firestore; empty = the ADC/environment default. |
| `GRAFIN_FIRESTORE_DATABASE` | `(default)` | Firestore database id. |
| `GRAFIN_CORS_ORIGINS` | empty | Comma-separated allowed browser origins (e.g. `https://<project>.web.app`). Empty = no CORS headers. |

## Firestore

With `GRAFIN_EXPLANATION_STORE=firestore` the Insight Narrator explanations are stored in
Google Cloud Firestore instead of Postgres: collection `transaction_explanations`, document
id = transaction id, same fields as the Postgres row plus `created_at`. Inserts use
`create()`, so concurrent "generate" clicks keep the first document (same as
`ON CONFLICT DO NOTHING`). Each generated LTKM draft is also written to collection
`str_drafts` (doc id = transaction id, with `generated_at` and `model`); a failure of that
write is logged and does not fail the request. Rules fallbacks are never stored.
Transactions, alerts and users stay in Postgres. Credentials come from Application
Default Credentials (on Cloud Run: the service account needs `roles/datastore.user`;
locally: `gcloud auth application-default login`).
