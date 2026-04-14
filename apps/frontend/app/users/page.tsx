'use client';
import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Users, Key, Check, Shield, Sparkles } from 'lucide-react';
import { api } from '../../lib/api';
import { GlassPanel, PageBackdrop, PermissionMatrix, RoleBadge, SectionHeader, StatusPill } from '../../components/cockpit';

const ROLE_OPTIONS = ['ANALYST', 'OPS_MANAGER', 'ADMIN', 'BANK_PARTNER'];
const ROLE_COLORS: Record<string, string> = {
  ADMIN:        'bg-red-100 text-red-700',
  OPS_MANAGER:  'bg-purple-100 text-purple-700',
  ANALYST:      'bg-blue-100 text-blue-700',
  BANK_PARTNER: 'bg-green-100 text-green-700',
};

export default function UsersPage() {
  const [tab,       setTab]       = useState<'users' | 'keys'>('users');
  const [users,     setUsers]     = useState<any[]>([]);
  const [apiKeys,   setApiKeys]   = useState<any[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [showForm,  setShowForm]  = useState(false);
  const [newKey,    setNewKey]    = useState<string | null>(null);

  // New user form
  const [username, setUsername] = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [role,     setRole]     = useState('ANALYST');
  const [orgId,    setOrgId]    = useState('');
  const [saving,   setSaving]   = useState(false);

  // New key
  const [keyName,  setKeyName]  = useState('');

  useEffect(() => {
    Promise.all([api.users.list(), api.apiKeys.list()])
      .then(([u, k]) => { setUsers(u); setApiKeys(k); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true);
    try {
      const u = await api.users.create({ username, email, password, role, org_id: orgId || null });
      setUsers(prev => [u, ...prev]);
      setShowForm(false); setUsername(''); setEmail(''); setPassword(''); setOrgId('');
    } catch (err: any) { alert(err.message); }
    finally { setSaving(false); }
  };

  const toggleActive = async (user: any) => {
    const updated = await api.users.update(user.id, { is_active: !user.is_active });
    setUsers(prev => prev.map(u => u.id === updated.id ? { ...u, is_active: updated.is_active } : u));
  };

  const createApiKey = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true);
    try {
      const k = await api.apiKeys.create(keyName);
      setNewKey(k.key);
      setApiKeys(prev => [k, ...prev]);
      setKeyName('');
    } catch (err: any) { alert(err.message); }
    finally { setSaving(false); }
  };

  const revokeKey = async (id: string) => {
    await api.apiKeys.revoke(id);
    setApiKeys(prev => prev.map(k => k.id === id ? { ...k, is_active: false } : k));
  };

  if (loading) {
    return (
      <div className="relative min-h-full px-4 py-6 lg:px-6">
        <PageBackdrop />
        <div className="relative z-10 mx-auto max-w-7xl grid gap-4 lg:grid-cols-2">
          <GlassPanel className="h-80 animate-shimmer" />
          <GlassPanel className="h-80 animate-shimmer" />
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Admin control room</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white flex items-center gap-3"><Users className="h-6 w-6 text-cyan-300" /> User management</h1>
              <p className="mt-2 text-sm text-slate-400">Role badges, activity glow, and a permission matrix for system visibility.</p>
            </div>
            <StatusPill label="ADMIN only" tone="rose" />
          </div>
        </GlassPanel>

        <PermissionMatrix rows={[
          { role: 'ADMIN', dashboard: 1, review: 1, analytics: 1, users: 1 },
          { role: 'OPS_MANAGER', dashboard: 1, review: 1, analytics: 1, users: 0 },
          { role: 'ANALYST', dashboard: 1, review: 1, analytics: 1, users: 0 },
          { role: 'BANK_PARTNER', dashboard: 1, review: 0, analytics: 1, users: 0 },
        ]} />

        {/* Tabs */}
        <div className="flex w-fit gap-1 rounded-2xl border border-white/10 bg-white/5 p-1 ring-1 ring-white/5">
          {(['users', 'keys'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`rounded-2xl px-4 py-2 text-sm font-medium transition ${tab === t ? 'bg-cyan-400 text-slate-950 shadow-[0_8px_24px_rgba(34,211,238,0.18)]' : 'text-slate-300 hover:text-white'}`}>
              {t === 'users' ? `Users (${users.length})` : `API Keys (${apiKeys.filter(k => k.is_active).length})`}
            </button>
          ))}
        </div>

      {tab === 'users' && (
        <>
          <button onClick={() => setShowForm(f => !f)}
            className="flex items-center gap-1.5 rounded-2xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:translate-y-[-1px]">
            <Plus className="w-4 h-4" /> Add User
          </button>

          {showForm && (
            <form onSubmit={createUser} className="space-y-4 rounded-3xl border border-white/10 bg-white/5 p-5">
              <SectionHeader title="New user" subtitle="Create access without changing the API contract" />
              <div className="grid sm:grid-cols-2 gap-4">
                {[
                  ['Username', username, setUsername, 'text', 'analyst2'],
                  ['Email',    email,    setEmail,    'email','analyst2@example.com'],
                  ['Password', password, setPassword, 'password', '••••••••'],
                  ['Org ID (for Bank Partners)', orgId, setOrgId, 'text', 'bank-xyz'],
                ].map(([label, val, setter, type, ph]: any) => (
                  <div key={label as string}>
                    <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">{label}</label>
                    <input type={type} value={val} onChange={e => setter(e.target.value)}
                      placeholder={ph} required={label !== 'Org ID (for Bank Partners)'}
                      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
                  </div>
                ))}
                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Role</label>
                  <select value={role} onChange={e => setRole(e.target.value)}
                    className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40">
                    {ROLE_OPTIONS.map(r => <option key={r}>{r}</option>)}
                  </select>
                </div>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={saving}
                  className="rounded-2xl bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-60">
                  {saving ? 'Creating…' : 'Create User'}
                </button>
                <button type="button" onClick={() => setShowForm(false)}
                  className="rounded-2xl bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-200 ring-1 ring-white/10 hover:bg-white/8">
                  Cancel
                </button>
              </div>
            </form>
          )}

          <div className="grid gap-3 lg:grid-cols-2">
            {users.map((u: any) => (
              <GlassPanel key={u.id} className="p-4 transition hover:border-white/20">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <div className={`h-12 w-12 rounded-2xl ring-1 ring-white/10 ${u.is_active ? 'bg-emerald-400/20 shadow-[0_0_24px_rgba(52,211,153,0.18)]' : 'bg-slate-500/20'}`} />
                      <div className={`absolute -right-1 -top-1 h-3 w-3 rounded-full ${u.is_active ? 'bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.9)]' : 'bg-rose-400'}`} />
                    </div>
                    <div>
                      <p className="font-semibold text-white">{u.username}</p>
                      <p className="text-sm text-slate-400">{u.email}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <RoleBadge role={u.role} />
                        <StatusPill label={u.is_active ? 'Active' : 'Disabled'} tone={u.is_active ? 'emerald' : 'rose'} />
                      </div>
                    </div>
                  </div>
                  <button onClick={() => toggleActive(u)} className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200 ring-1 ring-white/10 hover:bg-white/8">
                    {u.is_active ? 'Disable' : 'Enable'}
                  </button>
                </div>
                <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
                  <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">Org: <span className="text-white">{u.org_id || '—'}</span></div>
                  <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">Last active: <span className="text-white">{u.last_active_at || u.updated_at || '—'}</span></div>
                </div>
              </GlassPanel>
            ))}
          </div>
        </>
      )}

      {tab === 'keys' && (
        <>
          {newKey && (
            <GlassPanel className="p-4">
              <div className="mb-2 flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-300" />
                <span className="font-medium text-white text-sm">API key created - copy now, won't show again</span>
              </div>
              <code className="block rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs font-mono break-all text-slate-200">
                {newKey}
              </code>
              <button onClick={() => { navigator.clipboard.writeText(newKey); }} className="mt-3 text-xs text-cyan-300 hover:underline">Copy to clipboard</button>
            </GlassPanel>
          )}

          <form onSubmit={createApiKey} className="flex gap-2">
            <input value={keyName} onChange={e => setKeyName(e.target.value)}
              placeholder="Key name (e.g. prod-integration)"
              className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
            <button type="submit" disabled={!keyName || saving}
              className="inline-flex items-center gap-1.5 rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 disabled:opacity-60">
              <Key className="w-4 h-4" /> Generate Key
            </button>
          </form>

          <div className="grid gap-3 lg:grid-cols-2">
            {apiKeys.map((k: any) => (
              <GlassPanel key={k.id} className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-white">{k.name}</p>
                    <p className="mt-1 text-xs text-slate-400">Created {k.created_at?.slice(0,10)}</p>
                  </div>
                  <StatusPill label={k.is_active ? 'Active' : 'Revoked'} tone={k.is_active ? 'emerald' : 'rose'} />
                </div>
                <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
                  <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">Last used: <span className="text-white">{k.last_used_at?.slice(0,10) ?? '—'}</span></div>
                  <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">Visibility: <span className="text-white">{k.is_active ? 'Live' : 'Locked'}</span></div>
                </div>
                {k.is_active && (
                  <button onClick={() => revokeKey(k.id)} className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-200 ring-1 ring-rose-400/20">
                    <Trash2 className="h-3 w-3" /> Revoke
                  </button>
                )}
              </GlassPanel>
            ))}
          </div>
        </>
      )}
      </div>
    </div>
  );
}
