// TypeScript interfaces matching backend Pydantic models

export interface RiskScore {
  stage1_score: number
  stage2_score: number
  final_score: number
  decision: 'APPROVE' | 'REVIEW' | 'BLOCK'
  confidence: number
  stage1_features: Record<string, number>
  stage2_features: Record<string, number>
  explanation: FeatureExplanation[]
}

export interface FeatureExplanation {
  feature: string
  contribution: number
  direction: 'increase' | 'decrease'
}

export interface GraphNode {
  id: string
  type: 'user' | 'device' | 'ip' | 'account'
  label: string
  risk_score: number
  suspicious: boolean
}

export interface GraphEdge {
  source: string
  target: string
  weight: number
  type: string
}

export interface TransactionGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Transaction {
  id: string
  timestamp: string
  user_id: string
  amount: number
  merchant: string
  merchant_category: string
  location: string
  device_id: string
  ip_address: string
  risk_score: RiskScore
  graph: TransactionGraph
  status: 'pending' | 'approved' | 'blocked' | 'under_review'
}

export interface Case {
  id: string
  transaction_id: string
  assigned_to: string
  status: 'open' | 'investigating' | 'resolved' | 'escalated'
  priority: 'low' | 'medium' | 'high' | 'critical'
  created_at: string
  updated_at: string
  notes: string[]
  resolution: string | null
}

export interface Metrics {
  tps: number
  latency_p50: number
  latency_p95: number
  latency_p99: number
  fraud_rate: number
  false_positive_rate: number
  total_transactions: number
  blocked_transactions: number
  approved_transactions: number
  under_review_transactions: number
}

export interface TransactionsResponse {
  total: number
  transactions: Transaction[]
}

export interface CasesResponse {
  total: number
  cases: Case[]
}

export interface MetricsHistoryResponse {
  history: Metrics[]
  count: number
}

export interface TokenResponse {
  access_token: string
  token_type: string
}
