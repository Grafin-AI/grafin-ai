import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Sidebar } from './Sidebar';

describe('Sidebar', () => {
  it('renders the base navigation items, including the regulator radar', () => {
    render(<Sidebar currentView="/dashboard" />);
    expect(screen.getByText('Monitoring')).toBeInTheDocument();
    expect(screen.getByText('Radar Regulator')).toBeInTheDocument();
    expect(screen.getByText('Profil Risiko')).toBeInTheDocument();
    expect(screen.getByText('Analitik')).toBeInTheDocument();
  });

  it('marks the current view and navigates on click', () => {
    const onNavigate = vi.fn();
    render(<Sidebar currentView="/dashboard" onNavigate={onNavigate} />);
    expect(screen.getByRole('button', { name: 'Monitoring' })).toHaveAttribute('aria-current', 'page');
    fireEvent.click(screen.getByRole('button', { name: 'Radar Regulator' }));
    expect(onNavigate).toHaveBeenCalledWith('/radar');
  });
});
