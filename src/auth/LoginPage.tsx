import { useState } from 'react';
import { useAuth } from './AuthContext';
import grafinLogo from '../assets/grafin-logo.svg';

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
      setError('Invalid credentials');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <form onSubmit={submit} className="w-80 space-y-4 p-6 bg-white rounded-lg border">
        <img src={grafinLogo} alt="" aria-hidden="true" className="h-9 w-auto" />
        <h1 className="text-xl font-semibold text-gray-900">Grafin AI — Sign in</h1>
        <p className="-mt-2 text-xs text-gray-600">Graph-based Risk Analytics &amp; Federated Intelligence Network</p>
        <input
          type="email" required placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border rounded px-3 py-2 text-sm"
        />
        <input
          type="password" required placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded px-3 py-2 text-sm"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy}
          className="w-full bg-blue-600 text-white rounded px-3 py-2 text-sm disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
