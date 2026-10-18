# Frontend View Wiring Implementation Plan (Plan 4B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every hardcoded mock array in `grafin-ai-dashboard-web`'s components with real data from the backend: a typed TanStack Query hook per view, a `useLiveTransactions` WebSocket hook (with REST resync), the live transaction monitor, all dashboard views, the modals, the sim-clock indicator, and role-gated admin controls.

**Architecture:** Builds on Plan 4A (`api/client`, `api/types`, `auth/`, QueryClient). One `api/queries.ts` exposes a typed hook per endpoint. `useLiveTransactions` seeds from `GET /transactions/live`, opens the WS (`VITE_WS_URL`), appends events with `seq > cursor` into a bounded list, and re-fetches `?after_seq=cursor` on reconnect (the consistency contract). Each component keeps its existing JSX/markup; only its **data source** changes (mock array → hook), plus loading/error/empty states. No router change — the existing `currentView` nav stays.

**Tech Stack:** React 18 + TS, @tanstack/react-query, native WebSocket, Vitest + Testing Library.

---

### Task 1: View query hooks

**Files:**
- Create: `src/api/queries.ts`
- Test: `src/api/queries.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/api/queries.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { api } from './client';
import { useMetricsOverview, useAlerts } from './queries';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('view query hooks', () => {
  it('useMetricsOverview fetches /metrics/overview', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { total_transactions: 4, flagged: 1, blocked: 1, total_amount: 100, fraud_rate: 0.5 },
    } as any);
    const { result } = renderHook(() => useMetricsOverview(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total_transactions).toBe(4);
  });

  it('useAlerts fetches /alerts with status param', async () => {
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { alerts: [] } } as any);
    const { result } = renderHook(() => useAlerts('active'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith('/alerts', { params: { status: 'active' } });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/api/queries.test.tsx`
Expected: FAIL (cannot find `./queries`).

- [ ] **Step 3: Implement `src/api/queries.ts`**

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  AlertsResponse, FraudAnalytics, GeoResponse, HeatmapResponse, LiveResponse,
  MetricsOverview, RiskProfile, SimState, SystemHealth, TransactionDetail,
  UserRiskResponse, VolumeResponse,
} from './types';

const get = async <T,>(url: string, params?: Record<string, unknown>): Promise<T> =>
  (await api.get<T>(url, params ? { params } : undefined)).data;

export const useMetricsOverview = () =>
  useQuery({ queryKey: ['metrics', 'overview'], queryFn: () => get<MetricsOverview>('/metrics/overview') });

export const useVolume = (range: string) =>
  useQuery({ queryKey: ['metrics', 'volume', range], queryFn: () => get<VolumeResponse>('/metrics/volume', { range }) });

export const useHeatmap = () =>
  useQuery({ queryKey: ['metrics', 'heatmap'], queryFn: () => get<HeatmapResponse>('/metrics/heatmap') });

export const useFraudAnalytics = () =>
  useQuery({ queryKey: ['analytics', 'fraud'], queryFn: () => get<FraudAnalytics>('/analytics/fraud') });

export const useProvinces = () =>
  useQuery({ queryKey: ['geo', 'provinces'], queryFn: () => get<GeoResponse>('/geo/provinces') });

export const useUserRisk = (risk?: string) =>
  useQuery({ queryKey: ['users', 'risk', risk ?? 'all'], queryFn: () => get<UserRiskResponse>('/users/risk', risk ? { risk } : undefined) });

export const useUserProfile = (entityId: string | null) =>
  useQuery({
    queryKey: ['users', 'profile', entityId],
    queryFn: () => get<RiskProfile>(`/users/${entityId}/profile`),
    enabled: !!entityId,
  });

export const useAlerts = (status: string = 'all') =>
  useQuery({ queryKey: ['alerts', status], queryFn: () => get<AlertsResponse>('/alerts', { status }) });

export const useAckAlert = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post(`/alerts/${id}/ack`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
};

export const useTransactionDetail = (id: number | null) =>
  useQuery({
    queryKey: ['transaction', id],
    queryFn: () => get<TransactionDetail>(`/transactions/${id}`),
    enabled: id != null,
  });

export const useLiveRecent = (limit = 50) =>
  useQuery({ queryKey: ['transactions', 'live', limit], queryFn: () => get<LiveResponse>('/transactions/live', { limit }) });

