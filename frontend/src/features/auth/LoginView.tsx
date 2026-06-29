import { RefreshCw } from 'lucide-react';
import { type FormEvent, useState } from 'react';

export function LoginView({ onLogin }: { onLogin: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onLogin(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <header className="flex h-14 items-center border-b border-slate-800 bg-slate-950 px-5 text-white">
        <div className="flex items-center gap-2 text-sm font-bold tracking-wide">
          <RefreshCw size={18} aria-hidden="true" />
          CloseLoop CRM
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <form className="panel w-full max-w-sm p-6" onSubmit={submit}>
          <h1 className="text-lg font-bold text-slate-950">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Access your CRM workspace.</p>
          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="field-label">Email</span>
              <input className="field-input" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" required />
            </label>
            <label className="block">
              <span className="field-label">Password</span>
              <input className="field-input" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required />
            </label>
          </div>
          {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
          <button className="primary-button mt-5 w-full justify-center" disabled={busy} type="submit">
            {busy ? 'Signing in' : 'Sign in'}
          </button>
          <div className="mt-4 text-center text-xs text-slate-400">v2.1 React</div>
        </form>
      </main>
    </div>
  );
}
