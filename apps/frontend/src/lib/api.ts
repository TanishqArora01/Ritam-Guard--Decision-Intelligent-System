import type {
  Transaction,
  TransactionsResponse,
  Case,
  CasesResponse,
  Metrics,
  MetricsHistoryResponse,
  TokenResponse,
} from '@/types'

const API_URL =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')
    : (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getTransactions: (params?: {
    limit?: number
    offset?: number
    status?: string
  }): Promise<TransactionsResponse> => {
    const qs = new URLSearchParams()
    if (params?.limit !== undefined) qs.set('limit', String(params.limit))
    if (params?.offset !== undefined) qs.set('offset', String(params.offset))
    if (params?.status) qs.set('status', params.status)
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<TransactionsResponse>(`/api/transactions${query}`)
  },

  getTransaction: (id: string): Promise<Transaction> =>
    request<Transaction>(`/api/transactions/${id}`),

  getDecision: (id: string): Promise<{
    transaction_id: string
    risk_score: Transaction['risk_score']
    graph: Transaction['graph']
    status: string
  }> => request(`/api/decision/${id}`),

  getCases: (params?: { status?: string; priority?: string }): Promise<CasesResponse> => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.priority) qs.set('priority', params.priority)
    const query = qs.toString() ? `?${qs.toString()}` : ''
    return request<CasesResponse>(`/api/cases${query}`)
  },

  createCase: (data: {
    transaction_id: string
    assigned_to: string
    priority: string
    notes?: string[]
  }): Promise<Case> =>
    request<Case>('/api/cases', { method: 'POST', body: JSON.stringify(data) }),

  updateCase: (
    id: string,
    data: Partial<{
      status: string
      assigned_to: string
      priority: string
      notes: string[]
      resolution: string
    }>
  ): Promise<Case> =>
    request<Case>(`/api/cases/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  getMetrics: (): Promise<Metrics> => request<Metrics>('/api/metrics'),

  getMetricsHistory: (): Promise<MetricsHistoryResponse> =>
    request<MetricsHistoryResponse>('/api/metrics/history'),

  login: async (username: string, password: string): Promise<TokenResponse> => {
    const body = new URLSearchParams({ username, password })
    const res = await fetch(`${API_URL}/api/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    })
    if (!res.ok) throw new Error('Login failed')
    return res.json() as Promise<TokenResponse>
  },

  overrideDecision: (
    txnId: string,
    decision: string,
    reason: string,
    token: string
  ): Promise<{ transaction_id: string; new_status: string; overridden_by: string }> =>
    request(`/api/decision/${txnId}/override`, {
      method: 'POST',
      body: JSON.stringify({ decision, reason }),
      headers: { Authorization: `Bearer ${token}` },
    }),
}