export const useSystemHealth = () =>
  useQuery({ queryKey: ['system', 'health'], queryFn: () => get<SystemHealth>('/system/health') });

export const useSimState = () =>
  useQuery({ queryKey: ['sim', 'state'], queryFn: () => get<SimState>('/sim/state'), refetchInterval: 5000 });

export const useSimControl = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<SimState>) => api.post('/sim/control', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sim', 'state'] }),
  });
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/api/queries.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/api/queries.ts src/api/queries.test.tsx
git commit -m "feat: typed TanStack Query hooks for all views"
```

---

### Task 2: useLiveTransactions WebSocket hook (with resync)

**Files:**
- Create: `src/api/useLiveTransactions.ts`
- Test: `src/api/useLiveTransactions.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/api/useLiveTransactions.test.tsx`:
```tsx
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from './client';
import { tokenStore } from './tokenStore';
import { useLiveTransactions } from './useLiveTransactions';

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { FakeWS.instances.push(this); }
  emit(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

beforeEach(() => {
  FakeWS.instances = [];
  (globalThis as any).WebSocket = FakeWS as any;
  tokenStore.set({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' });
});
afterEach(() => vi.restoreAllMocks());

describe('useLiveTransactions', () => {
  it('seeds from REST then prepends newer WS events', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { items: [{ seq: 5, transaction_id: 5, bank: 'BRI', type: 'ACH', amount: 1, fraud_score: 0.1, typology: null, status: 'approved', surfaced_at: 't' }] },
    } as any);

    const { result } = renderHook(() => useLiveTransactions(10));
    await waitFor(() => expect(result.current.items.length).toBe(1));

    act(() => { FakeWS.instances[0].onopen?.(); });
    act(() => {
      FakeWS.instances[0].emit({ seq: 6, transaction_id: 6, bank: 'Mandiri', type: 'ACH', amount: 2, fraud_score: 0.9, typology: 'Fan-Out', status: 'blocked', surfaced_at: 't', sim_now: 't' });
    });
    await waitFor(() => expect(result.current.items[0].seq).toBe(6));
    // a stale seq (<= cursor) is ignored
    act(() => { FakeWS.instances[0].emit({ seq: 5, transaction_id: 5, bank: 'X', type: 'ACH', amount: 1, fraud_score: 0, typology: null, status: 'approved', surfaced_at: 't', sim_now: 't' }); });
    expect(result.current.items.filter((i) => i.seq === 5).length).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/api/useLiveTransactions.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement `src/api/useLiveTransactions.ts`**

```ts
import { useEffect, useRef, useState } from 'react';
import { api } from './client';
import { tokenStore } from './tokenStore';
import type { LiveEvent, LiveItem, LiveResponse } from './types';

const WS_BASE = (import.meta.env.VITE_WS_URL as string | undefined) ?? '/api/v1/ws/live';

export function useLiveTransactions(max = 100) {
  const [items, setItems] = useState<LiveItem[]>([]);
  const cursor = useRef(0);

  async function resync() {
    const after = cursor.current;
    const res = await api.get<LiveResponse>('/transactions/live', {
      params: after ? { after_seq: after } : { limit: max },
    });
    const fresh = res.data.items.filter((i) => i.seq > cursor.current);
    if (fresh.length) {
      cursor.current = Math.max(cursor.current, ...fresh.map((i) => i.seq));
      setItems((prev) => [...fresh.sort((a, b) => b.seq - a.seq), ...prev].slice(0, max));
    } else if (!after) {
      // first load with no after_seq returns newest-first window
      const initial = res.data.items;
      if (initial.length) cursor.current = Math.max(...initial.map((i) => i.seq));
      setItems(initial.slice(0, max));
    }
  }

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    void resync();

    function connect() {
      const token = tokenStore.getAccess();
      const url = `${WS_BASE}${WS_BASE.includes('?') ? '&' : '?'}token=${token ?? ''}`;
      ws = new WebSocket(url);
      ws.onopen = () => { void resync(); };
      ws.onmessage = (e) => {
        const ev = JSON.parse(e.data) as LiveEvent & { type?: string };
        if ((ev as { type?: string }).type === 'connected') return;
        if ((ev as { type?: string }).type === 'resync') { void resync(); return; }
        if (typeof ev.seq !== 'number' || ev.seq <= cursor.current) return;
        cursor.current = ev.seq;
        const item: LiveItem = {
          seq: ev.seq, transaction_id: ev.transaction_id, bank: ev.bank ?? '',
          type: ev.type ?? '', amount: ev.amount ?? 0, fraud_score: ev.fraud_score,
          typology: ev.typology, status: ev.status, surfaced_at: ev.surfaced_at,
        };
        setItems((prev) => [item, ...prev].slice(0, max));
      };
      ws.onclose = () => {
        if (!closed) setTimeout(connect, 1000);  // reconnect → resync on next open
      };
    }
    connect();

    return () => { closed = true; ws?.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [max]);

  return { items };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/api/useLiveTransactions.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/useLiveTransactions.ts src/api/useLiveTransactions.test.tsx
git commit -m "feat: useLiveTransactions WS hook with REST resync"
```

---

### Task 3: Wire the aggregate dashboard views

For each component below: **read the file**, delete its hardcoded mock array/constant, call the listed hook, and render its data through the **existing JSX** (keep the markup/styles). Add a loading state (use the existing `Skeleton` from `src/components/ui/skeleton.tsx`) and a simple empty/error fallback. Map fields exactly as noted.

**Files (modify):** `src/components/MetricsOverview.tsx`, `TransactionVolume.tsx`, `TransactionHeatmap.tsx`, `FraudAnalytics.tsx`, `GeographicMap.tsx`, `AlertsPanel.tsx`, and `src/App.tsx` (system-health cards).

- [ ] **Step 1: MetricsOverview** → `useMetricsOverview()`. Map: total_transactions, flagged, blocked, total_amount (format IDR), fraud_rate (→ %). Preserve the card layout.
- [ ] **Step 2: TransactionVolume** → `useVolume(range)` where `range` is the existing selector state (`'24h'|'weekly'|'monthly'|'yearly'`). Map `series[]` → the chart's `{bucket,count,flagged}`.
- [ ] **Step 3: TransactionHeatmap** → `useHeatmap()`. Map `cells` (7×24) to the grid (row = day, col = hour).
- [ ] **Step 4: FraudAnalytics** → `useFraudAnalytics()`. Map `distribution[]` `{typology,total_amount,count}` to the existing `{fraudType,totalAmount,count}` (rename keys at the boundary), and surface `detection.precision/recall/f1`.
- [ ] **Step 5: GeographicMap** → `useProvinces()`. Map `provinces[]` `{name,fraud_count,change_pct,risk_level}` to the existing `{name,fraudCount,change,riskLevel}`.
- [ ] **Step 6: AlertsPanel** → `useAlerts()` + `useAckAlert()`. Render real alerts; wire the acknowledge action to the mutation.
- [ ] **Step 7: App.tsx system health cards** → `useSystemHealth()`. Replace the hardcoded 23ms/99.94%/99.99%/1,247 cards with real `db_ok`/`redis_ok`/`events_surfaced`; for "Model Accuracy", when `model_accuracy_simulated` is true, label it "Simulated (Phase 1)" rather than a fake percentage.
- [ ] **Step 8: Verify + commit**

Run: `npm run build` (must compile) and `npm test`.
```bash
git add src/components/MetricsOverview.tsx src/components/TransactionVolume.tsx src/components/TransactionHeatmap.tsx src/components/FraudAnalytics.tsx src/components/GeographicMap.tsx src/components/AlertsPanel.tsx src/App.tsx
git commit -m "feat: wire aggregate dashboard views to backend (metrics/volume/heatmap/fraud/geo/alerts/health)"
```

---

### Task 4: Wire the live transaction monitor + detail modals

**Files (modify):** `src/components/TransactionMonitor.tsx`, `src/components/TransactionDetailsModal.tsx`, `src/components/UserProfileDetailsModal.tsx`

- [ ] **Step 1: TransactionMonitor** — remove `mockTransactions`; use `const { items } = useLiveTransactions(100)`. Render `items` through the existing table rows (fields: id→`TXN-${transaction_id}` or `transaction_id`, bank, type, amount, fraud_score, typology→suspectedFraudType, status, surfaced_at→relative time). Keep the "live" pulse + "Auto-refresh" badge (now genuinely live). The `View` action opens the detail modal with `transaction_id`.
- [ ] **Step 2: TransactionDetailsModal** — replace the random `extendedTransaction` with `useTransactionDetail(transactionId)`; render real fields (bank, amount, currency, type, fraud_score, typology, status, is_laundering, event_time). Keep the typology explanation block keyed by `typology`.
- [ ] **Step 3: UserProfileDetailsModal** — replace random profile with `useUserProfile(entityId)`; render the real `RiskProfile` (name already masked by the API, province, risk_level, risk_score, totals). Keep the layout; series the API doesn't provide yet (monthly activity / risk history) may stay as derived/placeholder ONLY IF clearly labeled, or be hidden — do not present fabricated values as real.
- [ ] **Step 4: Verify + commit**

Run: `npm run build` and `npm test`.
```bash
git add src/components/TransactionMonitor.tsx src/components/TransactionDetailsModal.tsx src/components/UserProfileDetailsModal.tsx
git commit -m "feat: wire live transaction monitor (WS) + transaction/user detail modals"
```

---

### Task 5: Wire user risk profiling + sim clock + role-gated controls

**Files (modify):** `src/components/UserRiskProfiling.tsx`, `src/components/Header.tsx`

- [ ] **Step 1: UserRiskProfiling** — replace `mockProfiles` with `useUserRisk(filterRisk)`; render the real `profiles[]` (names already masked). Keep the filter/search UI; the risk distribution chart is derived from the returned profiles.
- [ ] **Step 2: Header** — add a sim-clock indicator from `useSimState()` (show `sim_now` + running state). If `useAuth().user?.role === 'admin'`, render play/pause + speed controls wired to `useSimControl()`. Non-admins see the indicator only.
- [ ] **Step 3: Verify + commit**

Run: `npm run build` and `npm test`.
```bash
git add src/components/UserRiskProfiling.tsx src/components/Header.tsx
git commit -m "feat: wire user risk profiling + sim clock indicator + admin replay controls"
```

---

### Task 6: Env example, C4 docs, final gate

**Files:** `.env.example` (create), `docs/c4/03-component.md` + `docs/c4/04-code.md` (create)

- [ ] **Step 1: Create `.env.example`**

```bash
# Backend REST base (nginx proxies /api in deploy)
VITE_API_BASE_URL=/api/v1
# Backend WebSocket endpoint
VITE_WS_URL=/api/v1/ws/live
```

- [ ] **Step 2: Full gate** — `npm test` (all green) and `npm run build` (compiles). Fix any remaining type errors from the wiring.
- [ ] **Step 3: C4 docs** — generate `docs/c4/04-code.md` (c4-code over `src/api/`, `src/auth/`, the wired components) and `docs/c4/03-component.md` (c4-component: Data Layer, Auth, Live Feed hook, View Components) via the c4-architecture plugin. Note the frontend is the Dashboard Web container in `grafin-ai-deploy/docs/c4/02-container.md`.
- [ ] **Step 4: Commit**

```bash
git add .env.example docs/c4/
git commit -m "docs: frontend env example + C4 component/code documentation"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-22-frontend-integration-design.md`):
- TanStack Query hooks per view → Task 1. ✅
- Live monitor: REST seed + WS deltas + resync cursor → Task 2 + Task 4. ✅
- Every view component wired (metrics/volume/heatmap/monitor/detail/fraud/geo/user-risk/user-profile/alerts/system-health) → Tasks 3–5. ✅
- Role-aware UI (admin sim controls; PII already masked server-side) → Task 5. ✅
- Loading/error/empty states (skeletons) → Task 3 note, applied throughout. ✅
- Sim-clock indicator → Task 5. ✅
- `.env` (`VITE_API_BASE_URL`, `VITE_WS_URL`) → Tasks 2/6. ✅
- C4 deliverable → Task 6. ✅

**Honesty guard:** Task 4 Step 3 explicitly forbids presenting fabricated series (monthly activity / risk history the API doesn't yet expose) as real — hide or clearly label them. The system-health "Model Accuracy" card shows "Simulated (Phase 1)" rather than a fake number.

**Type consistency:** every hook returns the Plan-4A `api/types.ts` model; `useLiveTransactions` maps a `LiveEvent` (nullable bank/type/amount) into a `LiveItem` for the table; query keys are stable and parameter-scoped; mutations invalidate their list keys. The WS URL/token come from `VITE_WS_URL` + `tokenStore` (matching the backend `?token=` relay).
```
