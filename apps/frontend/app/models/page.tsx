'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Boxes, Brain, Workflow } from 'lucide-react';
import { MetricsDashboard } from '../../components/MetricsDashboard';
import { GlassPanel, PageBackdrop, SectionHeader, StatusPill } from '../../components/cockpit';
import { getMetricsSeries, getModelLifecycle } from '../../lib/intelligence-api';
import { useAuth } from '../../lib/auth-context';
import type { MetricPoint, ModelLifecycle } from '../../lib/types';

export default function ModelsPage() {
  const { user } = useAuth();
  const [lifecycle, setLifecycle] = useState<ModelLifecycle | null>(null);
  const [metrics, setMetrics] = useState<MetricPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextLifecycle, nextMetrics] = await Promise.all([
        getModelLifecycle(),
        getMetricsSeries(24),
      ]);
      setLifecycle(nextLifecycle);
      setMetrics(nextMetrics);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (user?.role === 'BANK_PARTNER') {
    return (
      <div className="relative min-h-full px-4 py-6 lg:px-6">
        <PageBackdrop />
        <div className="relative z-10 mx-auto max-w-3xl">
          <GlassPanel className="p-6">
            <SectionHeader title="Access restricted" subtitle="Model lifecycle controls are available for analyst, ops, and admin roles." />
          </GlassPanel>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-full px-4 py-6 lg:px-6">
      <PageBackdrop />
      <div className="relative z-10 mx-auto max-w-7xl space-y-5">
        <GlassPanel className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Models and pipelines</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">Model lifecycle visibility</h1>
              <p className="mt-2 text-sm text-slate-400">MLflow registry, Airflow orchestration health, drift indicators, and live serving metrics.</p>
            </div>
            {lifecycle && (
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill label={`Active ${lifecycle.active_version}`} tone="cyan" />
                <StatusPill label={lifecycle.drift_alert ? 'Drift alert' : 'Drift stable'} tone={lifecycle.drift_alert ? 'rose' : 'emerald'} />
              </div>
            )}
          </div>
        </GlassPanel>

        {loading || !lifecycle ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <GlassPanel className="h-40 animate-shimmer" />
            <GlassPanel className="h-40 animate-shimmer" />
            <GlassPanel className="h-40 animate-shimmer" />
            <GlassPanel className="h-40 animate-shimmer" />
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <GlassPanel className="p-4">
                <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400"><Brain className="h-4 w-4 text-cyan-300" /> Stage 1</p>
                <p className="mt-2 text-lg font-semibold text-white">{lifecycle.stage1_version}</p>
                <p className="mt-1 text-xs text-slate-400">Fast filter model</p>
              </GlassPanel>
              <GlassPanel className="p-4">
                <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400"><Boxes className="h-4 w-4 text-violet-300" /> Stage 2</p>
                <p className="mt-2 text-lg font-semibold text-white">{lifecycle.stage2_version}</p>
                <p className="mt-1 text-xs text-slate-400">Ensemble + graph intelligence</p>
              </GlassPanel>
              <GlassPanel className="p-4">
                <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400"><Workflow className="h-4 w-4 text-amber-300" /> Stage 3</p>
                <p className="mt-2 text-lg font-semibold text-white">{lifecycle.stage3_policy}</p>
                <p className="mt-1 text-xs text-slate-400">Cost-based policy engine</p>
              </GlassPanel>
              <GlassPanel className="p-4">
                <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400"><AlertTriangle className={`h-4 w-4 ${lifecycle.drift_alert ? 'text-rose-300' : 'text-emerald-300'}`} /> Drift score</p>
                <p className="mt-2 text-lg font-semibold text-white">{lifecycle.drift_score.toFixed(1)}</p>
                <p className="mt-1 text-xs text-slate-400">{lifecycle.drift_alert ? 'Investigate retraining' : 'Within expected variance'}</p>
              </GlassPanel>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <GlassPanel className="p-5">
                <SectionHeader title="MLflow snapshot" subtitle="Current model registry and validation metrics" />
                <div className="mt-4 space-y-2 text-sm text-slate-300">
                  <p><span className="text-slate-500">Experiment:</span> {lifecycle.mlflow.experiment}</p>
                  <p><span className="text-slate-500">Run:</span> <span className="font-mono">{lifecycle.mlflow.run_id}</span></p>
                  <p><span className="text-slate-500">AUC:</span> {lifecycle.mlflow.auc}</p>
                  <p><span className="text-slate-500">Precision:</span> {lifecycle.mlflow.precision}</p>
                  <p><span className="text-slate-500">Recall:</span> {lifecycle.mlflow.recall}</p>
                  <p><span className="text-slate-500">Last training:</span> {new Date(lifecycle.last_training_run).toLocaleString()}</p>
                  <p><span className="text-slate-500">Registry update:</span> {new Date(lifecycle.last_registry_update).toLocaleString()}</p>
                </div>
              </GlassPanel>

              <GlassPanel className="p-5">
                <SectionHeader title="Airflow orchestration" subtitle="DAG health and scheduling status" />
                <div className="mt-4 space-y-2 text-sm text-slate-300">
                  <p><span className="text-slate-500">DAG:</span> {lifecycle.airflow.dag_id}</p>
                  <p><span className="text-slate-500">Status:</span> {lifecycle.airflow.status}</p>
                  <p><span className="text-slate-500">Last run:</span> {new Date(lifecycle.airflow.last_run).toLocaleString()}</p>
                  <p><span className="text-slate-500">Next run:</span> {new Date(lifecycle.airflow.next_run).toLocaleString()}</p>
                  <p className="text-xs text-slate-500">Hooks are ready for direct Airflow and MLflow API integration in production.</p>
                </div>
              </GlassPanel>
            </div>

            <MetricsDashboard points={metrics} />
          </>
        )}
      </div>
    </div>
  );
}
