# Shed Simulation — Frontend Plan (Phase 5 ②)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the simulation UI from `garda-ai-dashboard-web`: delete the admin Simulation page, its Sidebar nav item, the `useSimState`/`useSimControl` hooks, the `SimState` type, and the now-removed `sim_now` field on the live-event type — matching the backend Phase 5 ① contract changes.

**Architecture:** Pure removal + dangling-reference cleanup. No new UI, no new deps.

**Tech Stack:** React 18 + TypeScript, TanStack Query, Vitest.

**Spec:** `garda-ai-deploy/docs/superpowers/specs/2026-06-25-shed-simulation-design.md`

**Guardrail — do NOT remove:** the `model_accuracy_simulated` → "Simulated (Phase 1)" banner in `App.tsx` (scorer honesty, unrelated to the sim clock).

---

## Task 0: Fix the git author for this repo

**Files:** none (git config)

- [ ] **Step 1: Set the local author to match the other repos**

This repo's local author is currently the BRI corp email. Set it before any commit:
```bash
git config user.name "Thariq Iskandar Zulkarnain M P"
git config user.email "thariqiskandar9@gmail.com"
git config user.name && git config user.email
```
Expected: prints the name + `thariqiskandar9@gmail.com`.

---

## Task 1: Delete the Simulation page

**Files:**
- Delete: `src/components/SimulationControl.tsx`, `src/components/SimulationControl.test.tsx`

- [ ] **Step 1: Delete both files**

```bash
git rm src/components/SimulationControl.tsx src/components/SimulationControl.test.tsx
```

- [ ] **Step 2: Commit** (the App/queries references are removed in later tasks; this commit will leave a temporary dangling import that Task 3 resolves — so do the delete + App/queries edits together if you prefer. If committing now, note the build isn't expected green until Task 4.)

Recommended: **do not build between tasks**; run the full build/test once at Task 6. Commit:
```bash
git add -A
git commit -m "feat: delete the admin Simulation page + its test"
```

---

## Task 2: Remove the sim hooks from `api/queries.ts`

**Files:**
- Modify: `src/api/queries.ts`

- [ ] **Step 1: Delete the two hooks**

Remove `useSimState` and the entire `useSimControl` block:
```typescript
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

- [ ] **Step 2: Drop the `SimState` import**

In the `import type { ... } from './types';` block, remove `SimState` from the list. **Keep** `useMutation` / `useQueryClient` in the `@tanstack/react-query` import — they are still used by another mutation later in the file.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: remove useSimState/useSimControl query hooks"
```

---

## Task 3: Remove the sim types from `api/types.ts`

**Files:**
- Modify: `src/api/types.ts`

- [ ] **Step 1: Delete the `SimState` interface**

```typescript
export interface SimState { sim_now: string; speed: number; running: boolean; }
```

- [ ] **Step 2: Remove `sim_now` from `LiveEvent`**

In the `LiveEvent` interface, delete the line:
```typescript
  sim_now: string;
```
(Keep `surfaced_at: string;`.)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: drop SimState type and sim_now from the LiveEvent type"
```

---

## Task 4: Remove the Sidebar nav item + the App route

**Files:**
- Modify: `src/components/Sidebar.tsx`, `src/components/Sidebar.test.tsx`, `src/App.tsx`

- [ ] **Step 1: `Sidebar.tsx` — remove the admin Simulation item + now-unused imports**

Delete the `simItem` object and the admin insertion, so `items` is just `navigationItems`:
```typescript
  const { user } = useAuth();
  const simItem: NavItem = {
    title: 'Simulation',
    icon: <Activity className="w-4 h-4" />,
    href: '/simulation',
  };
  const items: NavItem[] =
    user?.role === 'admin'
      ? [...navigationItems.slice(0, 2), simItem, ...navigationItems.slice(2)]
      : navigationItems;
```
becomes:
```typescript
  const items: NavItem[] = navigationItems;
```
Then remove the now-unused imports: `Activity` (from the lucide-react import list) and `useAuth` (`import { useAuth } from '../auth/AuthContext';`) — both were only used by the Simulation item. (Verify `user`/`useAuth`/`Activity` aren't referenced elsewhere in the file before removing.)

- [ ] **Step 2: `Sidebar.test.tsx` — remove the two Simulation-item tests**

Delete:
```typescript
  it('shows the Simulation item for admins', () => {
    ...
    expect(screen.getByText('Simulation')).toBeInTheDocument();
  });

  it('hides the Simulation item for analysts', () => {
    ...
    expect(screen.queryByText('Simulation')).not.toBeInTheDocument();
  });
```
Keep any other Sidebar tests. If the hoisted `role` mock (`h`) becomes unused after removing these, remove it too (avoid an unused-var lint error).

- [ ] **Step 3: `App.tsx` — remove the import + the route branch**

Delete the import:
```typescript
import { SimulationControl } from './components/SimulationControl';
```
And the route branch:
```typescript
        ) : currentView === '/simulation' ? (
          <SimulationControl />
```
so the conditional chain goes straight from the `/user-risk-profiling` branch to the placeholder `else`. **Keep** the `model_accuracy_simulated` banner untouched.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: remove the Simulation nav item and /simulation route"
```

---

## Task 5: Drop `sim_now` from the live-hook test fixtures

**Files:**
- Modify: `src/api/useLiveTransactions.test.tsx`

- [ ] **Step 1: Remove `sim_now` from the two emitted events**

In both `emit({...})` fixtures, remove `, sim_now: 't'` (the hook itself never referenced `sim_now`; the type no longer has it). Keep `surfaced_at: 't'`.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "test: drop sim_now from live-transaction test fixtures"
```

---

## Task 6: Full verification

**Files:** none

- [ ] **Step 1: Type-check**

Run: `npx tsc --noEmit`
Expected: no errors (no dangling `SimState`/`sim_now`/`SimulationControl`/`useSimState`/`useSimControl` references).

- [ ] **Step 2: Tests**

Run: `npm test`
Expected: green (the deleted components' tests are gone; `Header.test.tsx` still asserts the header has no sim element and stays green).

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: compiles cleanly.

- [ ] **Step 4: Confirm no sim residue**

Run: `grep -rniE "useSimState|useSimControl|SimulationControl|sim_now|interface SimState|/simulation|/sim/" src || echo "clean"`
Expected: `clean` (the "Simulated (Phase 1)" / `model_accuracy_simulated` strings are a different match and are intentionally kept — they will not appear in this grep).

- [ ] **Step 5: Commit any final fixups**

```bash
git add -A
git commit -m "chore: frontend sim-shed cleanup" || echo "nothing to commit"
```

---

## Definition of Done

- `npx tsc --noEmit` clean; `npm test` green; `npm run build` compiles.
- Simulation page, Sidebar item, `/simulation` route, `useSimState`/`useSimControl`, the `SimState` type, and `sim_now` on `LiveEvent` are all gone.
- `model_accuracy_simulated` / "Simulated (Phase 1)" banner PRESERVED; `Header.test` still green.
- All commits authored as Thariq Iskandar Zulkarnain M P (gmail) with the `Co-Authored-By: Claude` trailer.
```
