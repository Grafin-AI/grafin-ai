import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const health = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));

vi.mock('./api/queries', () => ({
  useSystemHealth: () => ({ data: health.data, isLoading: false }),
}));

import { SystemHealthCards } from './App';

const base = { db_ok: true, redis_ok: true, events_surfaced: 10 };

describe('SystemHealthCards model card', () => {
  it('shows the configured model name', () => {
    health.data = { ...base, model_accuracy_simulated: false, model_name: 'grafin-gnn-v1' };
    render(<SystemHealthCards />);
    expect(screen.getByText('Model: grafin-gnn-v1')).toBeInTheDocument();
    expect(screen.queryByText('Simulated (Phase 1)')).not.toBeInTheDocument();
    expect(screen.queryByText(/Label-replay simulation/)).not.toBeInTheDocument();
  });

  it('falls back to the simulation label without a model name', () => {
    health.data = { ...base, model_accuracy_simulated: true, model_name: null };
    render(<SystemHealthCards />);
    expect(screen.getByText('Simulated (Phase 1)')).toBeInTheDocument();
    expect(screen.getByText(/Label-replay simulation active/)).toBeInTheDocument();
    expect(screen.queryByText(/^Model:/)).not.toBeInTheDocument();
  });
});
