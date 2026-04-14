'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import clsx from 'clsx';
import { Shield, Sparkles, Activity, Gauge, Users, AlertTriangle, Clock3 } from 'lucide-react';
import type { Action, Role } from '../lib/types';

export function PageBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(79,70,229,0.22),transparent_32%),radial-gradient(circle_at_top_right,rgba(34,197,94,0.10),transparent_26%),linear-gradient(180deg,rgba(11,15,26,0.92),rgba(11,15,26,1))]" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:72px_72px] opacity-20" />
      <div className="absolute -top-32 left-1/2 h-96 w-96 -translate-x-1/2 rounded-full bg-cyan-500/15 blur-3xl animate-float-slow" />
      <div className="absolute bottom-0 right-0 h-96 w-96 rounded-full bg-fuchsia-500/10 blur-3xl animate-float-slower" />
    </div>
  );
}

export function GlassPanel({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={clsx('glass-panel rounded-3xl border border-white/10 shadow-glow backdrop-blur-xl', className)}>
      {children}
    </div>
  );
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-white">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const ACTION_STYLES: Record<string, string> = {
  APPROVE: 'bg-emerald-500/15 text-emerald-300 ring-emerald-400/30',
  BLOCK: 'bg-rose-500/15 text-rose-300 ring-rose-400/30',
  STEP_UP_AUTH: 'bg-amber-500/15 text-amber-300 ring-amber-400/30',
  MANUAL_REVIEW: 'bg-violet-500/15 text-violet-300 ring-violet-400/30',
};

export function DecisionBadge({ action, size = 'sm' }: { action: string; size?: 'xs' | 'sm' | 'md' }) {
  const style = ACTION_STYLES[action] ?? 'bg-white/5 text-slate-300 ring-white/10';
  const padding = size === 'xs' ? 'px-2 py-0.5 text-[11px]' : size === 'md' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs';
  return (
    <span className={clsx('inline-flex items-center rounded-full ring-1 backdrop-blur-md font-medium', style, padding)}>
      {action.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (s) => s.toUpperCase())}
    </span>
  );
}

export function RoleBadge({ role }: { role: Role }) {
  const styles: Record<Role, string> = {
    ADMIN: 'from-rose-500/20 to-orange-500/20 text-rose-200 ring-rose-400/30',
    ANALYST: 'from-cyan-500/20 to-blue-500/20 text-cyan-200 ring-cyan-400/30',
    OPS_MANAGER: 'from-violet-500/20 to-fuchsia-500/20 text-violet-200 ring-violet-400/30',
    BANK_PARTNER: 'from-emerald-500/20 to-teal-500/20 text-emerald-200 ring-emerald-400/30',
  };
  return (
    <span className={clsx('inline-flex items-center rounded-full bg-gradient-to-r px-3 py-1 text-xs font-semibold ring-1', styles[role])}>
      {role.replace(/_/g, ' ')}
    </span>
  );
}

export function HealthPulse({ status }: { status: 'healthy' | 'warning' | 'critical' }) {
  const map = {
    healthy: 'bg-emerald-400 shadow-[0_0_28px_rgba(52,211,153,0.75)]',
    warning: 'bg-amber-400 shadow-[0_0_28px_rgba(251,191,36,0.65)]',
    critical: 'bg-rose-400 shadow-[0_0_28px_rgba(251,113,133,0.75)]',
  };
  return <span className={clsx('inline-flex h-3 w-3 rounded-full animate-pulse', map[status])} />;
}

export function AnimatedCounter({ value, suffix = '', precision = 0 }: { value: number; suffix?: string; precision?: number }) {
  const [display, setDisplay] = useState(0);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion) {
      setDisplay(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const from = display;
    const duration = 650;
    const animate = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from + (value - from) * eased);
      if (progress < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduceMotion]);

  return <span>{display.toFixed(precision)}{suffix}</span>;
}

