'use client';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Pause, Play, RefreshCw, RotateCcw, Sparkles, Trash2, Zap } from 'lucide-react';
import { connectDecisionStream } from '../../lib/api';
import { useUiStore } from '../../lib/ui-store';
import { DecisionBadge, FeatureBar, GlassPanel, PageBackdrop, SectionHeader, StatusPill, TimelineCard } from '../../components/cockpit';
import type { SSEDecision } from '../../lib/types';
import { formatDistanceToNow, parseISO } from 'date-fns';

const MAX_ROWS = 200;

export default function LiveFeedPage() {
  const [events,  setEvents]  = useState<SSEDecision[]>([]);
  const [mode,    setMode]    = useState<'live' | 'replay'>('live');
  const [filter,  setFilter]  = useState<string>('ALL');
  const [connected, setConnected] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const archiveRef = useRef<SSEDecision[]>([]);
  const queueRef   = useRef<SSEDecision[]>([]);
  const { feedPaused, feedSpeed, setFeedPaused, setFeedSpeed } = useUiStore();

  useEffect(() => {
    const disconnect = connectDecisionStream((ev: SSEDecision) => {
      if (ev.type === 'connected') { setConnected(true); return; }
      if (ev.type === 'keepalive') return;
      if (ev.type !== 'decision')  return;
      archiveRef.current = [ev, ...archiveRef.current].slice(0, MAX_ROWS);
      queueRef.current = [ev, ...queueRef.current].slice(0, MAX_ROWS);
    });
    return disconnect;
  }, []);

  useEffect(() => {
    if (feedPaused) return;
    const interval = window.setInterval(() => {
      const next = queueRef.current.shift();
      if (next) {
        setEvents((prev) => [next, ...prev].slice(0, MAX_ROWS));
      } else if (mode === 'replay') {
        setMode('live');
      }
    }, Math.max(180, 900 / feedSpeed));
    return () => window.clearInterval(interval);
  }, [feedPaused, feedSpeed, mode]);

  const replay = () => {
    setMode('replay');
    setFeedPaused(false);
    setEvents([]);
    queueRef.current = [...archiveRef.current].reverse();
  };

  const clear = () => { setEvents([]); queueRef.current = []; archiveRef.current = []; setExpanded(null); };

  const visible = filter === 'ALL'
    ? events
    : events.filter(e => e.action === filter);

  const counts = events.reduce((acc, e) => {
    if (e.action) acc[e.action] = (acc[e.action] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const FILTERS = ['ALL', 'APPROVE', 'BLOCK', 'STEP_UP_AUTH', 'MANUAL_REVIEW'];
  const FILTER_LABELS: Record<string, string> = {
    ALL: 'All', APPROVE: 'Approve', BLOCK: 'Block',
    STEP_UP_AUTH: 'Step-Up', MANUAL_REVIEW: 'Review',
  };

  const streamStats = useMemo(() => ({
    total: events.length,
    risk: events.reduce((sum, ev) => sum + (ev.p_fraud ?? 0), 0) / Math.max(1, events.length),
    high: events.filter((ev) => (ev.p_fraud ?? 0) >= 0.7).length,
  }), [events]);

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-6">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Live decision feed</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Streaming system interface</h1>
              <p className="mt-2 text-sm text-slate-400">
                {connected ? 'Connected and rendering decisions in real time.' : 'Connecting to the decision stream…'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill label={connected ? 'Connected' : 'Connecting'} tone={connected ? 'emerald' : 'amber'} />
              <StatusPill label={`${streamStats.total} events`} tone="cyan" />
              <StatusPill label={`${streamStats.high} high risk`} tone="rose" />
            </div>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-4">
            <button onClick={() => setFeedPaused(!feedPaused)} className={`rounded-2xl px-4 py-3 text-sm font-medium transition ${feedPaused ? 'bg-emerald-500/15 text-emerald-100 ring-1 ring-emerald-400/20' : 'bg-amber-500/15 text-amber-100 ring-1 ring-amber-400/20'}`}>
              <div className="flex items-center justify-center gap-2">
                {feedPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                {feedPaused ? 'Resume stream' : 'Pause stream'}
              </div>
            </button>
            <button onClick={replay} className="rounded-2xl bg-white/5 px-4 py-3 text-sm font-medium text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8">
              <div className="flex items-center justify-center gap-2"><RotateCcw className="h-4 w-4" /> Replay latest 25</div>
            </button>
            <button onClick={clear} className="rounded-2xl bg-white/5 px-4 py-3 text-sm font-medium text-slate-100 ring-1 ring-white/10 transition hover:bg-white/8">
              <div className="flex items-center justify-center gap-2"><Trash2 className="h-4 w-4" /> Clear timeline</div>
            </button>
            <div className="rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10">
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.24em] text-slate-400">
                Speed
                <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
              </div>
              <div className="mt-2 flex gap-2">
                {[1, 2, 5].map((speed) => (
                  <button key={speed} onClick={() => setFeedSpeed(speed as 1 | 2 | 5)} className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${feedSpeed === speed ? 'bg-cyan-400 text-slate-950' : 'bg-white/5 text-slate-300 hover:text-white'}`}>
                    {speed}x
                  </button>
                ))}
              </div>
            </div>
          </div>
        </GlassPanel>

        <div className="grid gap-4 lg:grid-cols-[1fr_0.35fr]">
          <GlassPanel className="p-5">
            <SectionHeader title="Streaming timeline" subtitle="Monzo-style card feed with animated transitions and risk glow" />

            <div className="mt-4 flex flex-wrap gap-2">
              {FILTERS.map((f) => (
                <button key={f} onClick={() => setFilter(f)} className={`rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition ${filter === f ? 'bg-cyan-400 text-slate-950 ring-cyan-400/30' : 'bg-white/5 text-slate-300 ring-white/10 hover:bg-white/8'}`}>
                  {FILTER_LABELS[f]} {f !== 'ALL' && counts[f] ? `(${counts[f]})` : ''}
                </button>
              ))}
              <span className="ml-auto self-center text-xs text-slate-400">Showing {visible.length} of {events.length}</span>
            </div>

            <div className="mt-4 space-y-3">
              {visible.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-white/10 bg-white/5 px-6 py-16 text-center text-slate-400">
                  <Activity className="mx-auto h-10 w-10 text-slate-500" />
                  <p className="mt-4 text-sm font-medium text-white">Waiting for transactions…</p>
                  <p className="mt-1 text-sm text-slate-400">Cards will slide in as the live decision stream emits events.</p>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {visible.map((ev, i) => {
                    const txnId = ev.txn_id ?? `${i}`;
                    const riskTone = (ev.p_fraud ?? 0) >= 0.7 ? 'rose' : (ev.p_fraud ?? 0) >= 0.4 ? 'amber' : 'emerald';
                    return (
                      <motion.div key={`${txnId}-${i}`} initial={{ opacity: 0, y: -18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }} transition={{ duration: 0.22 }}>
                        <TimelineCard
                          title={`${ev.currency} ${Number(ev.amount ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                          subtitle={`${ev.customer_id} · ${txnId.slice(0, 12)}… · ${ev.decided_at ? formatDistanceToNow(parseISO(ev.decided_at), { addSuffix: true }) : 'just now'}`}
                          tone={riskTone as any}
                          expanded={expanded === txnId}
                          onToggle={() => setExpanded(expanded === txnId ? null : txnId)}
                          meta={<DecisionBadge action={ev.action ?? ''} size="xs" />}
                        >
                          <div className="grid gap-4 md:grid-cols-2">
                            <div className="space-y-3">
                              <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Decision signals</p>
                              <FeatureBar value={ev.p_fraud ?? 0} />
                              <FeatureBar value={ev.graph_risk ?? 0} />
                              <FeatureBar value={ev.anomaly ?? 0} />
                              <FeatureBar value={Math.min(1, (ev.latency_ms ?? 0) / 2000)} />
                            </div>
                            <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
                              <div className="flex items-center justify-between text-sm text-slate-300">
                                <span>Model confidence</span>
                                <span>{((1 - (ev.anomaly ?? 0) * 0.35) * 100).toFixed(1)}%</span>
                              </div>
                              <div className="flex items-center justify-between text-sm text-slate-300">
                                <span>Latency</span>
                                <span>{Number(ev.latency_ms ?? 0).toFixed(0)}ms</span>
                              </div>
                              <div className="flex items-center justify-between text-sm text-slate-300">
                                <span>Risk profile</span>
                                <span>{riskTone.toUpperCase()}</span>
                              </div>
                              <div className="rounded-2xl bg-slate-950/60 p-3 text-xs text-slate-300 ring-1 ring-white/10">
                                Streaming card expands to reveal the current risk posture, with proxy feature bars derived from live decision signals.
                              </div>
                            </div>
                          </div>
                        </TimelineCard>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              )}
            </div>
          </GlassPanel>

          <GlassPanel className="p-5">
            <SectionHeader title="Stream control" subtitle="Pause, replay and inspect the current lane" />
            <div className="mt-4 space-y-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between text-xs uppercase tracking-[0.24em] text-slate-400">
                  Mode
                  <StatusPill label={mode} tone={mode === 'live' ? 'emerald' : 'amber'} />
                </div>
                <p className="mt-2 text-sm text-slate-300">{mode === 'live' ? 'Live feed is consuming the SSE stream as it arrives.' : 'Replay mode is walking back through recent decisions.'}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between text-sm text-slate-300">
                  <span>Average risk</span>
                  <span>{(streamStats.risk * 100).toFixed(1)}%</span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/5">
                  <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-amber-400 to-rose-400" style={{ width: `${Math.min(100, streamStats.risk * 100)}%` }} />
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between text-sm text-slate-300"><span>Last event</span><span>{events[0] ? events[0].customer_id : '—'}</span></div>
                <div className="mt-2 text-xs text-slate-400">The detail panel tracks the current decision state, while the timeline preserves the streaming sequence.</div>
              </div>
            </div>
          </GlassPanel>
        </div>
      </div>
    </div>
  );
}
