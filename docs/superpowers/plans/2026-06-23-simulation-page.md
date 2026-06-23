# Simulation Control Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the simulation clock + replay controls out of the dashboard `Header` into a dedicated, admin-only **Simulation** page, leaving the dashboard a clean monitoring UI.

**Architecture:** Frontend-only, no backend change. The app navigates via `App.tsx`'s `currentView` state (no router), so the new page is a new `currentView` value (`/simulation`) reached from an admin-only Sidebar item. A new `SimulationControl` component reuses the existing `useSimState` / `useSimControl` / `useSystemHealth` hooks. The `Header` loses its sim block entirely.

**Tech Stack:** React 18 + TS, @tanstack/react-query (existing hooks), Vitest + Testing Library.

---

## File structure

```
src/
├── components/
│   ├── SimulationControl.tsx     # CREATE: the Simulation page (clock + admin controls + status)
│   ├── SimulationControl.test.tsx# CREATE
│   ├── Sidebar.tsx               # MODIFY: admin-only "Simulation" nav item
│   ├── Sidebar.test.tsx          # CREATE
│   ├── Header.tsx                # MODIFY: remove the sim block + sim hooks/imports
│   └── Header.test.tsx           # CREATE: assert no sim element
└── App.tsx                       # MODIFY: render SimulationControl on '/simulation'
```

---

### Task 1: SimulationControl page component

**Files:**
- Create: `src/components/SimulationControl.tsx`
- Test: `src/components/SimulationControl.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/SimulationControl.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  mutate: vi.fn(),
  simState: { sim_now: '2025-09-01T15:44:00Z', speed: 20, running: true } as
    { sim_now: string; speed: number; running: boolean } | null,
  role: 'admin' as string,
  health: { events_surfaced: 351979 } as { events_surfaced: number } | undefined,
}));

vi.mock('../api/queries', () => ({
  useSimState: () => ({ data: h.simState, isLoading: false }),
  useSimControl: () => ({ mutate: h.mutate, isPending: false }),
  useSystemHealth: () => ({ data: h.health }),
}));
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'a@b.c', role: h.role } }),
}));

import { SimulationControl } from './SimulationControl';

describe('SimulationControl', () => {
  beforeEach(() => {
    h.mutate.mockClear();
    h.role = 'admin';
    h.simState = { sim_now: '2025-09-01T15:44:00Z', speed: 20, running: true };
    h.health = { events_surfaced: 351979 };
  });

  it('admin sees clock, status, and working controls', async () => {
    render(<SimulationControl />);
    expect(screen.getByTestId('sim-now').textContent).toMatch(/Sep|2025/);
    expect(screen.getByTestId('events-surfaced').textContent).toMatch(/351/);

    const speed = screen.getByLabelText('Simulation speed') as HTMLSelectElement;
    expect(speed.value).toBe('20');
    await userEvent.selectOptions(speed, '5');
    expect(h.mutate).toHaveBeenCalledWith({ speed: 5 });

    await userEvent.click(screen.getByRole('button', { name: /pause/i }));
    expect(h.mutate).toHaveBeenCalledWith({ running: false });
  });

  it('non-admin sees the clock/status but no controls', () => {
    h.role = 'analyst';
    render(<SimulationControl />);
    expect(screen.getByTestId('sim-now')).toBeInTheDocument();
    expect(screen.queryByLabelText('Simulation speed')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause|resume/i })).not.toBeInTheDocument();
  });

  it('shows a fallback when sim state is unavailable', () => {
    h.simState = null;
    render(<SimulationControl />);
    expect(screen.getByText('Simulation unavailable')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/SimulationControl.test.tsx`
Expected: FAIL (cannot find `./SimulationControl`).

- [ ] **Step 3: Implement `src/components/SimulationControl.tsx`**

