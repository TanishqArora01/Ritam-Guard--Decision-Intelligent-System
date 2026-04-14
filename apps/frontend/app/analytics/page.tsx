'use client';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine,
} from 'recharts';
import { motion } from 'framer-motion';
import { BarChart2, Filter, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '../../lib/api';
import { AnimatedCounter, EmptyState, GlassPanel, PageBackdrop, RiskGauge, SectionHeader, StatusPill } from '../../components/cockpit';
import { format, parseISO } from 'date-fns';

const HOURS_OPTIONS = [1, 6, 24, 48, 168];

export default function AnalyticsPage() {
  const [hours,    setHours]    = useState(24);
  const [rateData, setRateData] = useState<any[]>([]);
  const [latency,  setLatency]  = useState<any>({});
  const [abData,   setAbData]   = useState<any[]>([]);
  const [loading,  setLoading]  = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const gran = hours <= 2 ? 'minute' : hours <= 48 ? 'hour' : 'day';
      const [rate, lat, ab] = await Promise.all([
        api.analytics.fraudRate(hours, gran),
        api.analytics.latency(Math.min(hours, 24)),
        api.analytics.abCompare(hours).catch(() => ({ data: [] })),
      ]);
      setRateData((rate.data ?? []).map((r: any) => ({
        ...r,
        time: r.bucket ? format(parseISO(r.bucket),
          gran === 'minute' ? 'HH:mm' : gran === 'day' ? 'MMM dd' : 'MM/dd HH:mm') : '',
      })));
      setLatency(lat ?? {});
      setAbData(ab.data ?? []);
    } catch { } finally { setLoading(false); }
  }, [hours]);

  useEffect(() => { load(); }, [load]);

  const drift = useMemo(() => {
    if (!rateData.length) return 0;
    const mid = Math.floor(rateData.length / 2);
    const left = rateData.slice(0, mid).reduce((sum, row) => sum + Number(row.block_rate_pct ?? 0), 0) / Math.max(1, mid);
    const right = rateData.slice(mid).reduce((sum, row) => sum + Number(row.block_rate_pct ?? 0), 0) / Math.max(1, rateData.length - mid);
    return Math.abs(right - left);
  }, [rateData]);

  const clusterNodes = useMemo(() => {
    const base = rateData.slice(-10);
    return base.map((row, index) => ({
      x: 40 + (index % 5) * 70,
      y: 40 + Math.floor(index / 5) * 70,
      label: row.time,
      score: Number(row.block_rate_pct ?? 0),
    }));
  }, [rateData]);

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Analytics</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Model performance and fraud trend analysis</h1>
              <p className="mt-2 text-sm text-slate-400">Animated metrics, cluster intelligence, and drift signals from the current REST-backed analytics endpoints.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={`${hours}h`} tone="cyan" />
              <button onClick={load} className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8">
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
              </button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-3 py-2 ring-1 ring-white/10">
              <Filter className="h-4 w-4 text-cyan-300" />
              <span className="text-xs uppercase tracking-[0.24em] text-slate-400">Window</span>
            </div>
            {HOURS_OPTIONS.map((h) => (
              <button key={h} onClick={() => setHours(h)} className={`rounded-full px-4 py-2 text-xs font-medium ring-1 transition ${hours === h ? 'bg-cyan-400 text-slate-950 ring-cyan-400/30' : 'bg-white/5 text-slate-300 ring-white/10 hover:bg-white/8'}`}>
                {h < 24 ? `${h}h` : h === 24 ? '1d' : h === 48 ? '2d' : '7d'}
              </button>
            ))}
          </div>
        </GlassPanel>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <GlassPanel className="p-5"><p className="text-xs uppercase tracking-[0.24em] text-slate-400">p50 latency</p><p className="mt-2 text-3xl font-semibold text-white"><AnimatedCounter value={Number(latency.p50 ?? 0)} suffix="ms" /></p></GlassPanel>
          <GlassPanel className="p-5"><p className="text-xs uppercase tracking-[0.24em] text-slate-400">p95 latency</p><p className="mt-2 text-3xl font-semibold text-white"><AnimatedCounter value={Number(latency.p95 ?? 0)} suffix="ms" /></p></GlassPanel>
          <GlassPanel className="p-5"><p className="text-xs uppercase tracking-[0.24em] text-slate-400">p99 latency</p><p className="mt-2 text-3xl font-semibold text-white"><AnimatedCounter value={Number(latency.p99 ?? 0)} suffix="ms" /></p></GlassPanel>
          <GlassPanel className="p-5"><p className="text-xs uppercase tracking-[0.24em] text-slate-400">Avg latency</p><p className="mt-2 text-3xl font-semibold text-white"><AnimatedCounter value={Number(latency.avg ?? 0)} suffix="ms" /></p><p className="mt-1 text-xs text-slate-400">{latency.total ?? 0} decisions</p></GlassPanel>
        </div>

        {loading ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <GlassPanel className="h-80 animate-shimmer" />
            <GlassPanel className="h-80 animate-shimmer" />
          </div>
        ) : (
          <>
            <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
              <GlassPanel className="p-5">
                <SectionHeader title="Fraud rate + decision volume" subtitle="Interactive series with a visible alert threshold" />
                {rateData.length ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={rateData}>
                      <defs>
                        <linearGradient id="analyticsLine" x1="0" y1="0" x2="1" y2="0">
                          <stop offset="0%" stopColor="#22d3ee" />
                          <stop offset="60%" stopColor="#60a5fa" />
                          <stop offset="100%" stopColor="#a78bfa" />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#94a3b8' }} domain={[0, 'auto']} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, color: '#fff' }} />
                      <Legend />
                      <ReferenceLine yAxisId="left" y={5} stroke="#fb7185" strokeDasharray="4 4" label={{ value: 'Alert 5%', fill: '#fb7185', fontSize: 10 }} />
                      <Line yAxisId="left" type="monotone" dataKey="block_rate_pct" stroke="url(#analyticsLine)" strokeWidth={3} dot={false} name="Block rate %" />
                      <Line yAxisId="left" type="monotone" dataKey="avg_p_fraud" stroke="#fbbf24" strokeWidth={2} dot={false} name="Avg P(fraud)" />
                      <Bar yAxisId="right" dataKey="total" fill="rgba(255,255,255,0.12)" name="Decision volume" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : <EmptyState title="No data for this period" description="The trend series populates once decisions are available" icon={BarChart2} />}
              </GlassPanel>

              <div className="space-y-4">
                <RiskGauge value={Math.min(1, drift / 10)} />
                <GlassPanel className="p-5">
                  <SectionHeader title="Drift indicator" subtitle="Variance between the first and second half of the window" />
                  <div className="mt-4 flex items-end gap-4">
                    <div className="text-4xl font-semibold text-white"><AnimatedCounter value={drift} precision={1} suffix="%" /></div>
                    <div className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${drift > 3 ? 'bg-rose-500/15 text-rose-200 ring-rose-400/20' : 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/20'}`}>{drift > 3 ? 'Watch closely' : 'Stable'}</div>
                  </div>
                  <p className="mt-3 text-sm text-slate-400">This indicator is computed from the current time-series trend and highlights when the system starts moving away from baseline behavior.</p>
                </GlassPanel>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
              <GlassPanel className="p-5">
                <SectionHeader title="Fraud clusters" subtitle="Graph visualization derived from the latest activity window" />
                <ClusterGraph nodes={clusterNodes} />
              </GlassPanel>

              {abData.length > 0 && (
                <GlassPanel className="p-5">
                  <SectionHeader title="A/B experiment" subtitle="Control vs treatment with the existing experiment output" />
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-xs uppercase tracking-[0.24em] text-slate-400">
                        <tr>
                          <th className="pb-3 text-left pr-6">Variant</th>
                          <th className="pb-3 text-right pr-4">Decisions</th>
                          <th className="pb-3 text-right pr-4">Block rate</th>
                          <th className="pb-3 text-right pr-4">Approved</th>
                          <th className="pb-3 text-right pr-4">Step-up</th>
                          <th className="pb-3 text-right pr-4">Avg P(fraud)</th>
                          <th className="pb-3 text-right">Avg latency</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {abData.map((r: any) => (
                          <tr key={r.ab_variant} className="hover:bg-white/5">
                            <td className="py-3 pr-6 font-semibold capitalize text-white">{r.ab_variant}</td>
                            <td className="py-3 pr-4 text-right text-slate-200">{r.total?.toLocaleString()}</td>
                            <td className="py-3 pr-4 text-right text-slate-200">{r.block_rate_pct}%</td>
                            <td className="py-3 pr-4 text-right text-emerald-300">{r.approved?.toLocaleString()}</td>
                            <td className="py-3 pr-4 text-right text-amber-300">{r.step_up?.toLocaleString()}</td>
                            <td className="py-3 pr-4 text-right font-mono text-xs text-slate-300">{r.avg_p_fraud}</td>
                            <td className="py-3 text-right font-mono text-xs text-slate-300">{r.avg_latency_ms}ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </GlassPanel>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ClusterGraph({ nodes }: { nodes: { x: number; y: number; label: string; score: number }[] }) {
  return (
    <svg viewBox="0 0 260 190" className="h-56 w-full">
      {nodes.map((node, index) => (
        <g key={`${node.label}-${index}`}>
          <circle cx={node.x} cy={node.y} r={12 + node.score / 2} fill={node.score > 5 ? 'rgba(251,113,133,0.8)' : node.score > 3 ? 'rgba(251,191,36,0.8)' : 'rgba(34,197,94,0.8)'} opacity="0.25" />
          <motion.circle cx={node.x} cy={node.y} r={7} fill={node.score > 5 ? '#fb7185' : node.score > 3 ? '#fbbf24' : '#22c55e'} animate={{ scale: [0.95, 1.05, 0.95] }} transition={{ duration: 2.8 + index * 0.15, repeat: Infinity }} />
          <text x={node.x} y={node.y + 22} textAnchor="middle" className="fill-slate-400 text-[10px]">{node.label}</text>
        </g>
      ))}
      {nodes.slice(1).map((node, index) => {
        const prev = nodes[index];
        return <line key={`${index}-${node.label}`} x1={prev.x} y1={prev.y} x2={node.x} y2={node.y} stroke="rgba(255,255,255,0.08)" strokeWidth="1" />;
      })}
    </svg>
  );
}
