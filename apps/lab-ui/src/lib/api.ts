import { normalizeArtifactPath } from "@/lib/format";
import { BUILTIN_PIPELINE_SPECS } from "@/lib/pipelines";

/** Same-origin proxy in dev (`/lab-api` → FastAPI). Override for production or direct API URL. */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "/lab-api";

export type DashboardStats = {
  run_count: number;
  config_count: number;
  compare_count: number;
  experiment_count: number;
  top_strategies: Array<{ strategy_id: string; n: number; best_return: number | null }>;
};

export type ArtifactRef = {
  name: string;
  url: string;
};

export type EvaluationRun = {
  id: string;
  run_kind: string;
  config_id: string;
  strategy_id: string | null;
  model_id: string | null;
  symbol: string | null;
  resolution: string | null;
  horizon_label: string | null;
  parameters: Record<string, unknown>;
  data_context: Record<string, unknown>;
  metrics: Record<string, unknown>;
  created_at_utc: string;
  compare_session_id: string | null;
  experiment_id: string | null;
  dataset_id: string | null;
  dataset_label: string | null;
  results_download_url: string;
  artifacts?: ArtifactRef[];
};

export type ConfigurationRow = {
  id: string;
  config_kind: string;
  strategy_id: string | null;
  model_id: string | null;
  symbol: string | null;
  resolution: string | null;
  horizon_label: string | null;
  parameters: Record<string, unknown>;
  data_context: Record<string, unknown>;
  created_at_utc: string;
  dataset_id: string | null;
  dataset_label: string | null;
};

export type ExperimentRow = {
  experiment_id: string;
  pipeline_id: string | null;
  title: string | null;
  status: string | null;
  payload: Record<string, unknown>;
  updated_at_utc: string;
  runnable: boolean;
  test_step_count?: number;
  last_error?: string | null;
};

export type PipelineStepView = {
  id: string;
  title: string;
};

export type PipelineInputView = {
  key: string;
  label: string;
  kind: "number" | "dataset" | "boolean" | "select" | string;
  required?: boolean;
  default?: string;
  hint?: string;
  options?: { value: string; label: string }[];
};

export type PipelineSpecRow = {
  id: string;
  title: string;
  description: string;
  full?: boolean;
  steps?: PipelineStepView[];
  inputs?: PipelineInputView[];
};

export type CompareSession = {
  id: string;
  dataset_id: string | null;
  dataset_label: string | null;
  bar_count: number | null;
  best_strategy_id: string | null;
  summary: Record<string, unknown>;
  created_at_utc: string;
  artifacts: ArtifactRef[];
};

export type CatalogStrategy = {
  id: string;
  name: string;
  summary: string;
  style: string;
  implemented: boolean;
};

export type AuthStatus = {
  api_keys_configured: boolean;
  auth_token_configured: boolean;
};

export type JobRow = {
  id: string;
  job_type: string;
  status: string;
  payload: Record<string, unknown>;
  log_text: string;
  created_at_utc: string;
  finished_at_utc: string | null;
};

export type DatasetRow = {
  id: string;
  label: string;
  symbol: string | null;
  resolution: string | null;
  horizon_label: string | null;
  range_start_utc: string | null;
  range_end_utc: string | null;
  source: string;
  repo_path?: string;
  last_seen_at_utc: string;
};

export type MarketSpec = {
  src: string;
  dst: string;
  symbol: string;
  label: string;
};

export type MarketsCatalog = {
  catalog_scope: string;
  total_in_catalog: number;
  matched_count: number;
  offset: number;
  limit: number;
  updated_at_utc: string | null;
  markets: MarketSpec[];
  udf_resolutions: string[];
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(
        "Lab API endpoint not found (404). Restart ./run-lab-api.sh or ./run-lab.sh to load the current API.",
      );
    }
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function apiUrl(relativePath: string): string {
  return `${API_BASE}${relativePath.startsWith("/") ? relativePath : `/${relativePath}`}`;
}

export function artifactUrl(repoRelativePath: string): string {
  const path = normalizeArtifactPath(repoRelativePath);
  return `${API_BASE}/artifact?path=${encodeURIComponent(path)}`;
}

export function datasetDownloadUrl(datasetId: string): string {
  return apiUrl(`/api/datasets/${encodeURIComponent(datasetId)}/download`);
}

