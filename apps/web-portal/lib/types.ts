// lib/types.ts — TypeScript types matching app-backend schemas

export type Role = 'ANALYST' | 'OPS_MANAGER' | 'ADMIN' | 'BANK_PARTNER';
export type Action = 'APPROVE' | 'BLOCK' | 'STEP_UP_AUTH' | 'MANUAL_REVIEW';
export type CaseStatus = 'OPEN' | 'IN_REVIEW' | 'RESOLVED' | 'ESCALATED';
export type CaseVerdict = 'CONFIRMED_FRAUD' | 'FALSE_POSITIVE' | 'INCONCLUSIVE';

export interface AuthUser {
  id:       string;
  username: string;
  email:    string;
  role:     Role;
  org_id:   string | null;
}

export interface TokenResponse {
  access_token:  string;
  refresh_token: string;
  token_type:    string;
  role:          Role;
  username:      string;
}

export interface Decision {
  txn_id:           string;
  customer_id:      string;
  amount:           number;
  currency:         string;
  action:           Action;
  p_fraud:          number;
  confidence:       number;
  graph_risk_score: number;
  anomaly_score:    number;
  optimal_cost:     number;
  model_version:    string;
  ab_variant:       string;
  latency_ms:       number;
  decided_at:       string;
  explanation:      Record<string, string>;
}

export interface ReviewCase {
  id:               string;
  txn_id:           string;
  customer_id:      string;
  amount:           number;
  currency:         string;
  channel:          string;
  country_code:     string;
  p_fraud:          number;
  confidence:       number;
  graph_risk_score: number;
  anomaly_score:    number;
  model_action:     Action;
  model_version:    string;
  explanation:      Record<string, string>;
  status:           CaseStatus;
  priority:         1 | 2 | 3;
  assigned_to:      string | null;
  verdict:          CaseVerdict | null;
  analyst_notes:    string;
  created_at:       string;
  updated_at:       string;
}

export interface PagedResponse<T> {
  items:     T[];
  total:     number;
  page:      number;
  page_size: number;
  pages:     number;
}

export interface OverviewStats {
  total_decisions:  number;
  blocked:          number;
  approved:         number;
  step_up:          number;
  manual_review:    number;
  avg_p_fraud:      number;
  block_rate_pct:   number;
  avg_latency_ms:   number;
  p95_latency_ms:   number;
}

export interface FraudRateBucket {
  bucket:         string;
  total:          number;
  blocked:        number;
  approved:       number;
  step_up:        number;
  manual_review:  number;
  block_rate_pct: number;
  avg_p_fraud:    number;
  avg_latency_ms: number;
}

export interface SSEDecision {
  type:        'decision' | 'connected' | 'keepalive';
  txn_id?:     string;
  customer_id?:string;
  amount?:     number;
  currency?:   string;
  action?:     Action;
  p_fraud?:    number;
  graph_risk?: number;
  anomaly?:    number;
  latency_ms?: number;
  decided_at?: string;
}

export interface StageScore {
  stage: 'STAGE_1' | 'STAGE_2' | 'STAGE_3';
  score: number;
  confidence: number;
  latency_ms: number;
  model: string;
}

export interface FeatureContribution {
  feature: string;
  impact: number;
  value: string;
  direction: 'up' | 'down';
}

export interface DecisionTrace {
  txn_id: string;
  final_action: Action;
  decided_at: string;
  stage_scores: StageScore[];
  contributions: FeatureContribution[];
  risk_breakdown: {
    behavioral: number;
    network: number;
    anomaly: number;
    historical: number;
  };
}

export interface GraphNode {
  id: string;
  label: string;
  kind: 'USER' | 'DEVICE' | 'IP' | 'ACCOUNT' | 'MERCHANT';
  risk: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  strength: number;
}

export interface FraudGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  suspicious_clusters: number;
}

export interface MetricPoint {
  bucket: string;
  tps: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  fraud_rate_pct: number;
  false_positive_pct: number;
  drift_score: number;
}

export interface ModelLifecycle {
  active_version: string;
  stage1_version: string;
  stage2_version: string;
  stage3_policy: string;
  last_training_run: string;
  last_registry_update: string;
  drift_alert: boolean;
  drift_score: number;
  airflow: {
    dag_id: string;
    status: 'healthy' | 'degraded' | 'failed';
    last_run: string;
    next_run: string;
  };
  mlflow: {
    experiment: string;
    run_id: string;
    auc: number;
    precision: number;
    recall: number;
  };
}