```tsx
import { Clock, Pause, Play } from 'lucide-react';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import { useSimControl, useSimState, useSystemHealth } from '../api/queries';
import { useAuth } from '../auth/AuthContext';

const SPEED_OPTIONS = [1, 2, 5, 10, 20] as const;

function formatSimNow(simNow: string): string {
  try {
    return new Date(simNow).toLocaleString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return simNow;
  }
}

export function SimulationControl() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data: simState, isLoading } = useSimState();
  const { data: health } = useSystemHealth();
  const simControl = useSimControl();

  const toggleRunning = () => {
    if (simState) simControl.mutate({ running: !simState.running });
  };
  const changeSpeed = (speed: number) => simControl.mutate({ speed });

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Simulation Control</h2>
        <p className="text-sm text-gray-500 mt-1">
          Replay clock for the demo dataset{isAdmin ? '' : ' (read-only)'}
        </p>
      </div>

      <div className="bg-white rounded-lg border p-6 space-y-6">
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : simState ? (
          <>
            <div className="flex items-center gap-3">
              <Clock className="w-6 h-6 text-gray-400" />
              <div>
                <div className="text-2xl font-semibold text-gray-900" data-testid="sim-now">
                  {formatSimNow(simState.sim_now)}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      simState.running ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
                    }`}
                  />
                  <span className="text-sm text-gray-600">
                    {simState.running ? `Running · ${simState.speed}x` : 'Paused'}
                  </span>
                </div>
              </div>
            </div>

            {isAdmin && (
              <div className="flex items-center gap-3 border-t pt-4">
                <Button
                  onClick={toggleRunning}
                  disabled={simControl.isPending}
                  variant="outline"
                  className="gap-2"
                >
                  {simState.running ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  {simState.running ? 'Pause' : 'Resume'}
                </Button>
                <label htmlFor="sim-speed" className="text-sm text-gray-600">Speed</label>
                <select
                  id="sim-speed"
                  aria-label="Simulation speed"
                  className="text-sm border border-gray-200 rounded px-2 py-1 bg-white text-gray-700 cursor-pointer"
                  value={simState.speed}
                  onChange={(e) => changeSpeed(Number(e.target.value))}
                  disabled={simControl.isPending}
                >
                  {SPEED_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}x</option>
                  ))}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 border-t pt-4">
              <div>
                <p className="text-xs text-gray-500">Events surfaced</p>
                <p className="text-lg font-medium text-gray-900" data-testid="events-surfaced">
                  {health ? health.events_surfaced.toLocaleString('id-ID') : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">State</p>
                <p className="text-lg font-medium text-gray-900">
                  {simState.running ? 'Running' : 'Paused'}
                </p>
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-gray-400">Simulation unavailable</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/components/SimulationControl.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/SimulationControl.tsx src/components/SimulationControl.test.tsx
git commit -m "feat: SimulationControl page (clock + admin controls + status)"
```

---

### Task 2: Admin-only Simulation item in the Sidebar

**Files:**
- Modify: `src/components/Sidebar.tsx`
- Test: `src/components/Sidebar.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/Sidebar.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({ role: 'admin' as string }));
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'a@b.c', role: h.role } }),
}));

import { Sidebar } from './Sidebar';

