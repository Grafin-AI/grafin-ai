import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { LoginPage } from './LoginPage';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth();
  if (!ready) return null;          // brief boot while restoring session
  if (!user) return <LoginPage />;
  return <>{children}</>;
}
