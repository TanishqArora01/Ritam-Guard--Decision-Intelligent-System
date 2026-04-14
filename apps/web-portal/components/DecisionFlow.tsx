'use client';

import React from 'react';
import { Clock3, Gauge, MoveRight } from 'lucide-react';
import type { DecisionTrace } from '../lib/types';
import { DecisionBadge, GlassPanel, SectionHeader } from './cockpit';

export function DecisionFlow({ trace }: { trace: DecisionTrace | null }) {
  if (!trace) {
    return (
      <GlassPanel className="p-5">
        <SectionHeader title="Decision pipeline" subtitle="Txn -> Stage 1 -> Stage 2 -> Stage 3 -> Final decision" />
        <p className="mt-4 text-sm text-slate-400">Select a transaction to inspect stage-level intelligence.</p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="p-5">
      <SectionHeader
        title="Decision pipeline"
        subtitle={`Transaction ${trace.txn_id.slice(0, 16)}... evaluated through the multi-stage stack`}
      />
      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        {trace.stage_scores.map((stage, index) => (
          <div key={stage.stage} className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{stage.stage.replace('_', ' ')}</p>
            <p className="mt-1 text-xl font-semibold text-white">{(stage.score * 100).toFixed(1)}%</p>
            <p className="mt-1 text-xs text-slate-300">{stage.model}</p>
            <div className="mt-3 space-y-1 text-xs text-slate-400">
              <p className="inline-flex items-center gap-1"><Gauge className="h-3.5 w-3.5 text-cyan-300" /> Confidence {(stage.confidence * 100).toFixed(1)}%</p>
              <p className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5 text-amber-300" /> {stage.latency_ms}ms</p>
            </div>
            {index < trace.stage_scores.length - 1 && <MoveRight className="mt-3 h-4 w-4 text-slate-500" />}
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between rounded-2xl border border-white/10 bg-slate-900/60 px-4 py-3">
        <p className="text-sm text-slate-300">Final decision</p>
        <DecisionBadge action={trace.final_action} size="md" />
      </div>
    </GlassPanel>
  );
}
