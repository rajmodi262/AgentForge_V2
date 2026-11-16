/**
 * Phantom Hunter — API client
 */
import { API_BASE } from './api';

export interface CallSegment { segment: string; priority: number; reasons: string[] }
export interface PhProject {
  id: string; name: string; developer: string | null; city: string | null; state: string | null; country: string | null;
  lat: number | null; lon: number | null; capacity_mw: number | null; capacity_basis: string | null; target_year: number | null;
  power_partner: string | null; ai_density: boolean; stage: number; stage_name: string; reality_score: number;
  reality_mw: number; weakest_assumption: string | null; n_sources: number;
  call_segments: Record<string, CallSegment> | null; has_debate: boolean; last_seen: string | null;
  priority?: number; reasons?: string[];
}
export interface ArticleRef { url: string; title: string; source: string; published: string | null; text_kind: string }
export interface EvidenceItem { layer: string; detail: string; quote: string; date: string | null; article: ArticleRef | null }
export interface DebatePoint { claim: string; cites: string[]; from_missing_evidence?: boolean }
export interface Debate { bull: DebatePoint[]; bear: DebatePoint[]; verdict: string; reasoning: string; watch_for: string; evidence_ids: string[] }
export interface ProjectDetail extends PhProject {
  score_breakdown: { key?: string; term: string; delta: number | null; value?: number; why: string }[];
  debate: Debate | null;
  evidence: EvidenceItem[];
  anomalies: { kind: string; severity: string; message: string }[];
  mentions: { article: ArticleRef | null; verified_ratio: number; verification: Record<string, any>; data: Record<string, any> }[];
  ladder: { layer: string; reached: boolean; verified: boolean }[];
  grid_position?: GridPosition; grid_label?: string | null; power?: Partial<PowerBrief>; power_facts?: PowerFact[];
}
export interface Summary {
  projects: number; announced_mw: number; reality_mw: number;
  by_country: Record<string, { projects: number; announced_mw: number; reality_mw: number; with_capacity: number }>;
  by_state: { place: string; projects: number; announced_mw: number; reality_mw: number }[];
  stages: Record<string, number>;
  articles: { total: number; full_text: number; headline_only: number; relevant: number; extracted: number };
  mentions: number; claims_verified_pct: number | null; anomalies: Record<string, number>;
}
export interface Signal { project_id: string; project: string; layer: string; quote: string; date: string | null; source: string; url: string; reality_score: number; country: string | null }
export interface ChatAnswer { answer: string; sources: { id: string; project_id: string; name: string; url: string | null; title: string | null }[] }

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem('agentforge_token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}/phantom${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}/phantom${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
}

export const phantom = {
  summary: () => get<Summary>('/summary'),
  projects: (q = '') => get<{ total: number; projects: PhProject[] }>(`/projects${q}`),
  whoToCall: (segment: string) => get<{ segment: string; projects: PhProject[] }>(`/who-to-call?segment=${segment}&limit=8`),
  project: (id: string) => get<ProjectDetail>(`/projects/${id}`),
  debate: (id: string, refresh = false) => post<Debate>(`/projects/${id}/debate${refresh ? '?refresh=true' : ''}`),
  ask: (question: string) => post<ChatAnswer>('/ask', { question }),
  signals: () => get<{ signals: Signal[]; anomalies: { project_id: string; project: string; kind: string; severity: string; message: string }[] }>('/signals'),
  hunt: (region: string) => post<{ run_id: string; websocket_url: string }>('/hunt', { region, max_rounds: 2 }),
  run: (id: string) => get<{ status: string; stats: Record<string, unknown>; log: string[] }>(`/runs/${id}`),
  // Business exports — plain links (public, read-only data), so the browser handles the download
  exportXlsxUrl: `${API_BASE}/phantom/export.xlsx`,
  exportCsvUrl: (table: string) => `${API_BASE}/phantom/export/${table}.csv`,
};

export const WS_BASE = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://').replace('/api/v1', '');

export const STAGE_COLORS: Record<string, string> = {
  ANNOUNCED: '#94a3b8', SITE: '#a78bfa', APPROVED: '#60a5fa', POWER: '#f59e0b', BUILDING: '#06b6d4', LIVE: '#10b981',
  FINANCED: '#e879f9', DELAYED: '#fb923c', CANCELLED: '#ef4444', OPPOSITION: '#f87171', SCALED_DOWN: '#fbbf24',
};

export const scoreColor = (s: number) => (s >= 0.7 ? '#10b981' : s >= 0.45 ? '#f59e0b' : '#ef4444');
export const fmtMW = (mw: number | null | undefined) =>
  mw == null ? '—' : mw >= 1000 ? `${(mw / 1000).toFixed(mw >= 10000 ? 0 : 1)} GW` : `${Math.round(mw)} MW`;