export type HealthResponse = {
  status: string;
  features: string[];
};

export const api = {
  health: () => fetchJson<HealthResponse>("/health"),
  stats: () => fetchJson<DashboardStats>("/api/stats"),
  runs: (query = "") => fetchJson<EvaluationRun[]>(`/api/runs${query}`),
  run: (id: string) => fetchJson<EvaluationRun>(`/api/runs/${id}`),
  configurations: (kind?: string) =>
    fetchJson<ConfigurationRow[]>(
      `/api/configurations${kind ? `?config_kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  experiments: () => fetchJson<ExperimentRow[]>("/api/experiments"),
  syncExperiments: async () => {
    const response = await fetch(`${API_BASE}/api/experiments/sync`, { method: "POST" });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{ registered_count: number }>;
  },
  pipelines: async () => {
    try {
      return await fetchJson<PipelineSpecRow[]>("/api/pipelines");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes("404")) {
        return BUILTIN_PIPELINE_SPECS;
      }
      throw error;
    }
  },
  compareSessions: () => fetchJson<CompareSession[]>("/api/compare-sessions"),
  jobs: (limit = 50) => fetchJson<JobRow[]>(`/api/jobs?limit=${limit}`),
  datasets: (limit = 200) => fetchJson<DatasetRow[]>(`/api/datasets?limit=${limit}`),
  /** Same rows as datasets — catalog OHLC files under data/ (SQLite-backed). */
  dataCsvFiles: (limit = 200) => fetchJson<DatasetRow[]>(`/api/data/csv-files?limit=${limit}`),
  dataMarketsCatalog: (scope: "default_jobs" | "nobitex_all" = "nobitex_all") => {
    const params = new URLSearchParams({ scope, catalog: "true" });
    return fetchJson<MarketsCatalog>(`/api/data/markets?${params.toString()}`);
  },
  dataMarkets: (options?: {
    scope?: "default_jobs" | "nobitex_all";
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const scope = options?.scope ?? "nobitex_all";
    const params = new URLSearchParams({ scope });
    if (options?.q?.trim()) {
      params.set("q", options.q.trim());
    }
    if (options?.limit !== undefined) {
      params.set("limit", String(options.limit));
    }
    if (options?.offset !== undefined) {
      params.set("offset", String(options.offset));
    }
    return fetchJson<MarketsCatalog>(`/api/data/markets?${params.toString()}`);
  },
  syncMarkets: async (scope: "default_jobs" | "nobitex_all" = "nobitex_all") => {
    const response = await fetch(
      `${API_BASE}/api/data/markets/sync?scope=${encodeURIComponent(scope)}`,
      { method: "POST" },
    );
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(
          "Sync endpoint not found — restart ./run-lab-api.sh to run the current Lab API.",
        );
      }
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{
      catalog_scope: string;
      cloned_count: number;
      updated_at_utc: string | null;
    }>;
  },
  experimentArtifacts: (experimentId: string) =>
    fetchJson<{ artifacts: ArtifactRef[] }>(`/api/experiments/${experimentId}/artifacts`),
  job: (id: string) => fetchJson<JobRow>(`/api/jobs/${id}`),
  authStatus: () => fetchJson<AuthStatus>("/api/auth/status"),
  authProfile: () => fetchJson<Record<string, unknown>>("/api/auth/profile"),
  authLogin: (body: Record<string, unknown>) =>
    fetchJson<Record<string, unknown>>("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  authApiKeys: () => fetchJson<unknown>("/api/auth/api-keys"),
  authCreateApiKey: (body: Record<string, unknown>) =>
    fetchJson<Record<string, unknown>>("/api/auth/api-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  catalogStrategies: (implementedOnly = true) =>
    fetchJson<CatalogStrategy[]>(
      `/api/catalog/strategies?implemented_only=${implementedOnly ? "true" : "false"}`,
    ),
  stopJob: async (jobId: string) => {
    const response = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/stop`, {
      method: "POST",
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{ id: string; status: string; stop_requested?: boolean }>;
  },
  postJob: async (jobType: string, body: Record<string, unknown>) => {
    const response = await fetch(`${API_BASE}/api/jobs/${jobType}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{ id: string; status: string }>;
  },
};
