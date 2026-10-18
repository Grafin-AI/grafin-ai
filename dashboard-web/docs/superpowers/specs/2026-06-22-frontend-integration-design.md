# Grafin AI — Frontend Integration Design

**Date:** 2026-06-22
**Status:** Approved (brainstorming)
**Repo:** `grafin-ai-dashboard-web`
**Anchor spec:** `grafin-ai-deploy/docs/superpowers/specs/2026-06-22-system-architecture-design.md`

Replace every hardcoded mock array with real data from `grafin-ai-backend`, add auth, and make the live monitor stream over WebSocket — without redesigning the existing UI. Components keep their markup; only their data source changes.

---

## 1. Stack additions

- **TanStack Query** (server state, caching, refetch, pagination).
- **Generated API types** from backend `openapi.json` (`openapi-typescript`) → one source of truth for the contract; no hand-written DTOs.
- **Axios** API client with auth interceptors + refresh-on-401.
- **React Context** auth provider + protected routes; login page.
- **Native WebSocket** wrapped in a `useLiveTransactions` hook.
- `.env` (`VITE_API_BASE_URL`, `VITE_WS_URL`).

## 2. Data layer

- `src/api/client.ts` — axios instance; attaches access token; on 401 calls `/auth/refresh` once, retries, else logs out.
- `src/api/types.ts` — generated from OpenAPI (CI step / `npm run gen:api`).
- `src/api/queries/*` — typed TanStack Query hooks per view (`useMetricsOverview`, `useVolume`, `useHeatmap`, `useFraudAnalytics`, `useProvinces`, `useUserRisk`, `useUserProfile`, `useAlerts`, `useSystemHealth`, `useSimState`).
- Query keys include `sim_now` bucket so caches refresh as the simulation advances.

## 3. Auth

- `AuthProvider` holds user/role + tokens (access in memory, refresh in httpOnly cookie if backend sets one, else secure storage).
- `LoginPage`; `RequireAuth` wrapper around the dashboard; `RequireRole` for admin-only controls (sim control, unmasked PII).
- Role drives UI: analysts see masked PII; admins see replay controls + unmask action.

## 4. Live monitor (WebSocket + resync) — `TransactionMonitor.tsx`

Implements the consistency contract (anchor §5):
1. On mount, `useQuery(['live'])` → `GET /transactions/live?limit=N` for the authoritative recent window; record max `seq` as cursor.
2. Open WS via `useLiveTransactions`; on each message with `seq > cursor`, prepend to a **bounded** list (cap ~100 rows) and advance cursor.
3. On reconnect, refetch `GET /transactions/live?after_seq=cursor` to backfill the gap, then resume WS.
4. Remove `mockTransactions`; row shape comes from generated types. Keep existing formatting (IDR, fraud-score bar, status colors). "Auto-refresh every 2s" badge becomes the live WS indicator.

## 5. Per-view wiring (replace mock → query hook)

| Component | Replaces | Source |
|---|---|---|
| `MetricsOverview` | inline `metrics` | `useMetricsOverview()` |
| `TransactionVolume` | `'24h'/'weekly'/'monthly'/'yearly'` arrays | `useVolume(range)` |
| `TransactionHeatmap` | generated 7×24 | `useHeatmap()` |
| `TransactionMonitor` | `mockTransactions` | live query + WS (§4) |
| `TransactionDetailsModal` | random `extendedTransaction` | `useTransaction(id)` |
| `FraudAnalytics` | `fraudDistributionData` | `useFraudAnalytics()` |
| `GeographicMap` | `provinceData` | `useProvinces()` |
| `UserRiskProfiling` | `mockProfiles` | `useUserRisk(filters,page)` |
| `UserProfileDetailsModal` | random profile | `useUserProfile(entityId)` |
| `AlertsPanel` | `mockAlerts` | `useAlerts()` + ack mutation |
| `App.tsx` system-health cards | hardcoded 23ms/99.94%/… | `useSystemHealth()` (real; Phase-1 model accuracy labeled "simulated") |

PII shown is whatever the API returns (already masked server-side); the frontend never unmasks on its own.

## 6. UX states

- Loading skeletons (existing `skeleton.tsx`) per card/table while queries load.
- Error + empty states (toast via existing `sonner`).
- Simulation clock + admin play/pause/speed (`useSimState`/`useSimControl`) live on a **dedicated admin-only Simulation page** (`SimulationControl`), reached from an admin-only Sidebar item — **not** in the dashboard Header (the dashboard stays a clean monitoring UI). See `docs/superpowers/specs/2026-06-23-simulation-page-design.md`.

## 7. Performance

- TanStack Query dedupes + caches; stale-times tuned to the sim tick.
- Bounded live list; virtualized if needed.
- Code-split routes; lazy-load modals.
- Charts memoized; WS updates batched to animation frames to avoid render thrash.

## 8. Build/deploy

- Existing Vite build + `nginx.conf`/Dockerfile retained; nginx also terminates TLS and proxies `/api` + `/ws` to backend (config finalized in `grafin-ai-deploy`).
- `npm run gen:api` wired into CI so types never drift from the backend contract.

## 9. Testing

- Component tests with mocked query hooks (Vitest + Testing Library).
- `useLiveTransactions` resync logic unit-tested (cursor, reconnect backfill, bounded list).
- Auth flow + role-gated UI tests.

## 10. C4 documentation (deliverable)

After integration, generate **C4 Component + Code** docs via the c4-architecture plugin (bottom-up against this repo's code) into `grafin-ai-dashboard-web/docs/c4/`. System-wide Context + Container live in `grafin-ai-deploy/docs/c4/`.

## 11. Out of scope here

- API/aggregation, auth issuance, masking → `grafin-ai-backend`.
- Scoring/replay → `grafin-ai-pipeline`.
