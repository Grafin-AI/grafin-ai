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
