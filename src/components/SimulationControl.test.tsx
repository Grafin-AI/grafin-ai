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
