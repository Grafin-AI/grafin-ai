import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sidebar } from './Sidebar';

describe('Sidebar', () => {
  it('renders the base navigation items', () => {
    render(<Sidebar currentView="/dashboard" />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('User Risk Profiling')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });
});
