import { render, screen } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { AuthProvider } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import { queryClient } from './queryClient';

describe('app shell', () => {
  it('shows the login page when unauthenticated', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RequireAuth>
            <div>secret dashboard</div>
          </RequireAuth>
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Grafin AI — Sign in')).toBeInTheDocument();
    expect(screen.queryByText('secret dashboard')).not.toBeInTheDocument();
  });
});
