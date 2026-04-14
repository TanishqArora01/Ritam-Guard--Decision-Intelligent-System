'use client';
import React, { useState } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { AlertCircle, ArrowRight, Loader2, Sparkles } from 'lucide-react';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { GlassPanel, PageBackdrop, RoleBadge } from '../../components/cockpit';

const ACCENTS = [
  'Fraud intelligence cockpit',
  'Real-time risk orchestration',
  'Glassmorphic control center',
];

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuth();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [username, setUsername] = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [error,    setError]    = useState('');
  const [securityMsg, setSecurityMsg] = useState('');
  const [loading,  setLoading]  = useState(false);

  const DEMO_ACCOUNTS = [
    { label: 'Admin',        username: 'admin',    role: 'ADMIN' },
    { label: 'Analyst',      username: 'analyst1', role: 'ANALYST' },
    { label: 'Ops Manager',  username: 'ops1',     role: 'OPS_MANAGER' },
    { label: 'Bank Partner', username: 'partner1', role: 'BANK_PARTNER' },
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      if (mode === 'signup') {
        await api.auth.signup({
          username,
          email,
          password,
        });
      }

      await api.auth.login(username, password);
      const me   = await api.auth.me();
      localStorage.setItem('user', JSON.stringify(me));
      setUser(me as any);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message ?? (mode === 'signup' ? 'Signup failed' : 'Login failed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-white">
      <PageBackdrop />
      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl items-center px-4 py-10 lg:px-8">
        <div className="grid w-full gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }} className="flex flex-col justify-center space-y-8">
            <div className="space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs font-medium text-cyan-100 ring-1 ring-cyan-400/10">
                <Sparkles className="h-3.5 w-3.5" /> Ritam Guard cockpit
              </div>
              <div className="max-w-2xl space-y-4">
                <h1 className="text-4xl font-semibold tracking-tight text-white md:text-6xl">
                  Fraud detection for teams that need{' '}
                  <span className="bg-gradient-to-r from-cyan-300 via-blue-300 to-violet-300 bg-clip-text text-transparent">
                    signal, not noise.
                  </span>
                </h1>
                <p className="max-w-xl text-base leading-7 text-slate-300 md:text-lg">
                  A glassmorphic, real-time interface for analysts, operations, admins, and banking partners.
                  Same backend. Higher signal. Faster decisions.
                </p>
              </div>
              <div className="flex flex-wrap gap-3 text-sm text-slate-300">
                {ACCENTS.map((item) => (
                  <span key={item} className="rounded-full border border-white/10 bg-white/5 px-3 py-2 backdrop-blur-md">
                    {item}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              {[
                ['Live feed', 'Streaming intelligence'],
                ['Role-aware', 'Adaptive layouts'],
                ['Explainable', 'Decision traceability'],
              ].map(([title, desc]) => (
                <GlassPanel key={title} className="p-4">
                  <p className="text-sm font-medium text-white">{title}</p>
                  <p className="mt-1 text-sm text-slate-400">{desc}</p>
                </GlassPanel>
              ))}
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 28 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.05 }} className="flex items-center justify-center">
            <div className="w-full max-w-lg">
              <GlassPanel className="relative overflow-hidden p-8">
                <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500" />
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Ritam Guard access</p>
                    <h2 className="mt-2 text-2xl font-semibold text-white">{mode === 'signup' ? 'Create your cockpit account' : 'Sign in to the cockpit'}</h2>
                  </div>
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 ring-1 ring-white/10">
                    <Image src="/ritam-guard-logo.png" alt="Ritam Guard" width={40} height={40} className="h-10 w-10 rounded-xl object-cover" priority />
                  </div>
                </div>

                {error && (
                  <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="mb-5 flex items-center gap-2 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {error}
                  </motion.div>
                )}

                <div className="mb-4 grid grid-cols-2 rounded-2xl border border-white/10 bg-white/5 p-1">
                  <button
                    type="button"
                    onClick={() => { setMode('login'); setError(''); }}
                    className={`rounded-xl px-3 py-2 text-sm font-medium transition ${mode === 'login' ? 'bg-cyan-400 text-slate-950' : 'text-slate-300 hover:text-white'}`}
                  >
                    Login
                  </button>
                  <button
                    type="button"
                    onClick={() => { setMode('signup'); setError(''); }}
                    className={`rounded-xl px-3 py-2 text-sm font-medium transition ${mode === 'signup' ? 'bg-cyan-400 text-slate-950' : 'text-slate-300 hover:text-white'}`}
                  >
                    Sign up
                  </button>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                  {mode === 'signup' && (
                    <>
                      <div>
                        <label className="mb-2 block text-sm font-medium text-slate-300">Email</label>
                        <input
                          type="email"
                          required
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition duration-200 focus:border-cyan-400/40 focus:bg-white/8 focus:shadow-[0_0_0_4px_rgba(34,211,238,0.08)]"
                          placeholder="Enter your email"
                        />
                      </div>
                      <div>
                        <div>
                          <label className="mb-2 block text-sm font-medium text-slate-300">Account Type</label>
                          <input
                            type="text"
                            value="USER"
                            readOnly
                            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300 outline-none"
                          />
                        </div>
                      </div>
                    </>
                  )}

                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-300">Username</label>
                    <input
                      type="text"
                      required
                      autoFocus
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition duration-200 focus:border-cyan-400/40 focus:bg-white/8 focus:shadow-[0_0_0_4px_rgba(34,211,238,0.08)]"
                      placeholder="Enter your username"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-300">Password</label>
                    <input
                      type="password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition duration-200 focus:border-cyan-400/40 focus:bg-white/8 focus:shadow-[0_0_0_4px_rgba(34,211,238,0.08)]"
                      placeholder="Enter your password"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="group inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-4 py-3 text-sm font-semibold text-slate-950 shadow-[0_12px_40px_rgba(34,211,238,0.22)] transition duration-200 hover:translate-y-[-1px] hover:shadow-[0_18px_44px_rgba(34,211,238,0.28)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />}
                    {loading ? (mode === 'signup' ? 'Creating account…' : 'Signing in…') : (mode === 'signup' ? 'Create and enter cockpit' : 'Enter cockpit')}
                  </button>
                </form>

                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="mb-3 text-xs font-medium uppercase tracking-[0.24em] text-slate-500">Role quick-fill</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {DEMO_ACCOUNTS.map((acc) => (
                      <button
                        key={acc.username}
                        onClick={() => { setUsername(acc.username); }}
                        className="rounded-2xl border border-white/10 bg-white/5 p-3 text-left transition duration-200 hover:border-cyan-400/30 hover:bg-white/8"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="block text-sm font-medium text-white">{acc.label}</span>
                          <RoleBadge role={acc.role as any} />
                        </div>
                        <span className="mt-1 block text-xs text-slate-400">{acc.username}</span>
                      </button>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-slate-500">Passwords are not embedded in UI. Use credentials issued through your secure vault.</p>
                  {securityMsg && <p className="mt-2 text-xs text-cyan-300">{securityMsg}</p>}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={async () => {
                        const res = await api.auth.beginSso('oidc');
                        setSecurityMsg(res.message);
                      }}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300"
                    >
                      SSO hook (SAML/OIDC)
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        const res = await api.auth.beginMfa();
                        setSecurityMsg(res.message);
                      }}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300"
                    >
                      MFA challenge hook
                    </button>
                  </div>
                </div>
              </GlassPanel>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
