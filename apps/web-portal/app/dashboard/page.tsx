'use client';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend, AreaChart, Area,
} from 'recharts';
import { motion } from 'framer-motion';
import { Activity, AlertTriangle, CheckCircle, MousePointer2, Network, Shield, Sparkles, TrendingUp, Users, XCircle, Zap } from 'lucide-react';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { useUiStore } from '../../lib/ui-store';
import {
  AnimatedCounter, DecisionBadge, EmptyState, GlassPanel, HealthPulse, MetricCard,
  PageBackdrop, PermissionMatrix, RiskGauge, RoleBadge, RoleSummary, SectionHeader,
  StatusPill, StreamTicker, SystemHealth, TimelineCard,
} from '../../components/cockpit';
import { format, parseISO } from 'date-fns';

const ACTION_COLORS: Record<string, string> = {
  APPROVE: '#22c55e', BLOCK: '#ef4444',
  STEP_UP_AUTH: '#f59e0b', MANUAL_REVIEW: '#8b5cf6',
};

function fmtNum(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { dashboardWidgets, moveWidget, resetWidgets } = useUiStore();
  const [overview,   setOverview]   = useState<any>(null);
  const [rateData,   setRateData]   = useState<any[]>([]);
  const [actionData, setActionData] = useState<any[]>([]);
  const [topRisk,    setTopRisk]    = useState<any[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [dragFrom,   setDragFrom]   = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [ov, rate, actions, risk] = await Promise.all([
        api.analytics.overview(),
        api.analytics.fraudRate(24, 'hour'),
        api.analytics.actions(24),
        api.analytics.topRisk(1),
      ]);
      setOverview(ov);
      setRateData((rate.data ?? []).map((r: any) => ({
        ...r,
        time: r.bucket ? format(parseISO(r.bucket), 'HH:mm') : '',
      })));
      setActionData(actions.data ?? []);
      setTopRisk(risk.data ?? []);
    } catch { /* backend may not be available in dev */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 30_000); return () => clearInterval(t); }, [load]);

  const role = user?.role ?? 'ANALYST';
  const ov = overview ?? {};
  const spark = useMemo(() => rateData.slice(-12).map((r: any) => ({ value: Number(r.block_rate_pct ?? 0) })), [rateData]);
  const activitySpark = useMemo(() => actionData.map((r: any) => ({ value: Number(r.count ?? 0) })), [actionData]);

  const widgets = {
    health: <SystemHealth status={ov.block_rate_pct >= 7 ? 'critical' : ov.block_rate_pct >= 4 ? 'warning' : 'healthy'} />,
    ticker: <StreamTicker items={[
      `${fmtNum(ov.total_decisions ?? 0)} decisions`,
      `${ov.block_rate_pct ?? 0}% block rate`,
      `${ov.p95_latency_ms ?? 0}ms p95 latency`,
      `${fmtNum(ov.manual_review ?? 0)} manual reviews`,
    ]} />,
    risk: <RiskGauge value={(ov.avg_p_fraud ?? 0)} />,
    network: <GlassPanel className="p-5"><SectionHeader title="Fraud network" subtitle="Activity clusters and graph pressure" /><FraudNetwork nodes={topRisk.slice(0, 6)} /></GlassPanel>,
    latency: <GlassPanel className="p-5"><SectionHeader title="Latency profile" subtitle="Recent decision latency trend" /><ResponsiveContainer width="100%" height={220}><AreaChart data={rateData}><defs><linearGradient id="latencyGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#22d3ee" stopOpacity={0.45} /><stop offset="95%" stopColor="#22d3ee" stopOpacity={0.04} /></linearGradient></defs><XAxis dataKey="time" tick={{ fontSize: 11, fill: '#94a3b8' }} /><YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, color: '#fff' }} /><Area type="monotone" dataKey="avg_latency_ms" stroke="#22d3ee" fill="url(#latencyGrad)" strokeWidth={2} /></AreaChart></ResponsiveContainer></GlassPanel>,
    users: <GlassPanel className="p-5"><SectionHeader title="Operational users" subtitle="Live team visibility" /><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{['Analysts online', 'Ops queue owners', 'Partner viewers'].map((label, index) => <div key={label} className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p><p className="mt-2 text-2xl font-semibold text-white">{[8, 3, 4][index]}</p></div>)}</div></GlassPanel>,
  } as const;

  const onDragStart = (index: number) => setDragFrom(index);
  const onDrop = (index: number) => {
    if (dragFrom === null || dragFrom === index) return;
    moveWidget(dragFrom, index);
    setDragFrom(null);
  };

  const rolePanels = {
    ADMIN: (
      <div className="space-y-5">
        <PermissionMatrix rows={[
          { role: 'ADMIN', dashboard: 1, review: 1, analytics: 1, users: 1 },
          { role: 'OPS_MANAGER', dashboard: 1, review: 1, analytics: 1, users: 0 },
          { role: 'ANALYST', dashboard: 1, review: 1, analytics: 1, users: 0 },
          { role: 'BANK_PARTNER', dashboard: 1, review: 0, analytics: 1, users: 0 },
        ]} />
      </div>
    ),
    ANALYST: (
      <GlassPanel className="p-5">
        <SectionHeader title="Investigation cockpit" subtitle="Transaction-level detail, explainability, and case building" />
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {topRisk.slice(0, 6).map((r: any) => (
            <div key={r.txn_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-white">{r.customer_id}</p>
                  <p className="mt-1 text-xs text-slate-400 font-mono">{r.txn_id.slice(0, 10)}…</p>
                </div>
                <DecisionBadge action={r.action} size="xs" />
              </div>
              <div className="mt-3 space-y-2 text-xs text-slate-300">
                <div className="flex items-center justify-between"><span>Confidence</span><span>{(Number(r.avg_p_fraud ?? 0) * 100).toFixed(0)}%</span></div>
                <div className="flex items-center justify-between"><span>Latency</span><span>{Number(r.latency_ms).toFixed(0)}ms</span></div>
              </div>
            </div>
          ))}
        </div>
      </GlassPanel>
    ),
    OPS_MANAGER: (
      <GlassPanel className="p-5">
        <SectionHeader title="Operations view" subtitle="Queue pressure, SLA and bulk review focus" />
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <MetricCard title="Backlog" value={fmtNum(ov.manual_review ?? 0)} icon={AlertTriangle} accent="amber" spark={spark} />
          <MetricCard title="Approved" value={fmtNum(ov.approved ?? 0)} icon={CheckCircle} accent="emerald" spark={activitySpark} />
          <MetricCard title="Latency" value={`${ov.p95_latency_ms ?? 0}ms`} icon={Zap} accent="cyan" />
        </div>
      </GlassPanel>
    ),
    BANK_PARTNER: (
      <GlassPanel className="p-5">
        <SectionHeader title="Partner summary" subtitle="Only your portfolio, clean reporting, trust-first UI" />
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <MetricCard title="Total decisions" value={fmtNum(ov.total_decisions ?? 0)} icon={Shield} accent="cyan" />
          <MetricCard title="Block rate" value={`${ov.block_rate_pct ?? 0}%`} icon={XCircle} accent="rose" />
          <MetricCard title="Avg P(fraud)" value={(ov.avg_p_fraud ?? 0).toFixed(3)} icon={TrendingUp} accent="violet" />
        </div>
      </GlassPanel>
    ),
  };

  const content = dashboardWidgets.map((key, index) => (
    <div
      key={key}
      draggable
      onDragStart={() => onDragStart(index)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={() => onDrop(index)}
      className="transition duration-200 hover:scale-[1.01]"
    >
      {widgets[key]}
    </div>
  ));

  if (loading) {
    return (
      <div className="relative min-h-[70vh] px-4 py-8 lg:px-6">
        <PageBackdrop />
        <div className="relative z-10 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <GlassPanel key={index} className="h-40 animate-shimmer" />
          ))}
        </div>
      </div>
    );
  }

  const health = ov.block_rate_pct >= 7 ? 'critical' : ov.block_rate_pct >= 4 ? 'warning' : 'healthy';

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
          <GlassPanel className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Dashboard</p>
                <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">{role === 'ADMIN' ? 'System Control View' : role === 'ANALYST' ? 'Investigation View' : role === 'OPS_MANAGER' ? 'Operations View' : 'Partner View'}</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">At-a-glance intelligence, live widgets, and role-specific action surfaces. The same endpoints, now presented as a decision cockpit.</p>
              </div>
              <div className="flex items-center gap-3">
                <RoleBadge role={role as any} />
                <StatusPill label="Auto refresh 30s" tone="cyan" />
              </div>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard title="Total decisions" value={<AnimatedCounter value={ov.total_decisions ?? 0} />} icon={Shield} accent="cyan" spark={spark} trend="rolling" />
              <MetricCard title="Block rate" value={`${ov.block_rate_pct ?? 0}%`} icon={XCircle} accent="rose" spark={spark} />
              <MetricCard title="Avg P(fraud)" value={(ov.avg_p_fraud ?? 0).toFixed(3)} icon={TrendingUp} accent="amber" spark={spark} />
              <MetricCard title="p95 latency" value={`${ov.p95_latency_ms ?? 0}ms`} icon={Zap} accent="emerald" spark={activitySpark} />
            </div>
          </GlassPanel>
          <div className="space-y-4">
            <SystemHealth status={health} />
            <RiskGauge value={ov.avg_p_fraud ?? 0} />
          </div>
        </motion.div>

        <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          {rolePanels[role as keyof typeof rolePanels]}
          <RoleSummary role={role as any} />
        </div>

        <GlassPanel className="p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <SectionHeader title="Widget surface" subtitle="Drag and drop the modules to reorder the cockpit" action={<button onClick={resetWidgets} className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:text-white">Reset layout</button>} />
            <MousePointer2 className="h-4 w-4 text-cyan-300" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {content.map((item, index) => (
              <div key={index} onDragOver={(e) => e.preventDefault()} onDrop={() => onDrop(index)} className="min-h-[20px]">
                {item}
              </div>
            ))}
          </div>
        </GlassPanel>

        <div className="grid gap-4 lg:grid-cols-2">
          <GlassPanel className="p-5">
            <SectionHeader title="Fraud rate + volume trend" subtitle="Animated decision pressure over time" />
            {rateData.length ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={rateData}>
                  <defs>
                    <linearGradient id="lineStroke" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#22d3ee" />
                      <stop offset="55%" stopColor="#60a5fa" />
                      <stop offset="100%" stopColor="#a78bfa" />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, color: '#fff' }} />
                  <Line type="monotone" dataKey="block_rate_pct" stroke="url(#lineStroke)" strokeWidth={3} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No trend data yet" description="Waiting for decisions to populate the trend line" icon={Sparkles} />
            )}
          </GlassPanel>
          <GlassPanel className="p-5">
            <SectionHeader title="Action distribution" subtitle="Risk posture over the last 24h" />
            {actionData.length ? (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={actionData} dataKey="count" nameKey="action" cx="50%" cy="50%" outerRadius={92} label={({ action, pct }: any) => `${pct}%`}>
                    {actionData.map((entry: any) => <Cell key={entry.action} fill={ACTION_COLORS[entry.action] ?? '#94a3b8'} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, color: '#fff' }} />
                  <Legend formatter={(val) => val.replace('_', ' ')} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No action distribution yet" description="Activity will appear here once the pipeline starts scoring transactions" icon={Activity} />
            )}
          </GlassPanel>
        </div>

        <GlassPanel className="p-5">
          <SectionHeader title="Highest risk transactions" subtitle="Live inspection list with score-first reading order" />
          {topRisk.length ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-[0.22em] text-slate-400">
                  <tr>
                    <th className="pb-3 pr-4 text-left">Transaction</th>
                    <th className="pb-3 pr-4 text-left">Customer</th>
                    <th className="pb-3 pr-4 text-left">Amount</th>
                    <th className="pb-3 pr-4 text-left">Action</th>
                    <th className="pb-3 pr-4 text-left">P(fraud)</th>
                    <th className="pb-3 text-left">Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {topRisk.map((r: any) => (
                    <tr key={r.txn_id} className="transition hover:bg-white/5">
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{r.txn_id.slice(0, 12)}…</td>
                      <td className="py-3 pr-4 text-sm text-white">{r.customer_id}</td>
                      <td className="py-3 pr-4 font-medium text-slate-200">${Number(r.amount).toLocaleString()}</td>
                      <td className="py-3 pr-4"><DecisionBadge action={r.action} size="xs" /></td>
                      <td className="py-3 pr-4">
                        <span className={`font-mono text-xs font-semibold ${r.p_fraud >= 0.7 ? 'text-rose-300' : r.p_fraud >= 0.4 ? 'text-amber-300' : 'text-emerald-300'}`}>
                          {(r.p_fraud * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-3 text-xs text-slate-400">{Number(r.latency_ms).toFixed(0)}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No high-risk transactions yet" description="Once live traffic reaches the system, this panel becomes the triage lane" icon={Shield} />
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function FraudNetwork({ nodes }: { nodes: any[] }) {
  const radius = 95;
  const center = 120;
  const positions = nodes.map((_, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, nodes.length);
    return {
      x: center + Math.cos(angle) * radius,
      y: center + Math.sin(angle) * radius,
    };
  });

  return (
    <svg viewBox="0 0 240 240" className="h-64 w-full">
      <defs>
        <radialGradient id="nodeCore" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.8" />
        </radialGradient>
      </defs>
      <circle cx={center} cy={center} r={28} fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.12)" />
      {positions.map((node, index) => (
        <g key={nodes[index]?.txn_id ?? index}>
          <line x1={center} y1={center} x2={node.x} y2={node.y} stroke="rgba(34,211,238,0.24)" strokeWidth="1.4" />
          <motion.circle cx={node.x} cy={node.y} r="10" fill="url(#nodeCore)" initial={{ scale: 0.8, opacity: 0.5 }} animate={{ scale: [0.9, 1.05, 0.9], opacity: 1 }} transition={{ duration: 3 + index * 0.2, repeat: Infinity }} />
          <text x={node.x} y={node.y + 22} textAnchor="middle" className="fill-slate-300 text-[10px] font-medium">
            {nodes[index]?.customer_id?.slice(0, 8) ?? 'node'}
          </text>
        </g>
      ))}
    </svg>
  );
}