export function MetricCard({
  title,
  value,
  sub,
  icon: Icon,
  accent = 'cyan',
  trend,
  spark,
}: {
  title: string;
  value: React.ReactNode;
  sub?: string;
  icon?: React.FC<any>;
  accent?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet';
  trend?: string;
  spark?: { value: number }[];
}) {
  const accentStyles: Record<string, string> = {
    cyan: 'from-cyan-400/20 to-blue-500/20 text-cyan-200',
    emerald: 'from-emerald-400/20 to-teal-500/20 text-emerald-200',
    amber: 'from-amber-400/20 to-orange-500/20 text-amber-200',
    rose: 'from-rose-400/20 to-red-500/20 text-rose-200',
    violet: 'from-violet-400/20 to-fuchsia-500/20 text-violet-200',
  };
  return (
    <GlassPanel className="p-4 transition duration-200 hover:-translate-y-0.5 hover:border-white/20 hover:shadow-[0_16px_50px_rgba(0,0,0,0.35)]">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <div className={clsx('inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br ring-1', accentStyles[accent])}>
            {Icon ? <Icon className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{title}</p>
            <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
            {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
          </div>
        </div>
        <div className="w-24">
          {spark?.length ? <MiniSparkline data={spark} color={accent} /> : trend ? <p className="text-right text-xs text-slate-400">{trend}</p> : null}
        </div>
      </div>
    </GlassPanel>
  );
}

export function MiniSparkline({ data, color = 'cyan' }: { data: { value: number }[]; color?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet' }) {
  const strokes: Record<string, string> = {
    cyan: '#22d3ee',
    emerald: '#34d399',
    amber: '#fbbf24',
    rose: '#fb7185',
    violet: '#a78bfa',
  };
  return (
    <ResponsiveContainer width="100%" height={52}>
      <AreaChart data={data}>
        <Tooltip content={() => null} />
        <Area type="monotone" dataKey="value" stroke={strokes[color]} strokeWidth={2} fillOpacity={0.18} fill={strokes[color]} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RiskGauge({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const status = pct >= 70 ? 'critical' : pct >= 40 ? 'warning' : 'healthy';
  const stroke = status === 'critical' ? '#fb7185' : status === 'warning' ? '#fbbf24' : '#34d399';
  return (
    <GlassPanel className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Risk gauge</p>
          <p className="mt-1 text-sm text-slate-300">Live risk pressure</p>
        </div>
        <HealthPulse status={status} />
      </div>
      <div className="mt-4 flex items-center justify-center">
        <svg width="180" height="180" viewBox="0 0 180 180" className="overflow-visible">
          <circle cx="90" cy="90" r="62" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="14" />
          <motion.circle
            cx="90"
            cy="90"
            r="62"
            fill="none"
            stroke={stroke}
            strokeLinecap="round"
            strokeWidth="14"
            strokeDasharray={389.6}
            initial={{ strokeDashoffset: 389.6 }}
            animate={{ strokeDashoffset: 389.6 - (389.6 * pct) / 100 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '90px 90px' }}
          />
          <text x="90" y="86" textAnchor="middle" className="fill-white text-3xl font-semibold">
            {pct.toFixed(0)}%
          </text>
          <text x="90" y="108" textAnchor="middle" className="fill-slate-400 text-xs uppercase tracking-[0.22em]">
            risk load
          </text>
        </svg>
      </div>
    </GlassPanel>
  );
}

export function SystemHealth({ status }: { status: 'healthy' | 'warning' | 'critical' }) {
  const label = status === 'healthy' ? 'Healthy' : status === 'warning' ? 'Degraded' : 'Critical';
  return (
    <GlassPanel className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        <HealthPulse status={status} />
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">System health</p>
          <p className="text-sm font-medium text-white">{label}</p>
        </div>
      </div>
      <Shield className="h-5 w-5 text-cyan-300" />
    </GlassPanel>
  );
}

export function StreamTicker({ items }: { items: string[] }) {
  return (
    <GlassPanel className="overflow-hidden px-4 py-3">
      <div className="flex items-center gap-3 text-xs uppercase tracking-[0.24em] text-slate-400">
        <Activity className="h-4 w-4 text-cyan-300" /> Real-time activity
      </div>
      <div className="mt-3 flex gap-8 whitespace-nowrap text-sm text-slate-300">
        <motion.div
          className="flex gap-8"
          animate={{ x: ['0%', '-50%'] }}
          transition={{ duration: 18, ease: 'linear', repeat: Infinity }}
        >
          {[...items, ...items].map((item, index) => (
            <span key={`${item}-${index}`} className="inline-flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.9)]" />
              {item}
            </span>
          ))}
        </motion.div>
      </div>
    </GlassPanel>
  );
}

export function FeatureBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const color = pct >= 70 ? 'bg-rose-400' : pct >= 40 ? 'bg-amber-400' : 'bg-emerald-400';
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>Feature contribution</span>
        <span>{pct.toFixed(0)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/5">
        <motion.div
          className={clsx('h-full rounded-full', color)}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

export function FeatureList({ items }: { items: { label: string; value: number }[] }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <FeatureBar key={item.label} value={item.value} />
      ))}
    </div>
  );
}

export function SLAChip({ createdAt }: { createdAt: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const age = Math.max(0, Math.floor((now - new Date(createdAt).getTime()) / 1000));
  const mins = Math.floor(age / 60);
  const secs = age % 60;
  const status = age > 900 ? 'critical' : age > 480 ? 'warning' : 'healthy';
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1',
      status === 'critical' ? 'bg-rose-500/15 text-rose-200 ring-rose-400/30' : status === 'warning' ? 'bg-amber-500/15 text-amber-200 ring-amber-400/30' : 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/30')}
    >
      <Clock3 className="h-3.5 w-3.5" />
      {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
    </span>
  );
}

export function PermissionMatrix({ rows }: { rows: { role: string; dashboard: number; review: number; analytics: number; users: number }[] }) {
  return (
    <GlassPanel className="p-5">
      <SectionHeader title="Permissions matrix" subtitle="Role coverage at a glance" />
      <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-slate-300">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Role</th>
              <th className="px-4 py-3 text-center font-medium">Dashboard</th>
              <th className="px-4 py-3 text-center font-medium">Review</th>
              <th className="px-4 py-3 text-center font-medium">Analytics</th>
              <th className="px-4 py-3 text-center font-medium">Users</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.role} className="border-t border-white/5 text-slate-200">
                <td className="px-4 py-3 font-medium">{row.role}</td>
                {[row.dashboard, row.review, row.analytics, row.users].map((value, index) => (
                  <td key={index} className="px-4 py-3 text-center">
                    <span className={clsx('inline-flex h-7 w-7 items-center justify-center rounded-lg text-xs font-semibold',
                      value ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/5 text-slate-500')}>{value ? '•' : '—'}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}

export function TimelineCard({
  title,
  subtitle,
  meta,
  tone = 'cyan',
  expanded,
  children,
  onToggle,
}: {
  title: string;
  subtitle?: string;
  meta?: React.ReactNode;
  tone?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet';
  expanded?: boolean;
  children?: React.ReactNode;
  onToggle?: () => void;
}) {
  const toneMap: Record<string, string> = {
    cyan: 'border-cyan-400/20 bg-cyan-400/8 shadow-[0_0_0_1px_rgba(34,211,238,0.12)]',
    emerald: 'border-emerald-400/20 bg-emerald-400/8 shadow-[0_0_0_1px_rgba(52,211,153,0.12)]',
    amber: 'border-amber-400/20 bg-amber-400/8 shadow-[0_0_0_1px_rgba(251,191,36,0.12)]',
    rose: 'border-rose-400/20 bg-rose-400/8 shadow-[0_0_0_1px_rgba(251,113,133,0.12)]',
    violet: 'border-violet-400/20 bg-violet-400/8 shadow-[0_0_0_1px_rgba(167,139,250,0.12)]',
  };
  return (
    <GlassPanel className={clsx('overflow-hidden border', toneMap[tone])}>
      <button onClick={onToggle} className="flex w-full items-start justify-between gap-4 p-4 text-left">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{subtitle}</p>
          <h3 className="mt-1 text-base font-semibold text-white">{title}</h3>
        </div>
        {meta}
      </button>
      {expanded && <div className="border-t border-white/10 p-4">{children}</div>}
    </GlassPanel>
  );
}

export function RoleSummary({ role }: { role: Role }) {
  const copy: Record<Role, { title: string; subtitle: string; icon: React.FC<any> }> = {
    ADMIN: { title: 'System Control View', subtitle: 'Full visibility, users, models, and network behavior.', icon: Shield },
    ANALYST: { title: 'Investigation View', subtitle: 'Transaction evidence, explainability, and case building.', icon: AlertTriangle },
    OPS_MANAGER: { title: 'Operations View', subtitle: 'Queue SLAs, bulk handling, and workload health.', icon: Activity },
    BANK_PARTNER: { title: 'Partner View', subtitle: 'Focused reporting with trust-first visibility.', icon: Users },
  };
  const item = copy[role];
  const Icon = item.icon;
  return (
    <GlassPanel className="p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/5 ring-1 ring-white/10">
          <Icon className="h-5 w-5 text-cyan-300" />
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Role mode</p>
          <h3 className="text-base font-semibold text-white">{item.title}</h3>
          <p className="mt-1 text-sm text-slate-400">{item.subtitle}</p>
        </div>
      </div>
    </GlassPanel>
  );
}

export function EmptyState({ title, description, icon: Icon }: { title: string; description?: string; icon?: React.FC<any> }) {
  return (
    <GlassPanel className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {Icon ? <Icon className="h-10 w-10 text-slate-500" /> : <Activity className="h-10 w-10 text-slate-500" />}
      <p className="mt-4 text-sm font-medium text-white">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-slate-400">{description}</p>}
    </GlassPanel>
  );
}

export function StatusPill({ label, tone = 'cyan' }: { label: string; tone?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet' }) {
  const map = {
    cyan: 'bg-cyan-500/15 text-cyan-200 ring-cyan-400/20',
    emerald: 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/20',
    amber: 'bg-amber-500/15 text-amber-200 ring-amber-400/20',
    rose: 'bg-rose-500/15 text-rose-200 ring-rose-400/20',
    violet: 'bg-violet-500/15 text-violet-200 ring-violet-400/20',
  };
  return <span className={clsx('inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1', map[tone])}>{label}</span>;
}
