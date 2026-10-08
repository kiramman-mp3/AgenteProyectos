import * as SecureStore from 'expo-secure-store';

const SERVER_KEY = 'server_url';
const SESSION_KEY = 'session';

export type Role = 'admin' | 'gestor' | 'observador';
export type Session = { token: string; username: string; role: Role };

export type ActivityStatus = 'pendiente' | 'en_ejecucion' | 'completada' | 'retrasada' | 'bloqueada';

export type Activity = {
  id: string;
  name: string;
  url: string;
  list: string;
  responsables: string[];
  labels: string[];
  priority: string | null;
  start: string | null;
  due: string | null;
  days_left: number | null;
  status: ActivityStatus;
  progress: number;
  at_risk: boolean;
  risk_reasons: string[];
  blocks: string[];
  description: string;
};

export type Summary = {
  total: number;
  counts: Record<ActivityStatus, number>;
  progress_weighted: number;
  progress_completed: number;
  at_risk: number;
};

export type Dashboard = {
  board: { name: string | null; url: string | null };
  summary: Summary | null;
  last_sync: string | null;
  attention: Activity[];
  pending_decisions: number;
  unread_notifications: number;
  jobs: { id: string; next_run: string | null }[];
  credentials: Record<string, boolean>;
};

export type Proposal = {
  id: number;
  created_at: string;
  source: 'retraso' | 'codigo';
  group_key: string | null;
  action_type: string;
  target_id: string | null;
  target_name: string | null;
  params: Record<string, unknown>;
  problem: string | null;
  justification: string | null;
  impact: string | null;
  status: string;
  reviewer_verdict: string | null;
  reviewer_notes: string | null;
  approver_decision: string | null;
  approver_risk: string | null;
  approver_notes: string | null;
  manager: string | null;
  manager_comment: string | null;
  decided_at: string | null;
  executed_at: string | null;
  execution_result: string | null;
  revision_of: number | null;
  history?: AuditEntry[];
  alternatives?: { id: number; action_type: string; status: string }[];
};

export type AuditEntry = {
  id: number;
  ts: string;
  actor: string;
  actor_type: 'agente' | 'humano' | 'sistema';
  action: string;
  entity: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
};

export type Finding = {
  archivo: string;
  linea: number | null;
  categoria: string;
  severidad: 'baja' | 'media' | 'alta' | 'critica';
  descripcion: string;
  recomendacion: string;
  estandar_incumplido?: string | null;
  comentario_revisor?: string | null;
};

export type CodeReviewSummary = {
  id: number;
  created_at: string;
  repo: string;
  commit_from: string;
  commit_to: string;
  score: number;
  summary: string;
  findings_count: number;
  severe_count: number;
};

export type CodeReview = CodeReviewSummary & {
  findings: Finding[];
  commits: { sha: string; autor: string; fecha: string; mensaje: string }[];
  review_notes: string;
};

export type ReportSummary = { id: number; created_at: string; period_start: string; period_end: string };
export type Report = ReportSummary & { content_md: string; review_notes: string };

export type Notification = {
  id: number;
  created_at: string;
  level: 'info' | 'advertencia' | 'critico';
  title: string;
  body: string;
  entity: string | null;
  entity_id: string | null;
  read: number;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let cachedServer: string | null = null;
let cachedSession: Session | null = null;
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function getServerUrl(): Promise<string | null> {
  if (cachedServer === null) cachedServer = await SecureStore.getItemAsync(SERVER_KEY);
  return cachedServer;
}

export async function loadSession(): Promise<Session | null> {
  const raw = await SecureStore.getItemAsync(SESSION_KEY);
  cachedSession = raw ? (JSON.parse(raw) as Session) : null;
  return cachedSession;
}

export async function clearSession() {
  cachedSession = null;
  await SecureStore.deleteItemAsync(SESSION_KEY);
}

async function request<T>(path: string, init: RequestInit = {}, server?: string): Promise<T> {
  const base = (server ?? (await getServerUrl()) ?? '').replace(/\/+$/, '');
  if (!base) throw new ApiError(0, 'Configura la dirección del servidor');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (cachedSession) headers.Authorization = `Bearer ${cachedSession.token}`;

  let res: Response;
  try {
    res = await fetch(base + path, { ...init, headers: { ...headers, ...(init.headers as object) } });
  } catch {
    throw new ApiError(0, `No se pudo conectar con ${base}`);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') onUnauthorized?.();
    throw new ApiError(res.status, typeof body.detail === 'string' ? body.detail : `Error ${res.status}`);
  }
  return body as T;
}

export async function login(server: string, username: string, password: string): Promise<Session> {
  const url = server.trim().replace(/\/+$/, '');
  cachedSession = null;
  const session = await request<Session>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  }, url);
  await SecureStore.setItemAsync(SERVER_KEY, url);
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session));
  cachedServer = url;
  cachedSession = session;
  return session;
}

const post = <T,>(path: string, body: object = {}) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) });

export const api = {
  dashboard: () => request<Dashboard>('/dashboard'),
  activities: () => request<Activity[]>('/activities'),
  sync: () => post<{ changes: number }>('/sync'),
  runAnalysis: () => post<{ status: string }>('/analysis/run'),
  proposals: (status?: string) => request<Proposal[]>(`/proposals${status ? `?status=${status}` : ''}`),
  proposal: (id: number) => request<Proposal>(`/proposals/${id}`),
  approve: (id: number, comment?: string) => post<{ status: string }>(`/proposals/${id}/approve`, { comment }),
  reject: (id: number, comment?: string) => post<{ status: string }>(`/proposals/${id}/reject`, { comment }),
  requestChanges: (id: number, comment: string) =>
    post<{ status: string }>(`/proposals/${id}/request-changes`, { comment }),
  codeReviews: () => request<CodeReviewSummary[]>('/code-reviews'),
  codeReview: (id: number) => request<CodeReview>(`/code-reviews/${id}`),
  runCodeReview: () => post<{ status: string }>('/code-reviews/run'),
  reports: () => request<ReportSummary[]>('/reports'),
  report: (id: number) => request<Report>(`/reports/${id}`),
  generateReport: () => post<{ status: string }>('/reports/generate'),
  audit: (actorType?: string) => request<AuditEntry[]>(`/audit${actorType ? `?actor_type=${actorType}` : ''}`),
  notifications: () => request<Notification[]>('/notifications'),
  readAllNotifications: () => post('/notifications/read-all'),
};
