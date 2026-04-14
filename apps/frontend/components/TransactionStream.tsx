'use client';

import React from 'react';
import { AlertTriangle, PauseCircle, PlayCircle, Radio } from 'lucide-react';
import type { Decision } from '../lib/types';
import { DecisionBadge, GlassPanel, SectionHeader, StatusPill } from './cockpit';

export function TransactionStream({
  items,
  connected,
  paused,
  onTogglePaused,
  onSelect,
  selectedTxnId,
}: {
  items: Decision[];
  connected: boolean;
  paused: boolean;
  onTogglePaused: () => void;
  onSelect: (txn: Decision) => void;
  selectedTxnId?: string;
}) {
  return (
    <GlassPanel className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          title="Real-time transaction stream"
          subtitle="SSE-backed decision events with high-risk and anomaly highlighting"
        />
        <div className="flex items-center gap-2">
          <StatusPill label={connected ? 'Connected' : 'Disconnected'} tone={connected ? 'emerald' : 'rose'} />
          <button
            onClick={onTogglePaused}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 transition hover:bg-white/10"
          >
            {paused ? <PlayCircle className="h-4 w-4" /> : <PauseCircle className="h-4 w-4" />}
            {paused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto rounded-2xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-xs uppercase tracking-[0.2em] text-slate-400">
            <tr>
              <th className="px-3 py-3 text-left">Txn</th>
              <th className="px-3 py-3 text-left">Customer</th>
              <th className="px-3 py-3 text-left">Amount</th>
              <th className="px-3 py-3 text-left">Decision</th>
              <th className="px-3 py-3 text-left">Risk</th>
              <th className="px-3 py-3 text-left">Anomaly</th>
              <th className="px-3 py-3 text-left">Latency</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-slate-400">
                  Waiting for stream events...
                </td>
              </tr>
            )}
            {items.map((row) => {
              const highRisk = row.p_fraud >= 0.7;
              const anomalous = row.anomaly_score >= 0.6;
              return (
                <tr
                  key={row.txn_id}
                  onClick={() => onSelect(row)}
                  className={`cursor-pointer transition ${
                    selectedTxnId === row.txn_id
                      ? 'bg-cyan-500/10'
                      : highRisk
                        ? 'bg-rose-500/7 hover:bg-rose-500/12'
                        : anomalous
                          ? 'bg-amber-500/8 hover:bg-amber-500/12'
                          : 'hover:bg-white/5'
                  }`}
                >
                  <td className="px-3 py-3 font-mono text-xs text-slate-300">{row.txn_id.slice(0, 12)}...</td>
                  <td className="px-3 py-3 text-white">{row.customer_id}</td>
                  <td className="px-3 py-3 text-slate-200">{row.currency} {Number(row.amount).toLocaleString()}</td>
                  <td className="px-3 py-3"><DecisionBadge action={row.action} size="xs" /></td>
                  <td className="px-3 py-3">
                    <span className={`font-mono text-xs ${highRisk ? 'text-rose-300' : row.p_fraud >= 0.4 ? 'text-amber-300' : 'text-emerald-300'}`}>
                      {(row.p_fraud * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] ${anomalous ? 'bg-amber-500/15 text-amber-200' : 'bg-white/5 text-slate-300'}`}>
                      {anomalous && <AlertTriangle className="h-3 w-3" />}
                      {(row.anomaly_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-400">{row.latency_ms.toFixed(0)}ms</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
        <span className="inline-flex items-center gap-1"><Radio className="h-3.5 w-3.5 text-cyan-300" /> Live flow</span>
        <span>{items.length} rows buffered</span>
      </div>
    </GlassPanel>
  );
}
