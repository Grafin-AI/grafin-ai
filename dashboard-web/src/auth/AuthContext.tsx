import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from 'react';
import type { ReactNode } from 'react';
import { api, onAuthFailure } from '../api/client';
import { tokenStore } from '../api/tokenStore';
import type { Me, TokenResponse } from '../api/types';

interface AuthValue {
  user: Me | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthCtx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const loadMe = useCallback(async () => {
    const res = await api.get<Me>('/auth/me');
    setUser(res.data);
  }, []);

  const logout = useCallback(() => {
    const refresh = tokenStore.getRefresh();
    if (refresh) void api.post('/auth/logout', { refresh_token: refresh }).catch(() => {});
    tokenStore.clear();
    setUser(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<TokenResponse>('/auth/login', { email, password });
    tokenStore.set(res.data);
    await loadMe();
  }, [loadMe]);

  useEffect(() => {
    onAuthFailure(() => setUser(null));
    (async () => {
      if (tokenStore.getAccess()) {
        try { await loadMe(); } catch { tokenStore.clear(); }
      }
      setReady(true);
    })();
  }, [loadMe]);

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
