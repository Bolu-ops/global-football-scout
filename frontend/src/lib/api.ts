export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SeasonRef = {
  season_id: number;
  name: string;
  competition_id: number;
  competition: string;
  competition_type: string;
  gender: string;
  coverage_type: string;
  end_year: number;
  minutes: number;
  appearances: number;
  starts: number;
  teams: string[];
  position: string | null;
  position_group: string | null;
  league_strength: number | null;
  league_strength_confidence: string | null;
};

export type PlayerSummary = {
  player_id: number;
  full_name: string;
  known_as: string | null;
  display_name: string;
  nationality: string | null;
  gender: string;
  date_of_birth: string | null;
  age: number | null;
  age_note: string | null;
  sources: string[];
  latest_season: SeasonRef | null;
};

export type PlayerDetail = PlayerSummary & {
  seasons: SeasonRef[];
  data_quality: { seasons_loaded: number; total_minutes: number; sources: number; has_date_of_birth: boolean; flags: string[] };
};

export type MetricValue = {
  code: string;
  name: string;
  family: string;
  value: number | null;
  per90: number | null;
  unit: string | null;
  is_rate: boolean;
  direction: string;
  percentile: number | null;
  percentile_pool: string | null;
  percentile_pool_n: number | null;
  adjusted_percentile: number | null;
  source: string;
  definition: string | null;
};

export type PlayerStats = { player_id: number; season: SeasonRef; metrics: MetricValue[]; percentile_note: string };

export type Contribution = {
  feature: string;
  category: string;
  weight: number;
  delta_z: number;
  target_value: number;
  candidate_value: number;
  target_z: number;
  candidate_z: number;
};

export type SimilarityHit = {
  rank: number;
  player_id: number;
  season_id: number;
  display_name: string;
  nationality: string | null;
  team_name: string | null;
  competition: string;
  competition_id: number;
  season: string;
  position: string;
  position_group: string;
  minutes: number;
  similarity: number;
  similarity_statistical: number;
  compatibility: number;
  compatibility_basis: string;
  sim_by_category: Record<string, number>;
  usable_weight: number;
  confidence: string;
  confidence_score: number;
  league_strength: number | null;
  league_confidence: string | null;
  explanation: { supporting: Contribution[]; divergent: Contribution[]; category_contributions: Record<string, number> };
  estimated_value_eur: number | null;
  value_note: string;
};

export type SimilarityResponse = {
  target: {
    player_id: number;
    season_id: number;
    position_group: string;
    position_code: string;
    secondary_position: string | null;
    minutes: number;
    competition: string;
    season: string;
    competition_id: number;
    mode: string;
  } | null;
  reason: string | null;
  excluded_competitions: { competition_id: number; name?: string; score?: number; basis?: string }[];
  category_weights: Record<string, number> | null;
  candidates_considered: number;
  results: SimilarityHit[];
};

export type TransferValue = {
  player_id: number;
  estimated_value_eur: number | null;
  range_eur: [number | null, number | null] | null;
  confidence: string;
  status: string;
  reference_market_value_eur?: number | null;
  model_market_discrepancy_eur?: number | null;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}: ${await r.text()}`);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}: ${await r.text()}`);
  return r.json();
}

export const api = {
  searchPlayers: (q: string, limit = 8) => get<PlayerSummary[]>(`/players?q=${encodeURIComponent(q)}&limit=${limit}`),
  player: (id: number) => get<PlayerDetail>(`/players/${id}`),
  stats: (id: number, seasonId?: number) => get<PlayerStats>(`/players/${id}/stats${seasonId ? `?season_id=${seasonId}` : ""}`),
  similarity: (id: number, body: Record<string, unknown>) => post<SimilarityResponse>(`/players/${id}/similarity`, body),
  transferValue: (id: number) => get<TransferValue>(`/players/${id}/transfer-value`),
  naturalLanguage: (query: string) => post<{ interpretation: string; notes: string[]; result: SimilarityResponse | null; structured_filters: Record<string, unknown> }>(`/scouting/natural-language`, { query }),
  adminStats: () => get<AdminStats>(`/admin/stats`),
  adminJobs: () => get<Job[]>(`/admin/jobs`),
  coverage: () => get<Coverage[]>(`/admin/coverage`),
  modelInfo: () => get<Record<string, unknown>>(`/model/info`),
  dataSources: () => get<DataSource[]>(`/data-sources`),
  competitions: () => get<Competition[]>(`/competitions`),
};

export type AdminStats = {
  counts: Record<string, number>;
  sources: { code: string; name: string; is_active: boolean; requires_api_key: boolean; jobs: number }[];
  last_ingestion: { job_type: string; status: string; params: Record<string, unknown>; started_at: string; finished_at: string | null; rows_written: number; running_jobs: number } | null;
  failed_jobs: number;
  pending_identity_reviews: number;
  open_quality_flags: number;
  excluded_competitions: { competition_id: number; name: string; country: string | null; score: number; basis: string; confidence: string }[];
  config_version: string;
};

export type Job = { job_id: number; job_type: string; status: string; params: Record<string, unknown>; started_at: string; finished_at: string | null; rows_read: number; rows_written: number; error: string | null; failed_items: number };
export type Coverage = { competition: string; gender: string; type: string; season: string; coverage: string; note: string | null; matches: number };
export type DataSource = { code: string; name: string; url: string | null; data_types: string[]; licence: string | null; licence_url: string | null; attribution_text: string | null; attribution_required: boolean; commercial_use_allowed: boolean | null; redistribution_allowed: boolean | null; requires_api_key: boolean; is_active: boolean; notes: string | null; reliability_score: number | null; update_frequency: string | null };
export type Competition = { competition_id: number; name: string; country: string | null; region: string | null; gender: string; type: string; tier: number | null; matches: number; seasons: { season_id: number; name: string; end_year: number; coverage_type: string; coverage_note: string | null; league_strength: number | null; league_strength_confidence: string | null; league_strength_is_prior: boolean | null }[] };

export const fmt = {
  num: (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toFixed(d)),
  int: (v: number | null | undefined) => (v == null ? "—" : Math.round(v).toLocaleString()),
  pct: (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}`),
  eur: (v: number | null | undefined) => (v == null ? "Data unavailable" : `€${(v / 1e6).toFixed(1)}M`),
};
