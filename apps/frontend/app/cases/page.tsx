'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ShieldCheck, ShieldX, TimerReset, UserCheck } from 'lucide-react';
import { api } from '../../lib/api';
import { DecisionBadge, GlassPanel, PageBackdrop, SectionHeader, StatusPill } from '../../components/cockpit';
import { listCaseQueue } from '../../lib/intelligence-api';
import { useAuth } from '../../lib/auth-context';
import type { ReviewCase } from '../../lib/types';

export default function CasesPage() {
  const { user } = useAuth();
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [selected, setSelected] = useState<ReviewCase | null>(null);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listCaseQueue(status ? { status, page: 1, page_size: 40 } : { page: 1, page_size: 40 });
      setCases(data.items);
      setSelected((prev) => prev ?? data.items[0] ?? null);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => ({
    open: cases.filter((c) => c.status === 'OPEN').length,
    inReview: cases.filter((c) => c.status === 'IN_REVIEW').length,
    escalated: cases.filter((c) => c.status === 'ESCALATED').length,
  }), [cases]);

  const refreshSelected = async () => {
    if (!selected) return;
    const updated = await api.queue.get(selected.id);
    setSelected(updated);
    setCases((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
  };

  const takeCase = async () => {
    if (!selected) return;
    setBusyAction('take');
    try {
      await api.queue.assign(selected.id);
      await refreshSelected();
    } finally {
      setBusyAction(null);
    }
  };

  const markBlocked = async () => {
    if (!selected) return;
    setBusyAction('block');
    try {
      await api.queue.resolve(selected.id, 'CONFIRMED_FRAUD', 'Blocked by analyst from intelligence cockpit.');
      await refreshSelected();
    } finally {
      setBusyAction(null);
    }
  };

  const markApproved = async () => {
    if (!selected) return;
    setBusyAction('approve');
    try {
      await api.queue.resolve(selected.id, 'FALSE_POSITIVE', 'Approved after analyst evidence review.');
      await refreshSelected();
    } finally {
      setBusyAction(null);
    }
  };

  const escalate = async () => {
    if (!selected) return;
    setBusyAction('escalate');
    try {
      await api.queue.status(selected.id, 'ESCALATED');
      await api.queue.priority(selected.id, 1);
      await refreshSelected();
    } finally {
      setBusyAction(null);
    }
  };

  if (user?.role === 'BANK_PARTNER') {
    return (
      <div className="relative min-h-full px-4 py-6 lg:px-6">
        <PageBackdrop />
        <div className="relative z-10 mx-auto max-w-3xl">
          <GlassPanel className="p-6">
            <SectionHeader title="Access restricted" subtitle="Case management is available for analyst, ops, and admin roles." />
          </GlassPanel>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-5">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Cases</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Analyst investigation workbench</h1>
              <p className="mt-2 text-sm text-slate-400">Case queue, transaction detail panel, and resolution actions for fraud analysts.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={`${grouped.open} open`} tone="amber" />
              <StatusPill label={`${grouped.inReview} in-review`} tone="cyan" />
              <StatusPill label={`${grouped.escalated} escalated`} tone="rose" />
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {['', 'OPEN', 'IN_REVIEW', 'ESCALATED', 'RESOLVED'].map((opt) => (
              <button
                key={opt || 'ALL'}
                onClick={() => setStatus(opt)}
                className={`rounded-full px-3 py-1.5 text-xs ring-1 transition ${status === opt ? 'bg-cyan-400 text-slate-950 ring-cyan-300/30' : 'bg-white/5 text-slate-300 ring-white/10 hover:bg-white/8'}`}
              >
                {opt || 'ALL'}
              </button>
            ))}
          </div>
        </GlassPanel>

        <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <GlassPanel className="p-4">
            <SectionHeader title="Case queue" subtitle="Prioritized fraud investigations" />
            <div className="mt-4 overflow-y-auto rounded-2xl border border-white/10" style={{ maxHeight: 560 }}>
              <table className="w-full text-sm">
                <thead className="bg-white/5 text-xs uppercase tracking-[0.2em] text-slate-400">
                  <tr>
                    <th className="px-3 py-3 text-left">Txn</th>
                    <th className="px-3 py-3 text-left">Action</th>
                    <th className="px-3 py-3 text-left">Status</th>
                    <th className="px-3 py-3 text-left">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {loading && (
                    <tr>
                      <td colSpan={4} className="px-3 py-8 text-center text-slate-400">Loading cases...</td>
                    </tr>
                  )}
                  {!loading && cases.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-3 py-8 text-center text-slate-400">No cases available.</td>
                    </tr>
                  )}
                  {!loading && cases.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setSelected(row)}
                      className={`cursor-pointer transition ${selected?.id === row.id ? 'bg-cyan-500/10' : 'hover:bg-white/5'}`}
                    >
                      <td className="px-3 py-3 font-mono text-xs text-slate-300">{row.txn_id.slice(0, 12)}...</td>
                      <td className="px-3 py-3"><DecisionBadge action={row.model_action} size="xs" /></td>
                      <td className="px-3 py-3 text-xs text-slate-200">{row.status}</td>
                      <td className="px-3 py-3 text-xs text-slate-300">{(row.p_fraud * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassPanel>

          <GlassPanel className="p-5">
            <SectionHeader title="Investigation panel" subtitle="Decision evidence and analyst actions" />
            {!selected ? (
              <p className="mt-4 text-sm text-slate-400">Select a case from the queue.</p>
            ) : (
              <div className="mt-4 space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Transaction</p>
                    <p className="mt-1 font-mono text-xs text-white">{selected.txn_id}</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Customer</p>
                    <p className="mt-1 text-white">{selected.customer_id}</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Risk</p>
                    <p className="mt-1 text-white">{(selected.p_fraud * 100).toFixed(1)}%</p>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Status</p>
                    <p className="mt-1 text-white">{selected.status}</p>
                  </div>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Model evidence</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {Object.entries(selected.explanation ?? {}).slice(0, 4).map(([k, v]) => (
                      <div key={k} className="rounded-xl bg-slate-950/60 p-3 text-xs text-slate-300 ring-1 ring-white/10">
                        <p className="uppercase tracking-[0.18em] text-slate-500">{k.replace(/_/g, ' ')}</p>
                        <p className="mt-1 text-white">{String(v)}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <button
                    onClick={takeCase}
                    disabled={busyAction !== null}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white/5 px-3 py-2 text-sm text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8 disabled:opacity-60"
                  >
                    <UserCheck className="h-4 w-4" /> Take
                  </button>
                  <button
                    onClick={markApproved}
                    disabled={busyAction !== null}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500/15 px-3 py-2 text-sm text-emerald-100 ring-1 ring-emerald-400/20 transition hover:bg-emerald-500/20 disabled:opacity-60"
                  >
                    <ShieldCheck className="h-4 w-4" /> Approve
                  </button>
                  <button
                    onClick={markBlocked}
                    disabled={busyAction !== null}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-rose-500/15 px-3 py-2 text-sm text-rose-100 ring-1 ring-rose-400/20 transition hover:bg-rose-500/20 disabled:opacity-60"
                  >
                    <ShieldX className="h-4 w-4" /> Block
                  </button>
                  <button
                    onClick={escalate}
                    disabled={busyAction !== null}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-500/15 px-3 py-2 text-sm text-amber-100 ring-1 ring-amber-400/20 transition hover:bg-amber-500/20 disabled:opacity-60"
                  >
                    <TimerReset className="h-4 w-4" /> Escalate
                  </button>
                </div>
              </div>
            )}
          </GlassPanel>
        </div>
      </div>
    </div>
  );
}
