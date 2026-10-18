import { useState } from 'react';
import { useAuth } from './AuthContext';

const FIELD =
  'h-11 w-full rounded-lg border border-border-strong bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-2 focus:outline-offset-2 focus:outline-ring';

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch {
      setError('Email atau kata sandi salah');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2.5">
          <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3l11 4v8c0 7-4.7 12.4-11 14-6.3-1.6-11-7-11-14V7z" fill="none" stroke="#139EF6" strokeWidth="2" />
            <path d="M11 16l3.5 3.5L21 13" fill="none" stroke="#139EF6" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <div>
            <h1 className="text-xl font-semibold text-foreground">Garda AI — Masuk</h1>
            <p className="text-xs text-muted-foreground">Monitoring anti pencucian uang real-time</p>
          </div>
        </div>
        <label className="block space-y-1.5">
          <span className="text-sm text-text-secondary">Email</span>
          <input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={FIELD} />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm text-text-secondary">Kata sandi</span>
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={FIELD} />
        </label>
        {error && <p role="alert" className="text-sm text-blocked">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="h-11 w-full rounded-lg bg-primary text-sm font-semibold text-primary-foreground transition-colors hover:bg-[#3AAFF8] disabled:opacity-50"
        >
          {busy ? 'Memproses…' : 'Masuk'}
        </button>
      </form>
    </div>
  );
}
