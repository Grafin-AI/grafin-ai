import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';
import { api } from '../api/client';
import { tokenStore } from '../api/tokenStore';

function Probe() {
  const { user, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="role">{user?.role ?? 'anon'}</span>
      <button onClick={() => login('a@example.com', 'pw')}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    tokenStore.clear();
    vi.restoreAllMocks();
  });

  it('logs in, exposes the user, and logs out', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({
      data: { access_token: 'a', refresh_token: 'r', token_type: 'bearer' },
    } as any);
    vi.spyOn(api, 'get').mockResolvedValue({
      data: { id: 1, email: 'a@example.com', role: 'analyst' },
    } as any);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByTestId('role').textContent).toBe('anon');

    await userEvent.click(screen.getByText('login'));
    await waitFor(() => expect(screen.getByTestId('role').textContent).toBe('analyst'));
    expect(tokenStore.getAccess()).toBe('a');

    await userEvent.click(screen.getByText('logout'));
    await waitFor(() => expect(screen.getByTestId('role').textContent).toBe('anon'));
    expect(tokenStore.getAccess()).toBeNull();
  });
});
