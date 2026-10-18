# Grafin AI — Graph-based Risk Analytics & Federated Intelligence Network

Grafin AI detects money laundering across Indonesian banks by scoring every interbank
transfer with a graph neural network. It also tells the analyst why a transfer is risky,
in plain Bahasa Indonesia.

- **Live prototype:** https://garda-ai-dev-01-52bc2.web.app (judge login is in the submission form)
- **API:** https://grafin-api-43447121190.asia-southeast2.run.app (`/readyz`)
- **Demo video:** see the submission

## What it does

1. **Federated nodes.** Each bank runs a small SDK that hashes customer identifiers and
   turns a transfer into a feature vector. Raw customer data never leaves the bank.
2. **Graph scoring.** Grafin AI scores each transfer with a **Multi-GNN (PNA)**
   (Egressy et al., AAAI 2024). The model was retrained on an Indonesian-localised IBM
   AMLworld dataset (HI-Small-ID), using causal per-day graphs with no look-ahead.
   - Test F1 is **67.17**, inside the paper's reported band of 68.16 ± 2.65.
   - Each transfer is approved, flagged for review, or blocked, using thresholds chosen
     on the validation days.
3. **Typology.** Label-free rules name the pattern behind a risky transfer:
   - Siklus Dana (Cycle)
   - Fan-in
   - Fan-out
   - Gather-scatter
   - Velocity
   - Anomali Jaringan (other network anomaly)
4. **Real-time dashboard.** A live transaction feed over WebSocket, with:
   - KPIs and alerts;
   - hourly volume and an activity heatmap;
   - typology and regional distribution;
   - a risk profile and detection analytics.
5. **Insight Narrator (Gemini).** On demand, an analyst clicks *Buat Penjelasan AI*.
   Gemini then writes an explanation of the alert containing:
   - a reason code;
   - a confidence level;
   - pattern, behaviour and network analysis;
   - recommended actions;
   - references to the relevant AML/CFT regulations (RAG-lite over a curated knowledge base).

   The explanation is generated once and persisted.
6. **LTKM draft.** One click drafts a suspicious-transaction report (LTKM/STR) for PPATK
   from the explanation.
7. **Network analysis.** An interactive 2-hop graph of the accounts around a transfer,
   over the preceding 24 hours.
8. **Radar Regulator.** A federated view across institutions: flagged flows between banks
   and per-institution risk, without exposing customer data.

## Google Cloud services

| Service | Role in Grafin AI |
|---|---|
| **Gemini** (`gemini-3.8-flash`, Generative Language API) | Insight Narrator explanations and LTKM drafts. A local Gemma model via Ollama is the fallback. |
| **Cloud Run** | Service `grafin-api` runs the FastAPI backend (REST + WebSocket), with the scoring service and Redis as private sidecars on localhost. Only the API is public. |
| **Firestore** (Native, `asia-southeast2`) | Stores Insight Narrator explanations (`transaction_explanations`) and LTKM drafts (`str_drafts`). An explanation is written once and never regenerated (`GARDA_EXPLANATION_STORE=firestore`). |
| **Firebase Hosting** | Serves the React dashboard, which calls the Cloud Run API directly with CORS. |
| **Cloud SQL** (PostgreSQL 16) | Transactions, accounts, banks, scores, alerts, users |
| **Artifact Registry** | Container images |
| **Vertex AI Workbench** (4× NVIDIA T4) | Multi-GNN training notebooks/runs; experiments tracked in **MLflow** (`training/docs/mlflow.md`) |
| **Cloud Storage** | Datasets (HI-Small-ID), model run artifacts, test outputs and the MLflow store (`gs://garda-ai-dev-01-grafin-artifacts`) |
| **Cloud Logging** | API, access and Insight Narrator tool-call logs from Cloud Run |
| **Secret Manager + IAM** | App secrets (Gemini key, JWT, DB URL, service tokens) in Secret Manager; a dedicated least-privilege runtime service account |

Insight Narrator uses **Gemini function calling**: the model calls `get_transaction_evidence`
and `get_policy_references` to pull evidence and regulation references before it writes the
case summary.

```
 Bank app ─▶ Node SDK (hash + vectorise) ─▶ Cloud Run: grafin-api ─┬─▶ Cloud SQL (Postgres)
                                              ├─ scoring sidecar     ├─▶ Firestore (explanations, LTKM)
                                              └─ redis sidecar       └─▶ Gemini (Insight Narrator)
 Analyst browser ─▶ Firebase Hosting (dashboard) ──REST/WebSocket──▶ grafin-api
```

## Repository layout

| Folder | What it contains |
|---|---|
| [`backend/`](backend) | FastAPI API: auth, ingest, live WebSocket, analytics, Insight Narrator, LTKM, network graph, Radar |
| [`dashboard-web/`](dashboard-web) | React + Vite + Tailwind dashboard |
| [`scoring/`](scoring) | Scoring service. It serves the Multi-GNN scores exported by `training/` |
| [`training/`](training) | Multi-GNN PNA training, evaluation, typology rules, score export (`garda-train`) |
| [`ingest/`](ingest) | Loads reference data (banks, accounts) |
| [`sim/`](sim) | Replays the dataset through the ingest API as live traffic |
| [`dataset/`](dataset) | Builds HI-Small-ID, the Indonesian localisation of IBM AMLworld |
| [`deploy/`](deploy) | Local stack, Terraform, and the Cloud Run / Firebase deploy steps ([`deploy/cloudrun/`](deploy/cloudrun)) |

Each component was developed as its own repository and was merged here with
`git subtree`, keeping its full history. Internal package names still use the
earlier working name `garda`.

## Run locally

```bash
cd deploy
cp .env.example .env        # set the secrets and, optionally, GARDA_LLM_API_KEY (Gemini)
make up                     # postgres, redis, scoring, backend, dashboard
make demo-history demo-test # replay validation days, then the test period live
```

## Results (HI-Small-ID, test days)

| Model | F1 | PR-AUC | ROC-AUC |
|---|---|---|---|
| Paper: Multi-GNN PNA, HI-Small | 68.16 ± 2.65 | – | – |
| Grafin, original HI-Small (reproduction) | 65.49 | – | – |
| **Grafin, HI-Small-ID (deployed)** | **67.17** | 0.622 | 0.984 |

The live replay through the full stack (validation days) gives F1 60.47, which equals
the offline validation F1. There is no train/serve skew. Details and caveats are in
[`training/README.md`](training/README.md).

## Roadmap

- Live GNN inference on GPU (Cloud Run GPU / GCE T4) in place of exported scores
- Tree-based ML (XGBoost) layer for GNN + tree hybrid scoring (in progress)
- Production federated SDK with secure aggregation
