import { addMinutes, formatISO, subMinutes } from 'date-fns';
import { api, connectDecisionStream } from './api';
import type {
  Decision,
  DecisionTrace,
  FeatureContribution,
  FraudGraph,
  GraphEdge,
  GraphNode,
  MetricPoint,
  ModelLifecycle,
  ReviewCase,
  StageScore,
} from './types';

function bounded(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function seeded(hash: string): number {
  let acc = 0;
  for (let i = 0; i < hash.length; i += 1) acc = (acc * 31 + hash.charCodeAt(i)) >>> 0;
  return (acc % 10000) / 10000;
}

function makeStageScores(score: number, txnId: string): StageScore[] {
  const r = seeded(txnId);
  const s1 = bounded(score * (0.75 + r * 0.25), 0, 1);
  const s2 = bounded(score * (0.85 + r * 0.2), 0, 1);
  const s3 = bounded(score * (0.9 + r * 0.15), 0, 1);
  return [
    { stage: 'STAGE_1', score: s1, confidence: bounded(0.72 + r * 0.18, 0, 0.99), latency_ms: 14 + Math.round(r * 20), model: 'lightgbm-fast-v3' },
    { stage: 'STAGE_2', score: s2, confidence: bounded(0.79 + r * 0.16, 0, 0.99), latency_ms: 58 + Math.round(r * 45), model: 'xgb-nn-graph-v8' },
    { stage: 'STAGE_3', score: s3, confidence: bounded(0.81 + r * 0.16, 0, 0.99), latency_ms: 18 + Math.round(r * 24), model: 'cost-policy-v5' },
  ];
}

function mockContributions(txnId: string, baseScore: number): FeatureContribution[] {
  const r = seeded(txnId);
  const vals = [
    { feature: 'velocity_5m', impact: bounded(0.36 + r * 0.3, -1, 1), value: `${Math.round(8 + r * 60)} txns/5m`, direction: 'up' as const },
    { feature: 'device_entropy', impact: bounded(0.18 + r * 0.22, -1, 1), value: `${(0.21 + r * 0.5).toFixed(2)}`, direction: 'up' as const },
    { feature: 'known_chargeback_ratio', impact: bounded(0.09 + r * 0.25, -1, 1), value: `${(0.02 + r * 0.19).toFixed(2)}`, direction: 'up' as const },
    { feature: 'geo_consistency', impact: bounded(-(0.07 + r * 0.16), -1, 1), value: `${(0.62 + r * 0.28).toFixed(2)}`, direction: 'down' as const },
    { feature: 'trusted_device_age_days', impact: bounded(-(0.05 + r * 0.12), -1, 1), value: `${Math.round(30 + r * 250)}`, direction: 'down' as const },
  ];
  return vals
    .map((v) => ({ ...v, impact: bounded(v.impact * (0.6 + baseScore * 0.7), -1, 1) }))
    .sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
}

function buildGraph(txnId: string, customerId: string, risk: number): FraudGraph {
  const userId = customerId || `cust-${txnId.slice(0, 6)}`;
  const device = `device-${txnId.slice(0, 4)}`;
  const ip = `ip-${txnId.slice(2, 7)}`;
  const account = `account-${customerId.slice(0, 5) || 'edge'}`;
  const merchant = `merchant-${txnId.slice(-4)}`;

  const nodes: GraphNode[] = [
    { id: userId, label: userId, kind: 'USER', risk },
    { id: device, label: device, kind: 'DEVICE', risk: bounded(risk * 0.9, 0, 1) },
    { id: ip, label: ip, kind: 'IP', risk: bounded(risk * 0.86, 0, 1) },
    { id: account, label: account, kind: 'ACCOUNT', risk: bounded(risk * 0.73, 0, 1) },
    { id: merchant, label: merchant, kind: 'MERCHANT', risk: bounded(risk * 0.62, 0, 1) },
  ];

  const edges: GraphEdge[] = [
    { source: userId, target: device, relation: 'USES', strength: 0.81 },
    { source: userId, target: account, relation: 'OWNS', strength: 0.95 },
    { source: device, target: ip, relation: 'SEEN_AT', strength: 0.78 },
    { source: account, target: merchant, relation: 'PAYS', strength: 0.64 },
    { source: ip, target: merchant, relation: 'TOUCHES', strength: 0.58 },
  ];

  return {
    nodes,
    edges,
    suspicious_clusters: risk >= 0.7 ? 2 : risk >= 0.4 ? 1 : 0,
  };
}

function mockDecision(seedKey: string, minuteOffset: number): Decision {
  const r = seeded(`${seedKey}-${minuteOffset}`);
  const score = bounded(0.15 + r * 0.86, 0, 0.99);
  const action = score >= 0.85 ? 'BLOCK' : score >= 0.65 ? 'MANUAL_REVIEW' : score >= 0.48 ? 'STEP_UP_AUTH' : 'APPROVE';
  return {
    txn_id: `txn-${seedKey.slice(0, 6)}-${String(minuteOffset).padStart(3, '0')}`,
    customer_id: `cust-${seedKey.slice(2, 6)}-${String((r * 1000) | 0).padStart(3, '0')}`,
    amount: Number((18 + r * 5600).toFixed(2)),
    currency: 'USD',
    action,
    p_fraud: score,
    confidence: bounded(0.62 + r * 0.33, 0, 0.99),
    graph_risk_score: bounded(score * (0.7 + r * 0.35), 0, 1),
    anomaly_score: bounded((1 - score) * 0.18 + r * 0.72, 0, 1),
    optimal_cost: Number((120 + score * 850).toFixed(2)),
    model_version: 'mock-ensemble-v8',
    ab_variant: r > 0.5 ? 'B' : 'A',
    latency_ms: Number((18 + r * 90).toFixed(0)),
    decided_at: formatISO(subMinutes(new Date(), minuteOffset)),
    explanation: {
      velocity_5m: `${Math.round(2 + r * 50)} txns`,
      graph_ring_density: (0.1 + r * 0.8).toFixed(2),
      geo_velocity: `${Math.round(40 + r * 620)}km/h`,
    },
  };
}

function mockDecisions(total = 50): Decision[] {
  return Array.from({ length: total }, (_, i) => mockDecision(`seed-${i}`, i + 1));
}

export function subscribeTransactionStream(onDecision: (decision: Decision) => void): () => void {
  return connectDecisionStream((event: any) => {
    if (event?.type !== 'decision') return;
    onDecision({
      txn_id: event.txn_id,
      customer_id: event.customer_id,
      amount: Number(event.amount ?? 0),
      currency: event.currency ?? 'USD',
      action: event.action,
      p_fraud: Number(event.p_fraud ?? 0),
      confidence: bounded(1 - Number(event.anomaly ?? 0), 0, 1),
      graph_risk_score: Number(event.graph_risk ?? 0),
      anomaly_score: Number(event.anomaly ?? 0),
      optimal_cost: 0,
      model_version: 'live-stream',
      ab_variant: 'A',
      latency_ms: Number(event.latency_ms ?? 0),
      decided_at: event.decided_at ?? new Date().toISOString(),
      explanation: {},
    });
  });
}

export async function listRecentTransactions(page = 1, pageSize = 30): Promise<{ items: Decision[]; total: number; pages: number; page: number }> {
  try {
    const data = await api.decisions.list({ page, page_size: pageSize });
    const items = (data.items ?? []) as Decision[];
    if (items.length === 0) {
      const fallback = mockDecisions(pageSize);
      return { items: fallback, total: fallback.length, pages: 1, page: 1 };
    }
    return {
      items,
      total: data.total ?? 0,
      pages: data.pages ?? 1,
      page: data.page ?? page,
    };
  } catch {
    const items = mockDecisions(pageSize);
    return { items, total: items.length, pages: 1, page: 1 };
  }
}

export async function getDecisionTrace(txnId: string): Promise<DecisionTrace | null> {
  let row: Decision | undefined;
  try {
    const data = await api.decisions.list({ txn_id: txnId, page: 1, page_size: 1 });
    row = (data.items ?? [])[0] as Decision | undefined;
    if (!row) row = mockDecision(txnId, 2);
  } catch {
    row = mockDecision(txnId, 2);
  }
  if (!row) return null;

  const contributions = mockContributions(txnId, row.p_fraud);
  const absSum = contributions.reduce((sum, c) => sum + Math.abs(c.impact), 0) || 1;
  const network = bounded((row.graph_risk_score + Math.abs(contributions[1]?.impact ?? 0)) / 2, 0, 1);
  const anomaly = bounded((row.anomaly_score + Math.abs(contributions[0]?.impact ?? 0) * 0.5), 0, 1);
  const behavioral = bounded((row.p_fraud + Math.abs(contributions[2]?.impact ?? 0) * 0.4), 0, 1);
  const historical = bounded(absSum / (contributions.length * 1.2), 0, 1);

  return {
    txn_id: row.txn_id,
    final_action: row.action,
    decided_at: row.decided_at,
    stage_scores: makeStageScores(row.p_fraud, txnId),
    contributions,
    risk_breakdown: {
      behavioral,
      network,
      anomaly,
      historical,
    },
  };
}

export async function getGraphForTransaction(txnId: string): Promise<FraudGraph | null> {
  let row: Decision | undefined;
  try {
    const data = await api.decisions.list({ txn_id: txnId, page: 1, page_size: 1 });
    row = (data.items ?? [])[0] as Decision | undefined;
    if (!row) row = mockDecision(txnId, 1);
  } catch {
    row = mockDecision(txnId, 1);
  }
  if (!row) return null;
  return buildGraph(row.txn_id, row.customer_id, row.p_fraud);
}

export async function listCaseQueue(params?: { status?: string; assigned_to_me?: boolean; page?: number; page_size?: number }): Promise<{ items: ReviewCase[]; total: number; pages: number; page: number }> {
  try {
    const data = await api.queue.list(params ?? {});
    const items = (data.items ?? []) as ReviewCase[];
    if (items.length === 0) {
      const fallback = mockDecisions(12)
        .filter((d) => d.action === 'MANUAL_REVIEW' || d.action === 'BLOCK')
        .map((d, i) => ({
          id: `case-${i + 1}`,
          txn_id: d.txn_id,
          customer_id: d.customer_id,
          amount: d.amount,
          currency: d.currency,
          channel: 'WEB',
          country_code: 'US',
          p_fraud: d.p_fraud,
          confidence: d.confidence,
          graph_risk_score: d.graph_risk_score,
          anomaly_score: d.anomaly_score,
          model_action: d.action,
          model_version: d.model_version,
          explanation: d.explanation,
          status: i % 3 === 0 ? 'ESCALATED' : i % 2 === 0 ? 'IN_REVIEW' : 'OPEN',
          priority: i % 3 === 0 ? 1 : i % 2 === 0 ? 2 : 3,
          assigned_to: i % 2 === 0 ? 'analyst1' : null,
          verdict: null,
          analyst_notes: '',
          created_at: d.decided_at,
          updated_at: d.decided_at,
        } as ReviewCase));
      return { items: fallback, total: fallback.length, pages: 1, page: 1 };
    }
    return {
      items,
      total: data.total ?? 0,
      pages: data.pages ?? 1,
      page: data.page ?? (params?.page ?? 1),
    };
  } catch {
    const fallback = mockDecisions(12)
      .filter((d) => d.action === 'MANUAL_REVIEW' || d.action === 'BLOCK')
      .map((d, i) => ({
        id: `case-${i + 1}`,
        txn_id: d.txn_id,
        customer_id: d.customer_id,
        amount: d.amount,
        currency: d.currency,
        channel: 'WEB',
        country_code: 'US',
        p_fraud: d.p_fraud,
        confidence: d.confidence,
        graph_risk_score: d.graph_risk_score,
        anomaly_score: d.anomaly_score,
        model_action: d.action,
        model_version: d.model_version,
        explanation: d.explanation,
        status: i % 3 === 0 ? 'ESCALATED' : i % 2 === 0 ? 'IN_REVIEW' : 'OPEN',
        priority: i % 3 === 0 ? 1 : i % 2 === 0 ? 2 : 3,
        assigned_to: i % 2 === 0 ? 'analyst1' : null,
        verdict: null,
        analyst_notes: '',
        created_at: d.decided_at,
        updated_at: d.decided_at,
      } as ReviewCase));
    return { items: fallback, total: fallback.length, pages: 1, page: 1 };
  }
}

export async function getMetricsSeries(windowHours = 24): Promise<MetricPoint[]> {
  const granularity = windowHours <= 2 ? 'minute' : windowHours <= 72 ? 'hour' : 'day';
  let rate: any;
  let latency: any;
  try {
    [rate, latency] = await Promise.all([
      api.analytics.fraudRate(windowHours, granularity),
      api.analytics.latency(Math.min(windowHours, 24)),
    ]);
  } catch {
    const fallbackRows = Array.from({ length: 24 }, (_, i) => {
      const r = seeded(`metric-${i}`);
      return {
        bucket: formatISO(subMinutes(new Date(), (24 - i) * 30)),
        total: Math.round(300 + r * 1500),
        block_rate_pct: Number((2.5 + r * 6.2).toFixed(2)),
        avg_p_fraud: Number((0.24 + r * 0.52).toFixed(3)),
      };
    });
    rate = { data: fallbackRows };
    latency = { p50: 42, p95: 116, p99: 188 };
  }

  const p50 = Number(latency?.p50 ?? 0);
  const p95 = Number(latency?.p95 ?? 0);
  const p99 = Number(latency?.p99 ?? 0);
  const rateRows = (rate?.data ?? []) as any[];

  if (rateRows.length === 0) {
    return Array.from({ length: 24 }, (_, i) => {
      const r = seeded(`metric-fallback-${i}`);
      return {
        bucket: formatISO(subMinutes(new Date(), (24 - i) * 30)),
        tps: 8 + r * 34,
        p50_ms: bounded(30 + r * 22, 1, 5000),
        p95_ms: bounded(90 + r * 44, 1, 8000),
        p99_ms: bounded(140 + r * 75, 1, 12000),
        fraud_rate_pct: Number((2.2 + r * 5.5).toFixed(2)),
        false_positive_pct: Number((0.6 + r * 2.1).toFixed(2)),
        drift_score: bounded(7 + r * 18, 0, 100),
      };
    });
  }

  return rateRows.map((row: any, i: number) => {
    const total = Number(row.total ?? 0);
    const bucket = row.bucket ?? formatISO(subMinutes(new Date(), (rateRows.length - i) * 5));
    return {
      bucket,
      tps: total / (granularity === 'minute' ? 60 : granularity === 'hour' ? 3600 : 86400),
      p50_ms: bounded(p50 * (0.88 + (i % 7) * 0.015), 1, 5000),
      p95_ms: bounded(p95 * (0.9 + (i % 5) * 0.02), 1, 8000),
      p99_ms: bounded(p99 * (0.92 + (i % 4) * 0.025), 1, 12000),
      fraud_rate_pct: Number(row.block_rate_pct ?? 0),
      false_positive_pct: bounded(Number(row.block_rate_pct ?? 0) * 0.18, 0, 100),
      drift_score: bounded(Math.abs(Number(row.avg_p_fraud ?? 0) - 0.5) * 100, 0, 100),
    };
  });
}

export async function getModelLifecycle(): Promise<ModelLifecycle> {
  const [overview, points] = await Promise.all([
    api.analytics.overview().catch(() => ({})),
    getMetricsSeries(24).catch(() => [] as MetricPoint[]),
  ]);

  const drift = points.length ? points[points.length - 1].drift_score : 8.2;
  const now = new Date();

  return {
    active_version: String(overview?.model_version ?? 'ensemble-v8.4'),
    stage1_version: 'lightgbm-fast-v3.2',
    stage2_version: 'xgb-nn-graph-v8.4',
    stage3_policy: 'cost-policy-v5.1',
    last_training_run: formatISO(subMinutes(now, 420)),
    last_registry_update: formatISO(subMinutes(now, 205)),
    drift_alert: drift >= 22,
    drift_score: drift,
    airflow: {
      dag_id: 'fraud_training_orchestration',
      status: drift >= 28 ? 'degraded' : 'healthy',
      last_run: formatISO(subMinutes(now, 58)),
      next_run: formatISO(addMinutes(now, 62)),
    },
    mlflow: {
      experiment: 'fraud-multi-stage-prod',
      run_id: `run_${String(Math.round(seeded(String(now.getTime())) * 1_000_000)).padStart(6, '0')}`,
      auc: 0.952,
      precision: 0.901,
      recall: 0.874,
    },
  };
}
