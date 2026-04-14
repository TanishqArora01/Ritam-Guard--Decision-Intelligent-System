'use client';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { AlertTriangle, Filter, RefreshCw, ShieldCheck, UserCheck } from 'lucide-react';
import { api } from '../../lib/api';
import {
  DecisionBadge, FeatureBar, GlassPanel, PageBackdrop, SLAChip, SectionHeader, StatusPill, TimelineCard,
} from '../../components/cockpit';
import type { ReviewCase } from '../../lib/types';
import { formatDistanceToNow, parseISO } from 'date-fns';

const COLUMNS = [
  { key: 'OPEN', label: 'Open', tone: 'amber' },
  { key: 'IN_REVIEW', label: 'In Review', tone: 'cyan' },
  { key: 'ESCALATED', label: 'Escalated', tone: 'rose' },
  { key: 'RESOLVED', label: 'Closed', tone: 'emerald' },
] as const;

const HEATMAP_BUCKETS = [
  { label: 'Low', min: 0, max: 0.4 },
  { label: 'Medium', min: 0.4, max: 0.7 },
  { label: 'High', min: 0.7, max: 1.01 },
];

export default function ReviewQueuePage() {
  const [cases,   setCases]   = useState<ReviewCase[]>([]);
  const [total,   setTotal]   = useState(0);
  const [openCt,  setOpenCt]  = useState(0);
  const [revCt,   setRevCt]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [status,  setStatus]  = useState('');
  const [myOnly,  setMyOnly]  = useState(false);
  const [page,    setPage]    = useState(1);
  const [pages,   setPages]   = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [dragId, setDragId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: 20 };
      if (status)  params.status         = status;
      if (myOnly)  params.assigned_to_me = true;
      const data = await api.queue.list(params);
      setCases(data.items ?? []);
      setTotal(data.total ?? 0);
      setPages(data.pages ?? 1);
      setOpenCt(data.open_count ?? 0);
      setRevCt(data.in_review_count ?? 0);
    } catch { } finally { setLoading(false); }
  }, [page, status, myOnly]);

  useEffect(() => { load(); }, [load]);

  const grouped = useMemo(() => {
    const items = cases.filter((item) => !status || item.status === status);
    return COLUMNS.map((column) => ({
      ...column,
      items: items.filter((item) => item.status === column.key),
    }));
  }, [cases, status]);

  const moveCase = async (id: string, target: typeof COLUMNS[number]['key']) => {
    const current = cases.find((item) => item.id === id);
    if (!current) return;
    if (target === current.status) return;

    try {
      if (target === 'IN_REVIEW') {
        const updated = await api.queue.assign(id);
        setCases((prev) => prev.map((item) => item.id === id ? { ...item, ...updated, status: 'IN_REVIEW' } : item));
      } else if (target === 'ESCALATED') {
        const [updated] = await Promise.all([
          api.queue.status(id, 'ESCALATED'),
          api.queue.priority(id, 1),
        ]);
        setCases((prev) => prev.map((item) => item.id === id ? { ...item, ...updated, status: 'ESCALATED', priority: 1 } : item));
      } else if (target === 'RESOLVED') {
        const updated = await api.queue.status(id, 'RESOLVED');
        setCases((prev) => prev.map((item) => item.id === id ? { ...item, ...updated, status: 'RESOLVED' } : item));
      } else {
        const updated = await api.queue.status(id, 'OPEN');
        setCases((prev) => prev.map((item) => item.id === id ? { ...item, ...updated, status: 'OPEN' } : item));
      }
    } catch {
      await load();
    }
  };

  const toggleSelected = (id: string) => {
    setSelected((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]);
  };

  const applyBulk = async (target: 'IN_REVIEW' | 'ESCALATED') => {
    const ids = selected.length ? selected : grouped[0]?.items.map((item) => item.id) ?? [];
    for (const id of ids) {
      // Keep actions on the existing API surface.
      // The visual board updates immediately, then refreshes from backend if needed.
      // eslint-disable-next-line no-await-in-loop
      await moveCase(id, target);
    }
    setSelected([]);
  };

  const sync = async () => {
    setSyncing(true);
    try { await api.queue.sync(); await load(); } catch { } finally { setSyncing(false); }
  };

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Review queue</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Operations board</h1>
              <p className="mt-2 text-sm text-slate-400">Queue prioritization, SLA pressure, and action-first case handling.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={`${openCt} open`} tone="amber" />
              <StatusPill label={`${revCt} in review`} tone="cyan" />
              <StatusPill label={`${total} total`} tone="emerald" />
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-3">
            <button onClick={sync} disabled={syncing} className="inline-flex items-center gap-2 rounded-2xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:translate-y-[-1px] disabled:opacity-60">
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} /> Sync from decisions
            </button>
            <button onClick={() => applyBulk('IN_REVIEW')} disabled={!selected.length && !grouped[0]?.items.length} className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8">
              <UserCheck className="h-4 w-4" /> Bulk assign
            </button>
            <button onClick={() => applyBulk('ESCALATED')} disabled={!selected.length && !grouped[0]?.items.length} className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8">
              <ShieldCheck className="h-4 w-4" /> Bulk escalate
            </button>
            <label className="ml-auto inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm text-slate-200 ring-1 ring-white/10">
              <input type="checkbox" checked={myOnly} onChange={(e) => { setMyOnly(e.target.checked); setPage(1); }} className="rounded border-white/20 bg-transparent text-cyan-400" />
              Assigned to me
            </label>
            <div className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm text-slate-300 ring-1 ring-white/10">
              <Filter className="h-4 w-4 text-cyan-300" />
              <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="bg-transparent text-sm outline-none">
                <option value="">All</option>
                {COLUMNS.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}
              </select>
            </div>
          </div>
        </GlassPanel>

        {loading ? (
          <div className="grid gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => <GlassPanel key={index} className="h-80 animate-shimmer" />)}
          </div>
        ) : (
          <>
            <GlassPanel className="p-5">
              <SectionHeader title="Risk heatmap" subtitle="Workload intensity by queue stage and fraud band" />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-[0.24em] text-slate-400">
                    <tr>
                      <th className="pb-2 pr-3 text-left">Stage</th>
                      {HEATMAP_BUCKETS.map((bucket) => (
                        <th key={bucket.label} className="pb-2 px-3 text-center">{bucket.label}</th>
                      ))}
                      <th className="pb-2 pl-3 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {grouped.map((column) => {
                      const counts = HEATMAP_BUCKETS.map((bucket) =>
                        column.items.filter((item) => item.p_fraud >= bucket.min && item.p_fraud < bucket.max).length,
                      );
                      const max = Math.max(1, ...counts);
                      return (
                        <tr key={`heat-${column.key}`}>
                          <td className="py-3 pr-3 text-slate-200 font-medium">{column.label}</td>
                          {counts.map((count, index) => {
                            const intensity = Math.min(1, count / max);
                            const tone = index === 2 ? `rgba(251,113,133,${0.18 + intensity * 0.4})` : index === 1 ? `rgba(251,191,36,${0.18 + intensity * 0.4})` : `rgba(52,211,153,${0.18 + intensity * 0.4})`;
                            return (
                              <td key={`${column.key}-${index}`} className="px-3 py-3 text-center">
                                <div className="rounded-xl border border-white/10 px-3 py-2 text-xs font-semibold text-slate-100" style={{ backgroundColor: tone }}>
                                  {count}
                                </div>
                              </td>
                            );
                          })}
                          <td className="py-3 pl-3 text-right text-slate-300">{column.items.length}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </GlassPanel>

            <div className="grid gap-4 lg:grid-cols-4">
            {grouped.map((column) => (
              <div key={column.key} className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <div>
                    <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{column.label}</p>
                    <p className="mt-1 text-sm text-slate-300">{column.items.length} cases</p>
                  </div>
                  <StatusPill label={column.label} tone={column.tone as any} />
                </div>
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => dragId && moveCase(dragId, column.key)}
                  className="min-h-[30rem] space-y-3 rounded-3xl border border-dashed border-white/10 bg-white/3 p-3"
                >
                  {column.items.length === 0 ? (
                    <div className="flex h-40 items-center justify-center rounded-3xl border border-white/5 bg-white/5 text-sm text-slate-500">Drop cases here</div>
                  ) : (
                    column.items.map((item, index) => {
                      const isSelected = selected.includes(item.id);
                      return (
                        <motion.div key={item.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, delay: index * 0.02 }} draggable onDragStart={() => setDragId(item.id)} onDragEnd={() => setDragId(null)}>
                          <TimelineCard
                            title={`${item.customer_id} · $${item.amount.toLocaleString()}`}
                            subtitle={`${item.txn_id.slice(0, 12)}… · ${item.priority === 1 ? 'High priority' : item.priority === 2 ? 'Medium priority' : 'Low priority'}`}
                            tone={(item.p_fraud >= 0.7 ? 'rose' : item.p_fraud >= 0.4 ? 'amber' : 'emerald') as any}
                            expanded
                            meta={<label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={isSelected} onChange={() => toggleSelected(item.id)} className="rounded border-white/20 bg-transparent text-cyan-400" /> Select</label>}
                          >
                            <div className="space-y-3">
                              <FeatureBar value={item.p_fraud} />
                              <div className="grid gap-2 text-xs text-slate-400 sm:grid-cols-2">
                                <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">Priority: <span className="text-white">{item.priority}</span></div>
                                <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">SLA: <SLAChip createdAt={item.created_at} /></div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Link href={`/review-queue/${item.id}`} className="rounded-full bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:translate-y-[-1px]">Open case</Link>
                                {item.status !== 'IN_REVIEW' && <button onClick={() => moveCase(item.id, 'IN_REVIEW')} className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-100 ring-1 ring-white/10">Take</button>}
                                {item.status !== 'ESCALATED' && <button onClick={() => moveCase(item.id, 'ESCALATED')} className="rounded-full bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-100 ring-1 ring-white/10">Escalate</button>}
                              </div>
                              <div className="text-xs text-slate-500">{item.created_at ? formatDistanceToNow(parseISO(item.created_at), { addSuffix: true }) : '—'}</div>
                            </div>
                          </TimelineCard>
                        </motion.div>
                      );
                    })
                  )}
                </div>
              </div>
            ))}
            </div>
          </>
        )}

        {pages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 disabled:opacity-40">Previous</button>
            <span className="text-xs text-slate-400">Page {page} of {pages}</span>
            <button onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page === pages} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 disabled:opacity-40">Next</button>
          </div>
        )}
      </div>
    </div>
  );
}
