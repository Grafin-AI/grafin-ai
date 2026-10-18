# Demo final: persisted explanations, Insight Narrator+, network graph, UI revamp

Date: 2026-10-18 (deadline mode: code freeze 22:30 WIB). Repos: garda-ai-backend, garda-ai-dashboard-web.

Scope: **A** persisted explanations + generate button, **C1** Insight Narrator+ (reason code,
confidence, policy references, LTKM draft), **C2** network graph, **B-lite** UI/UX revamp
(mockup made with Claude Design, GSAP motion). Stretch: **C3** Radar Regulator. Cut to
roadmap: GNN+XGBoost hybrid.

## A. Persisted explanations (backend)

Table `transaction_explanations` (alembic migration after `e4a8b2c6d913`):

| column | type |
|---|---|
| transaction_id | BigInteger PK, FK transactions.id |
| source | String (`llm` only is persisted) |
| model | String |
| pattern_matching, behavior_analysis, network_analysis, recommendation | Text |
| reason_code | String |
| confidence | String (`Tinggi`/`Sedang`/`Rendah`) |
| references | JSONB (list of `{id, title}`) |
| risk_factors | JSONB |
| evidence | JSONB |
| str_draft | JSONB nullable (C1) |
| generated_by | String (username) |
| generated_at, str_generated_at | timestamptz (str nullable) |

Endpoints (all require auth, like the current one):
- `GET /api/v1/transactions/{id}/explanation` -> 200 `TransactionExplanation` if stored;
  404 `{"detail": "explanation_not_generated"}` if the transaction exists but has none;
  404 `{"detail": "transaction not found"}` otherwise.
- `POST /api/v1/transactions/{id}/explanation` -> generates. If a row exists, returns it (200)
  without calling the LLM. LLM success -> insert (`ON CONFLICT DO NOTHING`, then select: a
  concurrent click returns the first row) and return with `persisted: true`. LLM disabled or
  failed -> return the rules narrative with `source: "rules"`, `persisted: false`, NOT stored
  (retry stays possible). Rules narrative gets `reason_code` from the deterministic mapping and
  `confidence` from the score (>=0.85 Tinggi, >=0.6 Sedang, else Rendah).
- Redis `expl:*` cache removed (delete the cache code path and its tests).

`TransactionExplanation` response = current fields + `reason_code: str`, `confidence: str`,
`references: [{id, title}]`, `persisted: bool`, `str_draft: StrDraft | null`.

## C1. Insight Narrator+ (backend)

- Knowledge base `services/explain/knowledge.py`: ~12 entries `{id, title, tags, text}`,
  Indonesian, paraphrased summaries (not legal text; each `text` ends with no citation of
  article numbers unless certain). Topics: UU 8/2010 TPPU (overview, reporting duty),
  POJK 8/2023 APU-PPT (CDD/EDD, monitoring), PPATK LTKM indicators, and one per typology/factor
  (fan-in mule, fan-out/smurfing, cycle/round-tripping, gather-scatter, velocity, cross-bank,
  unusual amount). Retrieval = deterministic: entries whose tags intersect the risk-factor
  codes + typology, plus the two general entries; max 5.
- Prompt gets the retrieved entries; LLM JSON adds `reason_code` (one of a fixed list, e.g.
  `GA-FANIN`, `GA-FANOUT`, `GA-CYCLE`, `GA-GATHER`, `GA-VELOCITY`, `GA-AMOUNT`, `GA-NETWORK`),
  `confidence`, `references` (list of entry ids it used; unknown ids dropped; titles filled
  server-side). Invalid reason_code -> deterministic mapping.
- `POST /api/v1/transactions/{id}/str-draft` -> requires a persisted explanation (409
  `explanation_required` otherwise). Returns existing draft if stored, else LLM generates and
  stores `str_draft`:
  `{ "nomor_draf": "LTKM-DRAFT-<id>", "pihak": {pengirim, penerima}, "kronologi": str,
  "indikator": [str], "analisis": str, "rekomendasi": str, "catatan": "DRAF — perlu verifikasi
  analis sebelum dilaporkan ke PPATK" }`. Parties come from evidence/detail (masked per view),
  never invented. LLM failure -> 502 `str_generation_failed` (nothing stored).

## C2. Network graph (backend)

`GET /api/v1/transactions/{id}/network` -> accounts within 2 hops of the sender and receiver,
edges with event_time in [t-24h, t]. Caps: 60 nodes, 150 edges (keep the focal edge and edges
touching the focal accounts first, then by fraud_score desc). Response:
```
{ "transaction_id": int, "window_hours": 24,
  "nodes": [{ "id": str, "label": str (masked account), "bank": str, "role": "sender"|"receiver"|"other",
              "flagged_count": int }],
  "edges": [{ "id": int, "source": str, "target": str, "amount": float, "currency": str,
              "event_time": iso, "status": str, "fraud_score": float, "focal": bool }],
  "truncated": bool }
```
Masking follows the same users-view rules as transaction detail.

## C3 (stretch). Radar Regulator (backend)

`GET /api/v1/analytics/institutions` -> `{ "institutions": [{bank, transactions, flagged,
blocked, flagged_rate}], "flows": [{from_bank, to_bank, flagged_count, amount}] }` for the top
12 banks by volume (others as "Lainnya"), over the loaded data. Page labelled
"Simulasi federasi — prototipe memakai model terpusat; data dipartisi per institusi".

## B-lite + frontend

- Mockup first (Claude Design artifact), then implement in garda-ai-dashboard-web keeping
  current data hooks. GSAP (`gsap` + `@gsap/react` useGSAP): KPI count-up, staggered card
  entrance, live-row slide-in, blocked-alert pulse, modal section reveal, graph build-in; all
  disabled under `prefers-reduced-motion`.
- Modal: no auto LLM call. Shows "Buat Penjelasan AI" button when GET returns
  `explanation_not_generated`; loading state; on `persisted:false` shows "Mode cadangan" badge +
  "Coba lagi". Shows reason_code, confidence, Rujukan chips, and "Buat Draf LTKM" button (enabled
  when persisted) rendering the draft with copy/print.
- "Analisis Jaringan" panel: d3-force SVG graph (`d3-force` dep), focal edge highlighted,
  flagged/blocked edges red, node colour by role.
- Stretch: "Radar Regulator" page in Sidebar.

## Testing

Backend TDD (pytest, existing fixtures): GET/POST explanation states, concurrency-safe insert,
rules not persisted, references filtering, str-draft 409/200/502, network caps + masking,
institutions aggregate. Frontend vitest: button states, fallback badge, LTKM render, graph data
mapping. Final E2E on the local stack.
