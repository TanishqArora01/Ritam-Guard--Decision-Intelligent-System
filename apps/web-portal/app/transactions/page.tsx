'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, ShieldAlert } from 'lucide-react';
import { DecisionFlow } from '../../components/DecisionFlow';
import { ExplainabilityPanel } from '../../components/ExplainabilityPanel';
import { GraphViewer } from '../../components/GraphViewer';
import { TransactionStream } from '../../components/TransactionStream';
import { GlassPanel, PageBackdrop, SectionHeader, StatusPill } from '../../components/cockpit';
import {
  getDecisionTrace,
  getGraphForTransaction,
  listRecentTransactions,
  subscribeTransactionStream,
} from '../../lib/intelligence-api';
import type { Decision, DecisionTrace, FraudGraph } from '../../lib/types';

const BUFFER_LIMIT = 150;

export default function TransactionsPage() {
  const [rows, setRows] = useState<Decision[]>([]);
  const [selected, setSelected] = useState<Decision | null>(null);
  const [trace, setTrace] = useState<DecisionTrace | null>(null);
  const [graph, setGraph] = useState<FraudGraph | null>(null);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);

    const loadInitial = useCallback(async () => {
      setLoading(true);
      try {
        const data = await listRecentTransactions(1, 40);
        setRows(data.items);
        if (!selected && data.items[0]) setSelected(data.items[0]);
      } catch {
        setRows([]);
      } finally {
        setLoading(false);
      }
    }, [selected]);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  useEffect(() => {
    const disconnect = subscribeTransactionStream((event) => {
      setConnected(true);
      setRows((prev) => {
        if (paused) return prev;
        return [event, ...prev].slice(0, BUFFER_LIMIT);
      });
    });
    return () => disconnect();
  }, [paused]);

  useEffect(() => {
    let mounted = true;
    async function loadDetail() {
      if (!selected) {
        setTrace(null);
        setGraph(null);
        return;
      }
      const [nextTrace, nextGraph] = await Promise.all([
        getDecisionTrace(selected.txn_id),
        getGraphForTransaction(selected.txn_id),
      ]);
      if (!mounted) return;
      setTrace(nextTrace);
      setGraph(nextGraph);
    }
    loadDetail();
    return () => {
      mounted = false;
    };
  }, [selected]);

  const highRiskCount = useMemo(() => rows.filter((r) => r.p_fraud >= 0.7).length, [rows]);
  const anomalyCount = useMemo(() => rows.filter((r) => r.anomaly_score >= 0.6).length, [rows]);

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-5">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Transactions</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Fraud transaction stream and decision trace</h1>
              <p className="mt-2 text-sm text-slate-400">Live intelligence stream, stage-by-stage scoring, explainability, and graph context.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={`${rows.length} buffered`} tone="cyan" />
              <StatusPill label={`${highRiskCount} high risk`} tone="rose" />
              <StatusPill label={`${anomalyCount} anomalous`} tone="amber" />
              <button
                onClick={loadInitial}
                className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-2.5 text-sm text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
              </button>
            </div>
          </div>
        </GlassPanel>

        <TransactionStream
          items={rows}
          connected={connected}
          paused={paused}
          onTogglePaused={() => setPaused((p) => !p)}
          onSelect={(txn) => setSelected(txn)}
          selectedTxnId={selected?.txn_id}
        />

        <DecisionFlow trace={trace} />
        <ExplainabilityPanel trace={trace} />
        <GraphViewer graph={graph} />

        <GlassPanel className="p-5">
          <SectionHeader
            title="Analyst assist"
            subtitle="Selected transaction context for quick triage handoff"
          />
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
            {selected ? (
              <div className="grid gap-3 md:grid-cols-3">
                <p><span className="text-slate-400">Txn:</span> <span className="font-mono text-white">{selected.txn_id}</span></p>
                <p><span className="text-slate-400">Customer:</span> <span className="text-white">{selected.customer_id}</span></p>
                <p><span className="text-slate-400">Current action:</span> <span className="text-white">{selected.action}</span></p>
              </div>
            ) : (
              <p className="inline-flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-amber-300" /> Select a transaction from the stream to enable detailed analyst workflow context.</p>
            )}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