describe('Sidebar', () => {
  beforeEach(() => { h.role = 'admin'; });

  it('shows the Simulation item for admins', () => {
    render(<Sidebar currentView="/dashboard" />);
    expect(screen.getByText('Simulation')).toBeInTheDocument();
  });

  it('hides the Simulation item for analysts', () => {
    h.role = 'analyst';
    render(<Sidebar currentView="/dashboard" />);
    expect(screen.queryByText('Simulation')).not.toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/Sidebar.test.tsx`
Expected: FAIL (no "Simulation" item yet).

Note: `Sidebar` imports a `figma:asset/...` logo. The Vite `resolve.alias` in `vite.config.ts` maps it to a real PNG, which Vitest resolves to a URL string — the render works. If the asset import errors under jsdom, add `'\\.png$': ...` handling, but it should resolve via the existing alias.

- [ ] **Step 3: Add the admin-only item**

In `src/components/Sidebar.tsx`:

(a) Add the import (with the other imports):
```tsx
import { useAuth } from '../auth/AuthContext';
```

(b) `Activity` is already imported from `lucide-react` (keep it). At the **top of the `Sidebar` function body** (before the `return`), compute the role-aware item list:
```tsx
  const { user } = useAuth();
  const simItem: NavItem = {
    title: 'Simulation',
    icon: <Activity className="w-4 h-4" />,
    href: '/simulation',
  };
  const items: NavItem[] =
    user?.role === 'admin'
      ? [navigationItems[0], navigationItems[1], simItem, navigationItems[2]]
      : navigationItems;
```

(c) In the nav map, iterate `items` instead of `navigationItems`:
```tsx
          {items.map((item, index) => (
            <NavItemComponent
              key={index}
              item={item}
              isActive={currentView === item.href}
              onNavigate={onNavigate}
              currentView={currentView}
            />
          ))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/components/Sidebar.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/components/Sidebar.tsx src/components/Sidebar.test.tsx
git commit -m "feat: admin-only Simulation nav item in sidebar"
```

---

### Task 3: Render the Simulation page in App

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Add the import**

In `src/App.tsx`, with the other component imports:
```tsx
import { SimulationControl } from './components/SimulationControl';
```

- [ ] **Step 2: Add the view branch**

In `App.tsx`, the main content currently branches on `currentView` (`/dashboard` → dashboard sections; `/user-risk-profiling` → `<UserRiskProfiling />`; else placeholder). Add a `/simulation` branch **before** the final placeholder, e.g.:
```tsx
        ) : currentView === '/user-risk-profiling' ? (
          <UserRiskProfiling />
        ) : currentView === '/simulation' ? (
          <SimulationControl />
        ) : (
```
(Insert the `/simulation` branch immediately after the existing `/user-risk-profiling` branch, keeping the existing placeholder as the final `else`.)

- [ ] **Step 3: Verify the build compiles**

Run: `npm run build`
Expected: compiles with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat: route /simulation to the SimulationControl page"
```

---

### Task 4: Remove the sim block from the Header

**Files:**
- Modify: `src/components/Header.tsx`
- Test: `src/components/Header.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/components/Header.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'admin@garda.local', role: 'admin' } }),
}));

import { Header } from './Header';

describe('Header', () => {
  it('renders the title and the user, with NO simulation element', () => {
    render(<Header />);
    expect(screen.getByText('Fraud Detection Dashboard')).toBeInTheDocument();
    expect(screen.getByText('admin@garda.local')).toBeInTheDocument();
    // sim controls/indicator are gone (now on the Simulation page)
    expect(screen.queryByLabelText('Simulation speed')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause|resume/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/Header.test.tsx`
Expected: FAIL — the header still renders the simulation speed control / pause button.

- [ ] **Step 3: Remove the sim block + its hooks/imports**

Edit `src/components/Header.tsx`:

(a) Imports — change the lucide line to drop `Play, Pause, Clock`:
```tsx
import { Bell, Settings, User, Search, Menu } from 'lucide-react';
```
Remove the now-unused imports entirely: the `Skeleton` import line, and the `useSimState, useSimControl` import line. Keep `Button`, `Input`, `Badge`, and `useAuth`.

(b) Remove the module-level `const SPEED_OPTIONS = [1, 2, 5, 10, 20] as const;`.

(c) Inside the component, remove the sim state/handlers:
```tsx
  const { data: simState, isLoading: simLoading } = useSimState();
  const simControl = useSimControl();
  const handleToggleRunning = () => { ... };
  const handleSpeedChange = (speed: number) => { ... };
  const formatSimNow = (simNow: string) => { ... };
```
Keep only:
```tsx
  const { user } = useAuth();
```
(`isAdmin` was only used by the sim controls — remove it too.)

(d) Delete the entire **Sim Clock Indicator** `div` block — the `{/* Sim Clock Indicator */}` `<div className="flex items-center gap-2 border ...">...</div>` (everything from that comment through its closing `</div>`), so the right-hand group starts directly with the search `<div className="relative">`.

The resulting Header right-side group is: search input → bell → settings → user panel. No sim element.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/components/Header.test.tsx` then `npm run build`
Expected: Header test PASS; build compiles (no unused-import / TS errors).

- [ ] **Step 5: Commit**

```bash
git add src/components/Header.tsx src/components/Header.test.tsx
git commit -m "refactor: remove simulation bar from Header (moved to Simulation page)"
```

---

### Task 5: Full gate + docs refresh

**Files:**
- Modify: `docs/c4/03-component.md`, `docs/c4/04-code.md`
- Modify: `docs/superpowers/specs/2026-06-22-frontend-integration-design.md`
- Modify: `../garda-ai-deploy/README.md`

- [ ] **Step 1: Full suite + build**

Run: `npm test` then `npm run build`
Expected: all tests green (existing 11 + new: 3 SimulationControl + 2 Sidebar + 1 Header), build compiles.

- [ ] **Step 2: Update the frontend C4 docs**

Use the c4-architecture `c4-code` agent over `src/` and `c4-component` agent to reflect: `Header` no longer contains the sim clock/controls; new `SimulationControl` component (clock + admin play/pause/speed + read-only events-surfaced/running status, reusing `useSimState`/`useSimControl`/`useSystemHealth`); `Sidebar` gains an admin-only "Simulation" item routing to `/simulation` via `App.tsx`. Add a dated note (2026-06-23).

- [ ] **Step 3: Update the frontend-integration spec**

In `docs/superpowers/specs/2026-06-22-frontend-integration-design.md`, update the Header/sim-clock references: the sim-clock indicator and admin replay controls now live on a dedicated admin-only **Simulation** page (`SimulationControl`), not in the Header; the dashboard header is clean.

- [ ] **Step 4: Update the deploy README**

In `../garda-ai-deploy/README.md` (the "Simulation clock" section), change "Control it from the header (admin only)" to "Control it from the **Simulation** page (admin-only sidebar item), or the API".

- [ ] **Step 5: Commit**

```bash
git add docs/c4/ docs/superpowers/specs/2026-06-22-frontend-integration-design.md
git commit -m "docs: simulation controls moved to dedicated page (C4 + frontend spec)"
# deploy repo is separate — commit there too:
cd ../garda-ai-deploy && git add README.md && git commit -m "docs: control the simulation from the Simulation page, not the header" && cd -
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-23-simulation-page-design.md`):
- Req 1 clean dashboard / Header sim removed → Task 4. ✅
- Req 2 dedicated `SimulationControl` at `/simulation` → Tasks 1, 3. ✅
- Req 3 admin-only Sidebar item → Task 2. ✅
- Req 4 page contents (clock, running indicator, admin play/pause + speed, events-surfaced + running status) → Task 1. ✅
- Req 5 non-admin read-only (no controls) → Task 1 (test `non-admin sees the clock/status but no controls`). ✅
- Req 6 loading skeleton + "Simulation unavailable" fallback → Task 1 (test `shows a fallback...`). ✅
- Testing (page admin/non-admin, cleaned Header, Sidebar item) → Tasks 1, 2, 4. ✅
- Docs (C4, frontend-integration spec, deploy README) → Task 5. ✅
- No backend change, no router migration → honored (uses `currentView`, existing hooks). ✅

**Placeholder scan:** none — every step has complete code or an exact edit description. The Header edit (Task 4) describes the precise lines/blocks to remove (the file is short and read in full during implementation).

**Type consistency:** `SimulationControl` (no props) is imported and rendered identically in the test and `App.tsx`. The mocked hook shapes (`useSimState → {data:{sim_now,speed,running}}`, `useSimControl → {mutate, isPending}`, `useSystemHealth → {data:{events_surfaced}}`, `useAuth → {user:{role}}`) match the real `src/api/queries.ts` / `src/auth/AuthContext.tsx` signatures. `SPEED_OPTIONS` and `formatSimNow` are defined inside `SimulationControl.tsx` (moved from the Header) and used only there. The Sidebar `NavItem` shape (`title`, `icon`, `href`) matches the existing interface; the new `simItem` conforms.
