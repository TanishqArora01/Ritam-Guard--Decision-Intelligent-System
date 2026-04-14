// lib/api.ts — Typed fetch wrapper with JWT auth

const BASE = typeof window === 'undefined'
  ? (process.env.NEXT_PUBLIC_API_URL ?? 'http://app-backend:8400')
  : '/api/backend';

function setAuthCookie(name: string, value: string) {
  if (typeof document === 'undefined') return;
  const maxAge = 7 * 24 * 60 * 60;
  const secure = typeof window !== 'undefined' && window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

function clearAuthCookie(name: string) {
  if (typeof document === 'undefined') return;
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

function getTokens() {
  if (typeof window === 'undefined') return { access: null, refresh: null };
  return {
    access:  localStorage.getItem('access_token'),
    refresh: localStorage.getItem('refresh_token'),
  };
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem('access_token',  access);
  localStorage.setItem('refresh_token', refresh);
  setAuthCookie('access_token', access);
  setAuthCookie('refresh_token', refresh);
}

export function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  clearAuthCookie('access_token');
  clearAuthCookie('refresh_token');
}

async function refreshAccessToken(): Promise<string | null> {
  const { refresh } = getTokens();
  if (!refresh) return null;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) { clearTokens(); return null; }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

async function apiFetch<T>(
  path:    string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  const { access } = getTokens();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  };
  if (access) headers['Authorization'] = `Bearer ${access}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401 && retry) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiFetch<T>(path, options, false);
    clearTokens();
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const api = {
  auth: {
    login:  (username: string, password: string) =>
      apiFetch<{ access_token: string; refresh_token: string; role: string; username: string }>(
        '/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }
      ).then(data => { setTokens(data.access_token, data.refresh_token); return data; }),
    signup: (payload: { username: string; email: string; password: string; role?: string; org_id?: string | null }) =>
      apiFetch<{ id: string; username: string; email: string; role: string }>(
        '/auth/signup', { method: 'POST', body: JSON.stringify(payload) }
      ),
    me: () => apiFetch<{ id: string; username: string; role: string; org_id: string | null }>('/auth/me'),
    beginSso: async (provider: 'saml' | 'oidc') => ({
      provider,
      enabled: false,
      message: 'SSO integration hook is ready. Connect your IdP endpoint to enable redirect-based auth.',
    }),
    beginMfa: async () => ({
      enabled: false,
      message: 'MFA hook is ready. Connect OTP/WebAuthn challenge endpoint to enforce second factor.',
    }),
    logout: () => { clearTokens(); },
  },

  decisions: {
    list: (params: Record<string, string | number>) => {
      const qs = new URLSearchParams(Object.entries(params).map(([k,v]) => [k, String(v)]));
      return apiFetch<{ items: any[]; total: number; page: number; pages: number }>(`/decisions?${qs}`);
    },
  },

  queue: {
    list:     (params?: Record<string, string | number | boolean>) => {
      const qs = params ? '?' + new URLSearchParams(Object.entries(params).map(([k,v]) => [k,String(v)])) : '';
      return apiFetch<any>(`/review-queue${qs}`);
    },
    get:      (id: string)    => apiFetch<any>(`/review-queue/${id}`),
    assign:   (id: string, assigned_to?: string) =>
      apiFetch<any>(`/review-queue/${id}/assign`, { method: 'PATCH', body: JSON.stringify({ assigned_to }) }),
    resolve:  (id: string, verdict: string, notes: string) =>
      apiFetch<any>(`/review-queue/${id}/resolve`, { method: 'PATCH', body: JSON.stringify({ verdict, analyst_notes: notes }) }),
    priority: (id: string, priority: number) =>
      apiFetch<any>(`/review-queue/${id}/priority`, { method: 'PATCH', body: JSON.stringify({ priority }) }),
    status:   (id: string, status: string) =>
      apiFetch<any>(`/review-queue/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
    sync:     () => apiFetch<any>('/review-queue/sync-from-decisions', { method: 'POST' }),
  },

  analytics: {
    overview:   () => apiFetch<any>('/analytics/overview'),
    fraudRate:  (hours = 24, granularity = 'hour') =>
      apiFetch<any>(`/analytics/fraud-rate?hours=${hours}&granularity=${granularity}`),
    actions:    (hours = 24) => apiFetch<any>(`/analytics/actions?hours=${hours}`),
    latency:    (hours = 1)  => apiFetch<any>(`/analytics/latency?hours=${hours}`),
    topRisk:    (hours = 1)  => apiFetch<any>(`/analytics/top-risk?hours=${hours}`),
    abCompare:  (hours = 24) => apiFetch<any>(`/analytics/ab-comparison?hours=${hours}`),
  },

  users: {
    list:   () => apiFetch<any[]>('/users'),
    create: (data: any) => apiFetch<any>('/users', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: any) => apiFetch<any>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },

  apiKeys: {
    list:   () => apiFetch<any[]>('/api-keys'),
    create: (name: string) => apiFetch<any>('/api-keys', { method: 'POST', body: JSON.stringify({ name }) }),
    revoke: (id: string)   => apiFetch<any>(`/api-keys/${id}`, { method: 'DELETE' }),
  },
};

// SSE helper
export function connectDecisionStream(onEvent: (event: any) => void): () => void {
  const { access } = getTokens();
  const url = `${BASE}/decisions/stream`;
  const es  = new EventSource(url + (access ? `?token=${access}` : ''));
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch {}
  };
  es.onerror = () => es.close();
  return () => es.close();
}
