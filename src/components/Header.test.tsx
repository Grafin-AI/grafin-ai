import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, email: 'admin@garda.local', role: 'admin' } }),
}));

import { Header } from './Header';

describe('Header', () => {
  it('renders the title and the user, with NO simulation element', () => {
    render(<Header />);
    expect(screen.getByText('Monitoring Transaksi')).toBeInTheDocument();
    expect(screen.getByText('LIVE')).toBeInTheDocument();
    expect(screen.getByText('admin@garda.local')).toBeInTheDocument();
    // sim controls/indicator are gone (now on the Simulation page)
    expect(screen.queryByLabelText('Simulation speed')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause|resume/i })).not.toBeInTheDocument();
  });
});
