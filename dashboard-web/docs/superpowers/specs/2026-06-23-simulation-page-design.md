# Simulation Control Page — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming)
**Repo:** `garda-ai-dashboard-web`

## Purpose

The simulation clock + replay controls currently live inside the dashboard's fixed
`Header`, where they visually compete with the analyst monitoring UI. The simulation is a
demo/ops construct (in production the feed would just be live), so it does not belong in the
analyst's "real" fraud dashboard. This change **removes the simulation bar from the dashboard
entirely** and relocates it to a **dedicated, admin-only Simulation page**, leaving the
dashboard as a clean monitoring UI.

## Scope

Frontend-only. No backend or API change — reuses the existing `useSimState`, `useSimControl`,
and `useSystemHealth` hooks. The app uses `App.tsx`'s `currentView` state for navigation (no
router), so the new page is a new `currentView` value, not a route.

## Requirements

1. **Clean dashboard:** the sim-clock + controls block is removed from `Header.tsx` completely
   (including its `useSimState`/`useSimControl` imports and handlers). The header retains only:
   title, search, alerts, settings, and the user panel. No simulation element appears on the
   Dashboard or any other analyst view.
2. **Dedicated Simulation page:** a new `SimulationControl` component rendered when
   `currentView === '/simulation'`.
3. **Admin-only navigation:** a "Simulation" item in the `Sidebar`, shown **only** when
   `useAuth().user?.role === 'admin'`. Analysts do not see it.
4. **Page contents:**
   - Current simulation time (formatted, `id-ID` locale) + a running/paused indicator (the
     green pulsing dot when running, grey when paused).
   - **Admin controls:** play/pause toggle and a speed selector (1, 2, 5, 10, 20×), wired to
     `useSimControl().mutate(...)`.
   - **Read-only status:** "events surfaced" (from `useSystemHealth().events_surfaced`) and the
     running state — making the page double as a lightweight replay-status panel.
5. **Non-admin direct access:** if a non-admin reaches `/simulation` directly (e.g. via a
   stale link), the page renders the read-only clock + status **without** the controls. This
   mirrors today's gating (controls already check `isAdmin`).
6. **Loading/empty states:** while `useSimState` loads, show a skeleton; if sim state is
   unavailable, show a "Simulation unavailable" message (same fallback the header used).

## Components & responsibilities

| Unit | Responsibility | Depends on |
|---|---|---|
| `components/SimulationControl.tsx` (new) | Render the Simulation page: clock, running indicator, admin play/pause + speed, read-only status. | `useSimState`, `useSimControl`, `useSystemHealth`, `useAuth`, existing `ui/*` |
| `components/Header.tsx` (modify) | Remove the sim block + sim hooks/handlers. | — (now only auth for the user panel) |
| `components/Sidebar.tsx` (modify) | Add an admin-only "Simulation" nav item. | `useAuth` for the role gate |
| `App.tsx` (modify) | Render `SimulationControl` when `currentView === '/simulation'`. | `SimulationControl` |

The `SIM_NOW` formatting helper and `SPEED_OPTIONS` move from `Header.tsx` into
`SimulationControl.tsx` (they are no longer needed in the header).

## Data flow

Unchanged from today: `SimulationControl` reads `GET /api/v1/sim/state` (polled 5s via
`useSimState`) and `GET /api/v1/system/health` (polled 4s via `useSystemHealth`); admin actions
POST `/api/v1/sim/control` via `useSimControl`, which invalidates the `['sim','state']` query.
The backend already enforces admin-only on `/sim/control`, so client-side gating is UX-only
(defense in depth remains server-side).

## Error handling

- Sim state loading → skeleton; unavailable → "Simulation unavailable" text.
- `useSimControl` pending → disable the play/pause + speed inputs (as the header did).
- A non-admin POSTing `/sim/control` would be rejected server-side (403); the UI simply hides
  the controls for non-admins so this isn't reachable from the page.

## Testing

Vitest + Testing Library:
- `SimulationControl` (admin): renders the formatted sim time, the running indicator, the
  play/pause button, and the speed selector; changing speed calls `useSimControl.mutate` with
  `{ speed }`; toggling calls it with `{ running: !running }`.
- `SimulationControl` (non-admin): renders the clock + status but **no** controls.
- `Header`: no longer renders any simulation element (assert the clock/speed controls are
  absent).
- `Sidebar`: the "Simulation" item shows for admin, is absent for analyst.

Query hooks are mocked (`vi.spyOn(api, ...)` / mocked hook returns) as in the existing tests.

## Implementation notes

- Implement with the `frontend-developer` agent and the `tailwind-design-system` skill so the
  page matches the existing card/spacing/typography conventions.
- Keep `SimulationControl` a single focused file; it has one clear purpose (sim status +
  control) and depends only on the listed hooks.

## Docs to update (after implementation)

- Frontend C4 `docs/c4/03-component.md` + `04-code.md`: Header loses the sim block; new
  `SimulationControl` component; Sidebar gains the admin-only item.
- `docs/superpowers/specs/2026-06-22-frontend-integration-design.md`: the sim-clock indicator +
  admin controls move from the Header to the dedicated Simulation page.
- `garda-ai-deploy/README.md`: "control the simulation from the **Simulation page** (admin)",
  not the header.

## Out of scope (YAGNI)

- No router migration (the app stays on `currentView` navigation).
- No replay progress bar / sim-time scrubber (would need a new API exposing the data's
  min/max `event_time`); the read-only "events surfaced" count is sufficient status for now.
- No backend changes.