// ───────────── Power forensics, model, timeline, backtest ─────────────
export type GridPosition = 'ENERGIZED' | 'AGREEMENT' | 'POWER_DEAL' | 'UNDER_CONSTRUCTION' | 'APPLIED' | 'NO_EVIDENCE';
export interface PowerFact { field: string; value: string | number; quote: string; planned: boolean; article?: ArticleRef | null }
export interface PowerBrief {
  grid_position: GridPosition; grid_label: string; secured: boolean; utilities: string[]; grid_kv: number | null; grid_mva: number | null;
  substation: string | null; onsite: string[]; renewable: string[]; cooling: string[]; rack_kw: number | null; pue: number | null; water: string[];
  contractors: string[]; equipment: string[]; financiers: string[]; n_facts: number;
}
export interface Share { mw: number; share: number | null; projects: number }
export interface PowerHeadline {
  projects: number; announced_mw: number; grid: Record<GridPosition, { projects: number; mw: number }>;
  secured_mw: number; unsecured_mw: number; secured_share: number | null; pipeline_mw: number;
  pipeline_secured: Share; pipeline_unsecured: Share; btm_signal: Share; liquid_cooling_signal: Share; low_water_signal: Share;
  renewable_signal: Share; no_utility_named: Share; coverage: Record<string, number>; with_any_fact: number;
}
export type PowerProject = PhProject & { grid_position: GridPosition; grid_label: string | null; power: Partial<PowerBrief> };
export interface PowerView { headline: PowerHeadline; labels: Record<GridPosition, string>; projects_by_position: Record<GridPosition, PowerProject[]>; note: string }
export interface DeveloperRow {
  developer: string; countries: string; projects: number; announced_mw: number; reality_mw: number; live: number; building: number;
  pre_construction: number; live_mw: number; secured_mw: number; judged: number; built_of_judged: number; build_rate: number | null;
  months_to_ground: number | null; timed_projects: number;
}
export interface ModelProject { id: string; name: string; developer: string | null; country: string | null; state: string | null; capacity_mw: number | null; stage: number; cancelled: boolean; terms: string[]; score: number }
export interface ScoreModel {
  layers: string[]; priors: { stated: number[]; active: number[]; fitted: number[] | null };
  calibration: { cases: number; projects: number; cutoffs: string[]; fitted_on: string; shrink: number } | null;
  weights: Record<string, number>; weight_labels: Record<string, string>; projects: ModelProject[];
}
export interface TimelineProject {
  id: string; name: string; developer: string | null; country: string | null; city: string | null; lat: number | null; lon: number | null;
  capacity_mw: number | null; first_seen: string; events: { layer: string; date: string }[]; stage: number; reality_score: number; grid_position: GridPosition;
}
export interface Timeline { projects: TimelineProject[]; from: string | null; to: string | null; undated: number }
export interface Reliability { bucket: string; n: number; predicted: number; observed: number }
export interface Evaluation {
  n: number; projects: number; base_rate: number; brier: number; auc: number | null; baselines: { base_rate: number; flat_35: number; stage_only: number };
  auc_stage_only: number | null; table: Reliability[]; brier_ci?: [number, number] | null; auc_ci?: [number, number] | null;
  phantom_calls: { n: number; right: number; accuracy: number | null }; likely_calls: { n: number; right: number; accuracy: number | null };
}
export interface BacktestCase {
  project_id: string; name: string; developer: string | null; country: string; cutoff: string; stage_then: string; stage_now: string;
  progressed: boolean; score_stated: number; score_fitted: number; news_after: number; sources_then: number;
}
export interface Backtest {
  generated: string; rows: BacktestCase[]; cutoffs: string[]; fit_cutoffs: string[]; fit_cases: { n: number; projects: number };
  fitted: Record<string, number>; assumed: Record<string, number>; shrink: number; mature_years: number; bands: { phantom: number; likely: number };
  fitted_priors: { layer: string; assumed: number; n: number; progressed: number; observed: number | null; fitted: number }[];
  pooled: Evaluation; assumed_mature: Evaluation; assumed_mature_pre: Evaluation; cv: Evaluation; cv_pre: Evaluation;
  by_cutoff: Record<string, Evaluation>; by_cutoff_pre_construction: Record<string, Evaluation>;
}

export const lab = {
  power: (country = '') => get<PowerView>(`/power${country ? `?country=${country}` : ''}`),
  developers: (min = 1) => get<{ developers: DeveloperRow[]; total: number; note: string }>(`/developers?min_projects=${min}&limit=300`),
  model: () => get<ScoreModel>('/model'),
  timeline: () => get<Timeline>('/timeline'),
  backtest: () => get<Backtest>('/backtest'),
};

export const GRID_COLORS: Record<GridPosition, string> = {
  ENERGIZED: '#10b981', AGREEMENT: '#22d3ee', POWER_DEAL: '#a78bfa', UNDER_CONSTRUCTION: '#f59e0b', APPLIED: '#fb923c', NO_EVIDENCE: '#f43f5e',
};
export const GRID_ORDER: GridPosition[] = ['ENERGIZED', 'AGREEMENT', 'POWER_DEAL', 'UNDER_CONSTRUCTION', 'APPLIED', 'NO_EVIDENCE'];
export const pct = (x: number | null | undefined, digits = 0) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`);
