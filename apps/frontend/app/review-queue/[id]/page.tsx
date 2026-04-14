'use client';
import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { ArrowLeft, CheckCircle, Clock3, Shield, User, Workflow } from 'lucide-react';
import { api } from '../../../lib/api';
import {
  DecisionBadge, FeatureBar, GlassPanel, PageBackdrop, SectionHeader, SLAChip, StatusPill, TimelineCard,
} from '../../../components/cockpit';
import type { ReviewCase, CaseVerdict } from '../../../lib/types';
import { formatDistanceToNow } from 'date-fns';

const VERDICTS: { value: CaseVerdict; label: string; color: string }[] = [
  { value: 'CONFIRMED_FRAUD', label: 'Confirmed Fraud',  color: 'red'   },
  { value: 'FALSE_POSITIVE',  label: 'False Positive',   color: 'green' },
  { value: 'INCONCLUSIVE',    label: 'Inconclusive',     color: 'gray'  },
];

function SignalRow({ label, value, children }: { label: string; value?: string | number; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
      <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</span>
      <div className="text-sm font-medium text-white">{children ?? value}</div>
    </div>
  );
}

export default function CaseDetailPage() {
  const { id }  = useParams<{ id: string }>();
  const router  = useRouter();
  const [c,       setC]       = useState<ReviewCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [verdict, setVerdict] = useState<CaseVerdict | ''>('');
  const [notes,   setNotes]   = useState('');
  const [saving,  setSaving]  = useState(false);

  useEffect(() => {
    api.queue.get(id).then(data => { setC(data); setNotes(data.analyst_notes ?? ''); })
       .catch(() => {}).finally(() => setLoading(false));
  }, [id]);

  const assign = async () => {
    if (!c) return;
    setSaving(true);
    try { const updated = await api.queue.assign(c.id); setC(updated); }
    catch { } finally { setSaving(false); }
  };

  const resolve = async () => {
    if (!c || !verdict) return;
    setSaving(true);
    try {
      const updated = await api.queue.resolve(c.id, verdict, notes);
      setC(updated);
    } catch { } finally { setSaving(false); }
  };

  const setPriority = async (p: number) => {
    if (!c) return;
    const updated = await api.queue.priority(c.id, p);
    setC(updated);
  };

  if (loading) return <div className="px-4 py-6 lg:px-6"><GlassPanel className="h-80 animate-shimmer" /></div>;
  if (!c)      return <div className="p-6 text-gray-500">Case not found</div>;

  const isResolved = c.status === 'RESOLVED';

  const journey = useMemo(() => [
    { title: 'Transaction detected', subtitle: 'Pipeline emitted a high-signal event', tone: 'cyan' as const },
    { title: 'Risk scored', subtitle: 'Stage 1 and Stage 2 generated the current evidence set', tone: 'amber' as const },
    { title: 'Decision routed', subtitle: `Current action: ${c.model_action}`, tone: 'violet' as const },
    { title: 'Analyst resolution', subtitle: c.status === 'RESOLVED' ? `Verdict: ${c.verdict ?? '—'}` : 'Pending investigation', tone: c.status === 'RESOLVED' ? 'emerald' as const : 'rose' as const },
  ], [c]);

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <button onClick={() => router.back()} className="inline-flex items-center gap-2 text-sm text-slate-400 transition hover:text-white">
          <ArrowLeft className="h-4 w-4" /> Back to queue
        </button>

        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Case review</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Decision journey</h1>
              <p className="mt-2 font-mono text-xs text-slate-400">{c.txn_id}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={c.status.replace('_', ' ')} tone={isResolved ? 'emerald' : c.status === 'ESCALATED' ? 'rose' : 'amber'} />
              <StatusPill label={`Priority ${c.priority}`} tone={c.priority === 1 ? 'rose' : c.priority === 2 ? 'amber' : 'cyan'} />
              <SLAChip createdAt={c.created_at} />
            </div>
          </div>
        </GlassPanel>

        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <GlassPanel className="p-5 space-y-4">
            <SectionHeader title="Evidence panel" subtitle="Risk signals and model explanation in a single view" />
            <div className="grid gap-3 md:grid-cols-2">
              <SignalRow label="Customer">{c.customer_id}</SignalRow>
              <SignalRow label="Amount">${c.amount.toLocaleString()} {c.currency}</SignalRow>
              <SignalRow label="Channel">{c.channel || '—'}</SignalRow>
              <SignalRow label="Country">{c.country_code || '—'}</SignalRow>
              <SignalRow label="Confidence">{(c.confidence * 100).toFixed(1)}%</SignalRow>
              <SignalRow label="Model version"><span className="font-mono text-xs">{c.model_version || '—'}</span></SignalRow>
            </div>
            <div className="space-y-3 pt-2">
              <FeatureBar value={c.p_fraud} />
              <FeatureBar value={c.graph_risk_score} />
              <FeatureBar value={c.anomaly_score} />
            </div>
            <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Model action</p>
                  <div className="mt-2"><DecisionBadge action={c.model_action} size="xs" /></div>
                </div>
                <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Graph risk</p>
                  <p className="mt-2 text-sm text-white">{(c.graph_risk_score * 100).toFixed(1)}%</p>
                </div>
                <div className="rounded-2xl bg-slate-950/60 p-3 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Anomaly score</p>
                  <p className="mt-2 text-sm text-white">{(c.anomaly_score * 100).toFixed(1)}%</p>
                </div>
              </div>
            </div>
          </GlassPanel>

          <div className="space-y-4">
            <GlassPanel className="p-5">
              <SectionHeader title="Decision trace" subtitle="Before / after journey through the resolution path" />
              <div className="mt-4 space-y-3">
                {journey.map((step) => (
                  <div key={step.title} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-white">{step.title}</p>
                        <p className="mt-1 text-xs text-slate-400">{step.subtitle}</p>
                      </div>
                      <StatusPill label={step.title} tone={step.tone} />
                    </div>
                  </div>
                ))}
              </div>
            </GlassPanel>

            <GlassPanel className="p-5">
              <SectionHeader title="Explanation" subtitle="Expandable reasoning from the decision payload" />
              <div className="mt-4 space-y-2">
                {Object.keys(c.explanation ?? {}).length ? Object.entries(c.explanation).map(([k, v]) => (
                  <div key={k} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                    <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{k.replace(/_/g, ' ')}</div>
                    <div className="mt-1 text-sm text-white">{v}</div>
                  </div>
                )) : <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-slate-400">No explanation available</div>}
              </div>
            </GlassPanel>
          </div>
        </div>

        {!isResolved ? (
          <GlassPanel className="p-5 space-y-4">
            <SectionHeader title="Analyst action" subtitle="Assign, document and close the case" />
            <div className="flex flex-wrap items-center gap-3">
              {!c.assigned_to && (
                <button onClick={assign} disabled={saving} className="inline-flex items-center gap-2 rounded-2xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:translate-y-[-1px] disabled:opacity-60">
                  <User className="h-4 w-4" /> Assign to me
                </button>
              )}
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-slate-300">
                Active since {c.created_at ? formatDistanceToNow(new Date(c.created_at), { addSuffix: true }) : '—'}
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">Verdict</label>
              <div className="flex flex-wrap gap-2">
                {VERDICTS.map((v) => (
                  <button key={v.value} onClick={() => setVerdict(v.value)} className={`rounded-full px-4 py-2 text-sm font-medium ring-1 transition ${verdict === v.value ? 'bg-white text-slate-950 ring-white/20' : 'bg-white/5 text-slate-200 ring-white/10 hover:bg-white/8'}`}>
                    {v.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">Analyst notes</label>
              <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add notes about this case…" className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40 focus:shadow-[0_0_0_4px_rgba(34,211,238,0.08)]" />
            </div>

            <button onClick={resolve} disabled={!verdict || saving} className="inline-flex items-center gap-2 rounded-2xl bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:translate-y-[-1px] disabled:opacity-50">
              <CheckCircle className="h-4 w-4" /> {saving ? 'Saving…' : 'Resolve case'}
            </button>
          </GlassPanel>
        ) : (
          <GlassPanel className="p-5">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-emerald-300" />
              <h2 className="text-lg font-semibold text-white">Case resolved</h2>
            </div>
            <p className="mt-2 text-sm text-slate-300">Verdict: <strong>{(c.verdict ?? '').replace('_', ' ')}</strong></p>
            {c.analyst_notes && <p className="mt-2 text-sm text-slate-400">{c.analyst_notes}</p>}
          </GlassPanel>
        )}
      </div>
    </div>
  );
}
