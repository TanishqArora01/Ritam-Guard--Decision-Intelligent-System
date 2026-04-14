'use client';
import React, { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Clock3, FileSearch, Search, Workflow } from 'lucide-react';
import { api } from '../../lib/api';
import { DecisionBadge, EmptyState, FeatureBar, GlassPanel, PageBackdrop, SectionHeader, StatusPill, TimelineCard } from '../../components/cockpit';
import { format, parseISO } from 'date-fns';

const ACTIONS = ['', 'APPROVE', 'BLOCK', 'STEP_UP_AUTH', 'MANUAL_REVIEW'];

export default function AuditPage() {
  const [txnId,      setTxnId]      = useState('');
  const [customerId, setCustomerId] = useState('');
  const [action,     setAction]     = useState('');
  const [pFraudMin,  setPFraudMin]  = useState('');
  const [pFraudMax,  setPFraudMax]  = useState('');
  const [dateFrom,   setDateFrom]   = useState('');
  const [dateTo,     setDateTo]     = useState('');
  const [page,       setPage]       = useState(1);
  const [results,    setResults]    = useState<any[]>([]);
  const [total,      setTotal]      = useState(0);
  const [pages,      setPages]      = useState(1);
  const [loading,    setLoading]    = useState(false);
  const [searched,   setSearched]   = useState(false);
  const [expanded,   setExpanded]   = useState<string | null>(null);

  const search = useCallback(async (pg = 1) => {
    setLoading(true); setSearched(true); setPage(pg);
    const params: any = { page: pg, page_size: 25 };
    if (txnId)      params.txn_id      = txnId;
    if (customerId) params.customer_id = customerId;
    if (action)     params.action      = action;
    if (pFraudMin !== '')  params.p_fraud_min = pFraudMin;
    if (pFraudMax !== '')  params.p_fraud_max = pFraudMax;
    if (dateFrom)   params.date_from   = dateFrom;
    if (dateTo)     params.date_to     = `${dateTo}T23:59:59`;
    try {
      const data = await api.decisions.list(params);
      setResults(data.items ?? []);
      setTotal(data.total ?? 0);
      setPages(data.pages ?? 1);
    } catch {
      setResults([]);
      setTotal(0);
      setPages(1);
    }
    finally { setLoading(false); }
  }, [txnId, customerId, action, pFraudMin, pFraudMax, dateFrom, dateTo]);

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); search(1); };

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-5">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Audit trail</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Decision journey search</h1>
              <p className="mt-2 text-sm text-slate-400">Timeline-based inspection of decisions with before/after evidence and explainability.</p>
            </div>
            <StatusPill label="Traceable" tone="cyan" />
          </div>
        </GlassPanel>

        {/* Search form */}
        <GlassPanel className="p-5 space-y-4">
          <SectionHeader title="Search filters" subtitle="Refine the timeline using decision and transaction attributes" />
          <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Transaction ID</label>
            <input value={txnId} onChange={e => setTxnId(e.target.value)} placeholder="txn-001…"
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Customer ID</label>
            <input value={customerId} onChange={e => setCustomerId(e.target.value)} placeholder="cust-001…"
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Action</label>
            <select value={action} onChange={e => setAction(e.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40">
              {ACTIONS.map(a => (
                <option key={a} value={a}>{a || 'All actions'}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Min P(fraud)</label>
            <input type="number" min="0" max="1" step="0.01"
              value={pFraudMin} onChange={e => setPFraudMin(e.target.value)}
              placeholder="0.70"
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">Max P(fraud)</label>
            <input type="number" min="0" max="1" step="0.01"
              value={pFraudMax} onChange={e => setPFraudMax(e.target.value)}
              placeholder="1.00"
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">From date</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-[0.24em] text-slate-400">To date</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/40" />
          </div>
          <div className="lg:col-span-3">
            <button type="submit" className="inline-flex items-center gap-2 rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:translate-y-[-1px]">
              <Search className="h-4 w-4" /> Search decisions
            </button>
          </div>
        </form>
        </GlassPanel>

        {loading && <div className="grid gap-3"><GlassPanel className="h-40 animate-shimmer" /><GlassPanel className="h-40 animate-shimmer" /></div>}

        {!loading && searched && (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">{total.toLocaleString()} decisions found</p>

            {results.length === 0 ? (
              <EmptyState title="No decisions found" description="Try different search criteria" icon={FileSearch} />
            ) : (
              <div className="space-y-3">
                {results.map((r: any, index) => (
                  <motion.div key={r.txn_id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, delay: index * 0.02 }}>
                    <TimelineCard
                      title={`${r.currency} ${Number(r.amount).toLocaleString()}`}
                      subtitle={`${r.customer_id} · ${r.decided_at ? format(parseISO(r.decided_at), 'MMM dd HH:mm:ss') : '—'}`}
                      tone={(r.action === 'BLOCK' ? 'rose' : r.action === 'STEP_UP_AUTH' ? 'amber' : r.action === 'MANUAL_REVIEW' ? 'violet' : 'emerald') as any}
                      expanded={expanded === r.txn_id}
                      onToggle={() => setExpanded(expanded === r.txn_id ? null : r.txn_id)}
                      meta={<DecisionBadge action={r.action} size="xs" />}
                    >
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-3">
                          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <div className="grid gap-2 text-xs text-slate-300 sm:grid-cols-2">
                              <div className="rounded-xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="block text-slate-400">Graph risk</span><span className="mt-1 block text-white">{(r.graph_risk_score * 100).toFixed(1)}%</span></div>
                              <div className="rounded-xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="block text-slate-400">Anomaly score</span><span className="mt-1 block text-white">{(r.anomaly_score * 100).toFixed(1)}%</span></div>
                              <div className="rounded-xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="block text-slate-400">Confidence</span><span className="mt-1 block text-white">{(r.confidence * 100).toFixed(1)}%</span></div>
                              <div className="rounded-xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="block text-slate-400">Latency</span><span className="mt-1 block text-white">{Number(r.latency_ms).toFixed(0)}ms</span></div>
                            </div>
                          </div>
                          <FeatureBar value={r.p_fraud ?? 0} />
                          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-xs text-slate-300">
                            Trace path: source ingestion → model scoring → action routing → persistence.
                          </div>
                        </div>
                        <div className="space-y-3 rounded-3xl border border-white/10 bg-white/5 p-4">
                          <div className="flex items-center justify-between text-xs uppercase tracking-[0.24em] text-slate-400">
                            Evidence panel
                            <Workflow className="h-4 w-4 text-cyan-300" />
                          </div>
                          <div className="grid gap-2 text-sm text-slate-200">
                            <div className="rounded-2xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="text-slate-400">Optimal cost</span><span className="ml-2 text-white">${r.optimal_cost?.toFixed(2)}</span></div>
                            <div className="rounded-2xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="text-slate-400">A/B variant</span><span className="ml-2 text-white">{r.ab_variant || '—'}</span></div>
                            <div className="rounded-2xl bg-slate-950/50 p-3 ring-1 ring-white/10"><span className="text-slate-400">Model</span><span className="ml-2 font-mono text-white">{r.model_version || '—'}</span></div>
                          </div>
                          <div className="space-y-2">
                            {Object.entries(r.explanation ?? {}).slice(0, 4).map(([k, v]: any) => (
                              <div key={k} className="rounded-2xl bg-slate-950/50 p-3 ring-1 ring-white/10">
                                <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{k.replace(/_/g, ' ')}</div>
                                <div className="mt-1 text-sm text-white">{v}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </TimelineCard>
                  </motion.div>
                ))}

                {pages > 1 && (
                  <div className="flex items-center justify-center gap-2">
                    <button onClick={() => search(page - 1)} disabled={page === 1} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 disabled:opacity-40">Previous</button>
                    <span className="text-xs text-slate-400">Page {page} of {pages}</span>
                    <button onClick={() => search(page + 1)} disabled={page === pages} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 disabled:opacity-40">Next</button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
