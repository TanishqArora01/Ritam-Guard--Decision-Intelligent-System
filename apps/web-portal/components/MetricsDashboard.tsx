'use client';

import React, { useMemo } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { format, parseISO } from 'date-fns';
import type { MetricPoint } from '../lib/types';
import { AnimatedCounter, GlassPanel, MetricCard, SectionHeader } from './cockpit';
import { Activity, AlertTriangle, Gauge, ShieldAlert, Timer } from 'lucide-react';

export function MetricsDashboard({ points }: { points: MetricPoint[] }) {
  const normalized = useMemo(() => points.map((p) => ({
    ...p,
    label: p.bucket ? format(parseISO(p.bucket), 'HH:mm') : '',
  })), [points]);

  const latest = points[points.length - 1];
  const avgTps = points.length ? points.reduce((sum, row) => sum + row.tps, 0) / points.length : 0;
  const avgFraud = points.length ? points.reduce((sum, row) => sum + row.fraud_rate_pct, 0) / points.length : 0;
  const avgFp = points.length ? points.reduce((sum, row) => sum + row.false_positive_pct, 0) / points.length : 0;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard title="TPS" value={<AnimatedCounter value={avgTps} precision={2} />} icon={Activity} accent="cyan" />
        <MetricCard title="p95 latency" value={<AnimatedCounter value={latest?.p95_ms ?? 0} suffix="ms" />} icon={Timer} accent="amber" />
        <MetricCard title="p99 latency" value={<AnimatedCounter value={latest?.p99_ms ?? 0} suffix="ms" />} icon={Gauge} accent="rose" />
        <MetricCard title="Fraud rate" value={<AnimatedCounter value={avgFraud} precision={2} suffix="%" />} icon={ShieldAlert} accent="emerald" />
        <MetricCard title="False positives" value={<AnimatedCounter value={avgFp} precision={2} suffix="%" />} icon={AlertTriangle} accent="violet" />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <GlassPanel className="p-5">
          <SectionHeader title="Traffic and latency" subtitle="TPS and p95 latency trend" />
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={normalized}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12 }} />
              <Legend />
              <Line yAxisId="left" dataKey="tps" stroke="#22d3ee" strokeWidth={2.5} dot={false} name="TPS" />
              <Line yAxisId="right" dataKey="p95_ms" stroke="#fbbf24" strokeWidth={2.2} dot={false} name="p95 ms" />
            </LineChart>
          </ResponsiveContainer>
        </GlassPanel>

        <GlassPanel className="p-5">
          <SectionHeader title="Risk quality" subtitle="Fraud rate vs false positives vs drift" />
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={normalized}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12 }} />
              <Legend />
              <Area type="monotone" dataKey="fraud_rate_pct" stroke="#34d399" fill="#34d39944" name="Fraud rate %" />
              <Area type="monotone" dataKey="false_positive_pct" stroke="#a78bfa" fill="#a78bfa33" name="False positive %" />
              <Bar dataKey="drift_score" fill="#fb718533" name="Drift score" />
            </AreaChart>
          </ResponsiveContainer>
        </GlassPanel>
      </div>
    </div>
  );
}
