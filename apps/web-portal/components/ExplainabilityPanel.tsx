'use client';

import React from 'react';
import type { DecisionTrace } from '../lib/types';
import { FeatureBar, GlassPanel, SectionHeader } from './cockpit';

function riskRows(trace: DecisionTrace) {
  return [
    { key: 'behavioral', label: 'Behavioral risk', value: trace.risk_breakdown.behavioral },
    { key: 'network', label: 'Graph/network risk', value: trace.risk_breakdown.network },
    { key: 'anomaly', label: 'Anomaly risk', value: trace.risk_breakdown.anomaly },
    { key: 'historical', label: 'Historical chargeback risk', value: trace.risk_breakdown.historical },
  ];
}

export function ExplainabilityPanel({ trace }: { trace: DecisionTrace | null }) {
  if (!trace) {
    return (
      <GlassPanel className="p-5">
        <SectionHeader title="Explainability panel" subtitle="SHAP-style factors and risk decomposition" />
        <p className="mt-4 text-sm text-slate-400">Select a transaction to view feature contribution and risk breakdown.</p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="p-5">
      <SectionHeader title="Explainability panel" subtitle="Top factors driving the final decision" />
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Feature contributions</p>
          {trace.contributions.slice(0, 6).map((item) => (
            <div key={item.feature} className="rounded-xl bg-slate-950/60 p-3 ring-1 ring-white/10">
              <div className="mb-2 flex items-center justify-between text-xs text-slate-300">
                <span className="font-mono">{item.feature}</span>
                <span className={item.direction === 'up' ? 'text-rose-300' : 'text-emerald-300'}>
                  {item.direction === 'up' ? '+' : '-'}{(Math.abs(item.impact) * 100).toFixed(1)}%
                </span>
              </div>
              <FeatureBar value={Math.abs(item.impact)} />
              <p className="mt-2 text-xs text-slate-400">Value: {item.value}</p>
            </div>
          ))}
        </div>

        <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Risk breakdown</p>
          {riskRows(trace).map((row) => (
            <div key={row.key} className="rounded-xl bg-slate-950/60 p-3 ring-1 ring-white/10">
              <div className="mb-2 flex items-center justify-between text-xs text-slate-300">
                <span>{row.label}</span>
                <span className="font-mono text-white">{(row.value * 100).toFixed(1)}%</span>
              </div>
              <FeatureBar value={row.value} />
            </div>
          ))}
          <p className="text-xs text-slate-500">
            Traceability note: all factors are attached to this decision id and are suitable for audit and analyst review workflows.
          </p>
        </div>
      </div>
    </GlassPanel>
  );
}
