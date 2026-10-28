import { normalizeArtifactPath } from "@/lib/format";
import { BUILTIN_PIPELINE_SPECS } from "@/lib/pipelines";

/** Same-origin proxy in dev (`/lab-api` → FastAPI). Override for production or direct API URL. */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "/lab-api";

export type DashboardStats = {
  run_count: number;
  config_count: number;
  compare_count: number;
  sweep_count: number;
  experiment_count: number;
  backtest_summary: {
    count: number;
    avg_return: number | null;
    best_return: number | null;
    worst_return: number | null;
    positive_pct: number | null;
  };
  top_strategies: Array<{
    strategy_id: string;
    n: number;
    best_return: number | null;
    avg_return: number | null;
  }>;
  strategy_catalog_stats?: Array<{
    strategy_id: string;
    n: number;
    best_return: number | null;
    avg_return: number | null;
  }>;
  top_markets: Array<{ symbol: string; n: number; best_return: number | null; avg_return: number | null }>;
  top_intervals: Array<
    { interval_label: string; n: number; best_return: number | null; avg_return: number | null }
  >;
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

export type SweepSession = {
  id: string;
  strategy_id: string;
  symbol: string | null;
  resolution: string | null;
  horizon_label: string | null;
  csv_path: string;
  bar_count: number | null;
  rank_by: string;
  holdout_tail_bars: number | null;
  min_trades: number | null;
  cash: number | null;
  fee: number | null;
  param_grid: Record<string, unknown[]>;
  best_params: Record<string, unknown>;
  best_metrics: Record<string, unknown>;
  config_id: string | null;
  manifest_path: string | null;
  optimize_start_utc: string | null;
  optimize_end_utc: string | null;
  compare_start_utc: string | null;
  compare_end_utc: string | null;
  created_at_utc: string;
};

export type CatalogStrategy = {
  id: string;
  name: string;
  summary: string;
  style: string;
  implemented: boolean;
};

export type BacktestCatalog = {
  vectorbt_available: boolean;
  execution_modes: string[];
};

export type TerminalCatalog = {
  commands: Array<{ id: string; summary: string }>;
  strategies: CatalogStrategy[];
  execution_modes: string[];
  live_exchanges?: string[];
  default_live_exchange?: string;
  udf_resolutions: string[];
  hyperliquid_resolutions?: string[];
};

export type LiveStrategyRankRow = {
  strategy_id: string;
  rank: number;
  return_pct: number | null;
  max_drawdown_pct?: number | null;
  trade_count?: number | null;
  final_equity?: number | null;
  stored_sweep_return_pct?: number | null;
  stored_sweep_holdout_return_pct?: number | null;
};

export type LiveStrategyRanks = {
  exchange: string;
  symbol: string;
  src: string;
  dst: string;
  resolution: string;
  bars: number;
  initial_cash: number;
  ranked: LiveStrategyRankRow[];
  skipped: Array<{ strategy_id: string; error: string }>;
  strategy_count: number;
};

export type StrategyParamField = {
  name: string;
  kind: "int" | "float" | "bool" | "optional_float" | "string";
  default: unknown;
};

export type OptimizedStrategyParams = {
  strategy_id: string;
  symbol: string | null;
  resolution: string | null;
  values: Record<string, unknown>;
  sources: Record<string, string>;
  sweep_meta?: {
    requested_symbol: string | null;
    sweep_symbol: string | null;
    sweep_horizon_label?: string | null;
    sweep_fallback: boolean;
    optimize_start_utc?: string | null;
    optimize_end_utc?: string | null;
    compare_start_utc?: string | null;
    compare_end_utc?: string | null;
  };
};

export type AuthStatus = {
  api_keys_configured: boolean;
  auth_token_configured: boolean;
  hyperliquid_wallet_configured?: boolean;
  hyperliquid_trading_configured?: boolean;
  live_exchange_default?: string;
  lab_api_auth_enabled?: boolean;
  lab_api_token_configured?: boolean;
  coinbeacon_configured?: boolean;
  coinbeacon_key_count?: number;
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

export type OhlcBar = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  symbol?: string;
  resolution?: string;
};

export type MarketsOhlcResponse = {
  exchange?: string;
  symbol: string;
  src: string;
  dst: string;
  resolution: string;
  bars: OhlcBar[];
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

function labAuthHeaders(): Record<string, string> {
  const token = process.env.NEXT_PUBLIC_LAB_API_TOKEN?.trim();
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

export function withLabAuth(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers ?? undefined);
  for (const [key, value] of Object.entries(labAuthHeaders())) {
    headers.set(key, value);
  }
  return { ...init, headers };
}

export function parseApiErrorBody(text: string, status: number): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return `${status}`;
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; error?: unknown };
    if (typeof parsed.error === "string" && parsed.error) {
      return parsed.error;
    }
    if (typeof parsed.detail === "string" && parsed.detail) {
      return parsed.detail;
    }
  } catch {
    /* plain text */
  }
  return trimmed;
}

export function formatApiError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (error === null || error === undefined) {
    return "Request failed";
  }
  return String(error);
}

export function isLabAuthError(error: unknown): boolean {
  const message = formatApiError(error).toLowerCase();
  return (
    message.includes("invalid or missing lab api token") ||
    message.includes("401") ||
    message.includes("unauthorized")
  );
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, withLabAuth(init));
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(
        "Lab API endpoint not found (404). Restart ./run-lab-api.sh or ./run-lab.sh to load the current API.",
      );
    }
    const detail = await response.text();
    throw new Error(parseApiErrorBody(detail, response.status) || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

/** Fetch JSON and also surface the `X-Total-Count` response header. */
async function fetchJsonWithTotal<T>(path: string, init?: RequestInit): Promise<{ data: T; total: number }> {
  const response = await fetch(`${API_BASE}${path}`, withLabAuth(init));
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(
        "Lab API endpoint not found (404). Restart ./run-lab-api.sh or ./run-lab.sh to load the current API.",
      );
    }
    const detail = await response.text();
    throw new Error(parseApiErrorBody(detail, response.status) || `${response.status} ${response.statusText}`);
  }
  const data = (await response.json()) as T;
  const totalHeader = response.headers.get("X-Total-Count");
  const total = totalHeader ? Math.max(0, parseInt(totalHeader, 10) || 0) : 0;
  return { data, total };
}

export type PaginatedRuns = { data: EvaluationRun[]; total: number };

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

export type PairBacktestResult = {
  exchange: string;
  fee_role?: string;
  initial_cash: number;
  final_equity: number;
  return_pct: number;
  max_drawdown_pct: number;
  total_fees: number;
  trade_count: number;
  equity_curve: [number, number][];
  spread_curve: [number, number][];
  z_score_curve: [number, number][];
  trades: Array<{
    timestamp: number;
    leg: string;
    action: string;
    price: number;
    size: number;
    fee: number;
  }>;
};

export type FundingBacktestResult = {
  exchange: string;
  src: string;
  return_pct: number;
  max_drawdown_pct: number;
  total_funding_pnl: number;
  total_fees: number;
  trade_count: number;
  equity_curve: [number, number][];
  funding_curve: [number, number][];
};

export type GridBacktestResult = {
  exchange: string;
  return_pct: number;
  trade_count: number;
  final_equity: number;
  total_fees: number;
};

export type StrategyExchangeCatalog = {
  exchanges: string[];
  strategies: Record<string, string[]>;
  execution_costs: Record<string, Record<string, { fee_rate: number; slippage_rate: number }>>;
};

export const api = {
  health: () => fetchJson<HealthResponse>("/health"),
  stats: () => fetchJson<DashboardStats>("/api/stats"),
  /** Fetch runs with a raw query string (no total count). Kept for the dashboard widget. */
  runs: (query = "") => fetchJson<EvaluationRun[]>(`/api/runs${query}`),
  /** Fetch runs with structured pagination params and the server-side total count. */
  runsPaginated: (params: {
    limit: number;
    offset: number;
    run_kind?: string;
    symbol?: string;
    strategy_id?: string;
    model_id?: string;
    horizon_label?: string;
  }) => {
    const q = new URLSearchParams();
    q.set("limit", String(params.limit));
    q.set("offset", String(params.offset));
    if (params.run_kind) q.set("run_kind", params.run_kind);
    if (params.symbol) q.set("symbol", params.symbol);
    if (params.strategy_id) q.set("strategy_id", params.strategy_id);
    if (params.model_id) q.set("model_id", params.model_id);
    if (params.horizon_label) q.set("horizon_label", params.horizon_label);
    return fetchJsonWithTotal<EvaluationRun[]>(`/api/runs?${q.toString()}`);
  },
  run: (id: string) => fetchJson<EvaluationRun>(`/api/runs/${id}`),
  runAnalytics: (id: string) => fetchJson<RunAnalytics>(`/api/runs/${id}/analytics`),
  configurations: (kind?: string) =>
    fetchJson<ConfigurationRow[]>(
      `/api/configurations${kind ? `?config_kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  experiments: () => fetchJson<ExperimentRow[]>("/api/experiments"),
  syncExperiments: async () => {
    const response = await fetch(`${API_BASE}/api/experiments/sync`, withLabAuth({ method: "POST" }));
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
  sweeps: (query = "") => fetchJson<SweepSession[]>(`/api/sweeps${query}`),
  bestSweep: (strategyId: string, symbol?: string, resolution?: string) => {
    const params = new URLSearchParams({ strategy_id: strategyId });
    if (symbol) params.set("symbol", symbol);
    if (resolution) params.set("resolution", resolution);
    return fetchJson<SweepSession>(`/api/sweeps/best?${params.toString()}`);
  },
  jobs: (limit = 50) => fetchJson<JobRow[]>(`/api/jobs?limit=${limit}`),
  datasets: (limit = 200) => fetchJson<DatasetRow[]>(`/api/datasets?limit=${limit}`),
  /** Same rows as datasets — catalog OHLC files under data/ (SQLite-backed). */
  dataCsvFiles: (limit = 200) => fetchJson<DatasetRow[]>(`/api/data/csv-files?limit=${limit}`),
  dataMarketsCatalog: (scope: "default_jobs" | "nobitex_all" | "hyperliquid_all" = "hyperliquid_all") => {
    const params = new URLSearchParams({ scope, catalog: "true" });
    return fetchJson<MarketsCatalog>(`/api/data/markets?${params.toString()}`);
  },
  dataMarkets: (options?: {
    scope?: "default_jobs" | "nobitex_all" | "hyperliquid_all";
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const scope = options?.scope ?? "hyperliquid_all";
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
  syncMarkets: async (scope: "default_jobs" | "nobitex_all" | "hyperliquid_all" = "hyperliquid_all") => {
    const response = await fetch(
      `${API_BASE}/api/data/markets/sync?scope=${encodeURIComponent(scope)}`,
      withLabAuth({ method: "POST" }),
    );
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(
          "Sync endpoint not found — restart ./run-lab-api.sh to run the current Lab API.",
        );
      }
      const raw = await response.text();
      let detail = raw;
      try {
        const parsed = JSON.parse(raw) as { detail?: string };
        if (typeof parsed.detail === "string") {
          detail = parsed.detail;
        }
      } catch {
        /* plain text */
      }
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
  authSaveCoinbeacon: (body: Record<string, unknown>) =>
    fetchJson<Record<string, unknown>>("/api/auth/coinbeacon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  authHyperliquidAccount: () => fetchJson<Record<string, unknown>>("/api/auth/hyperliquid"),
  authSaveHyperliquid: (body: Record<string, unknown>) =>
    fetchJson<Record<string, unknown>>("/api/auth/hyperliquid", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  catalogBacktest: () => fetchJson<BacktestCatalog>("/api/catalog/backtest"),
  catalogStrategies: (implementedOnly = true) =>
    fetchJson<CatalogStrategy[]>(
      `/api/catalog/strategies?implemented_only=${implementedOnly ? "true" : "false"}`,
    ),
  catalogTerminal: (implementedOnly = true) =>
    fetchJson<TerminalCatalog>(
      `/api/catalog/terminal?implemented_only=${implementedOnly ? "true" : "false"}`,
    ),
  liveStrategyRanks: (options: {
    exchange: string;
    src: string;
    dst: string;
    resolution: string;
    maxBars?: number;
    initialCash?: number;
  }) => {
    const params = new URLSearchParams({
      exchange: options.exchange,
      src: options.src,
      dst: options.dst,
      resolution: options.resolution,
    });
    if (options.maxBars !== undefined) {
      params.set("max_bars", String(options.maxBars));
    }
    if (options.initialCash !== undefined && options.initialCash > 0) {
      params.set("initial_cash", String(options.initialCash));
    }
    return fetchJson<LiveStrategyRanks>(`/api/catalog/live-strategy-ranks?${params.toString()}`);
  },
  strategyParams: (strategyId: string) =>
    fetchJson<{ strategy_id: string; params: StrategyParamField[] }>(
      `/api/catalog/strategy-params?strategy_id=${encodeURIComponent(strategyId)}`,
    ),
  strategyTuneGrid: (strategyId: string, full = false) =>
    fetchJson<{ strategy_id: string; full: boolean; param_grid: Record<string, unknown[]> }>(
      `/api/catalog/strategy-tune-grid?strategy_id=${encodeURIComponent(strategyId)}&full=${full ? "true" : "false"}`,
    ),
  optimizedStrategyParams: (options: {
    strategyId: string;
    symbol?: string;
    resolution?: string;
    datasetId?: string;
  }) => {
    const params = new URLSearchParams({ strategy_id: options.strategyId });
    if (options.symbol) {
      params.set("symbol", options.symbol);
    }
    if (options.resolution) {
      params.set("resolution", options.resolution);
    }
    if (options.datasetId) {
      params.set("dataset_id", options.datasetId);
    }
    return fetchJson<OptimizedStrategyParams>(`/api/catalog/optimized-strategy-params?${params.toString()}`);
  },
  marketsOhlc: (options: {
    src: string;
    dst: string;
    resolution: string;
    maxBars?: number;
    exchange?: string;
  }) => {
    const params = new URLSearchParams({
      src: options.src,
      dst: options.dst,
      resolution: options.resolution,
      max_bars: String(options.maxBars ?? 300),
      exchange: options.exchange ?? "hyperliquid",
    });
    return fetchJson<MarketsOhlcResponse>(`/api/markets/ohlc?${params.toString()}`);
  },
  stopJob: async (jobId: string) => {
    const response = await fetch(
      `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/stop`,
      withLabAuth({ method: "POST" }),
    );
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{ id: string; status: string; stop_requested?: boolean }>;
  },
  /** Re-queue a job with the same stored payload (new job id). */
  restartJob: async (job: JobRow) => {
    const body = { ...job.payload };
    delete body.job_id;
    const response = await fetch(
      `${API_BASE}/api/jobs/${encodeURIComponent(job.job_type)}`,
      withLabAuth({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
    if (!response.ok) {
      const raw = await response.text();
      throw new Error(parseApiErrorBody(raw, response.status));
    }
    return response.json() as Promise<{ id: string; status: string }>;
  },
  riskState: () => fetchJson<Record<string, unknown>>("/api/risk/state"),
  riskKillSwitch: (enabled: boolean) =>
    fetchJson<Record<string, unknown>>("/api/risk/kill-switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  strategyExchangeCatalog: () => fetchJson<StrategyExchangeCatalog>("/api/strategies/exchange-catalog"),
  pairBacktest: (body: Record<string, unknown>) =>
    fetchJson<PairBacktestResult>("/api/strategies/pair-backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  fundingBacktest: (body: Record<string, unknown>) =>
    fetchJson<FundingBacktestResult>("/api/strategies/funding-backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  gridBacktest: (body: Record<string, unknown>) =>
    fetchJson<GridBacktestResult>("/api/strategies/grid-backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  runFinrlPlatform: (body: Record<string, unknown> = {}) =>
    fetchJson<{ id: string; status: string }>("/api/jobs/finrl-platform", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        src: "btc",
        dst: "usdt",
        intervals: "1,5",
        max_bars: 100,
        equity_periods: 100,
        include_equity_rotation: true,
        ...body,
      }),
    }),
  coinbeaconStatus: () =>
    fetchJson<{
      configured: boolean;
      key_count?: number;
      usage?: Record<string, unknown> | null;
      credits?: { remaining?: number | null; limit?: number | null };
      error?: string;
    }>("/api/coinbeacon/status"),
  coinbeaconScreenerPresets: () =>
    fetchJson<{
      presets: Array<{ id: string; label: string; description: string }>;
    }>("/api/coinbeacon/screener/presets"),
  coinbeaconScreener: (preset: string) =>
    fetchJson<Record<string, unknown>>(`/api/coinbeacon/screener?preset=${encodeURIComponent(preset)}`),
  coinbeaconTrendScanner: (params: {
    exchange?: string;
    sort?: string;
    dir?: string;
    quote?: string;
  }) => {
    const search = new URLSearchParams();
    if (params.exchange) search.set("exchange", params.exchange);
    if (params.sort) search.set("sort", params.sort);
    if (params.dir) search.set("dir", params.dir);
    if (params.quote) search.set("quote", params.quote);
    return fetchJson<Record<string, unknown>>(`/api/coinbeacon/trend-scanner?${search.toString()}`);
  },
  discoveryRuns: (limit = 50) =>
    fetchJson<
      Array<{
        id: string;
        job_id: string | null;
        exchange: string;
        status: string;
        summary: Record<string, unknown>;
        config?: Record<string, unknown>;
        scan_kind?: string;
        artifact_path: string | null;
        finished_at_utc: string | null;
      }>
    >(`/api/catalog/discovery-runs?limit=${limit}`),
  discoveryRun: (runId: string) =>
    fetchJson<{
      id: string;
      job_id: string | null;
      exchange: string;
      status: string;
      summary: Record<string, unknown>;
      config?: Record<string, unknown>;
      artifact_path: string | null;
      report?: import("@/lib/opportunityDiscoveryLog").OpportunityDiscoveryReport;
      finished_at_utc: string | null;
    }>(`/api/catalog/discovery-runs/${encodeURIComponent(runId)}`),
  discoveryRunByJob: (jobId: string) =>
    fetchJson<{
      id: string;
      job_id: string | null;
      exchange: string;
      status: string;
      summary: Record<string, unknown>;
      artifact_path: string | null;
      report?: import("@/lib/opportunityDiscoveryLog").OpportunityDiscoveryReport;
      finished_at_utc: string | null;
    }>(`/api/catalog/discovery-runs/by-job/${encodeURIComponent(jobId)}`),
  marketCapGlobal: (refresh = false) =>
    fetchJson<MarketCapGlobal>(`/api/marketcap/global${refresh ? "?refresh=true" : ""}`),
  marketCapCoins: (params?: {
    page?: number;
    limit?: number;
    category?: string;
    search?: string;
    sort_by?: string;
    sort_dir?: string;
    refresh?: boolean;
  }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.category) query.set("category", params.category);
    if (params?.search) query.set("search", params.search);
    if (params?.sort_by) query.set("sort_by", params.sort_by);
    if (params?.sort_dir) query.set("sort_dir", params.sort_dir);
    if (params?.refresh) query.set("refresh", "true");
    const qs = query.toString();
    return fetchJson<MarketCapCoinsResponse>(`/api/marketcap/coins${qs ? `?${qs}` : ""}`);
  },
  marketCapCoin: (id: string) =>
    fetchJson<MarketCapCoin>(`/api/marketcap/coin/${encodeURIComponent(id)}`),
  refreshMarketCap: () =>
    fetchJson<{ status: string; coins_count: number }>("/api/marketcap/refresh", {
      method: "POST",
    }),
  postJob: async (jobType: string, body: Record<string, unknown>) => {
    const response = await fetch(
      `${API_BASE}/api/jobs/${jobType}`,
      withLabAuth({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
    if (!response.ok) {
      if (response.status === 404 || response.status === 405) {
        throw new Error(
          "Lab API is outdated or missing this job route (404/405). Stop the process on port 8765 and run ./run-lab.sh or ./run-lab-api.sh again.",
        );
      }
      const detail = await response.text();
      throw new Error(parseApiErrorBody(detail, response.status) || `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<{ id: string; status: string }>;
  },
};

export type RunAnalyticsSummary = {
  initial_cash: number | null;
  final_equity: number | null;
  net_pnl: number | null;
  return_pct: number | null;
  fills: number;
  round_trips: number;
  open_position: boolean;
  wins: number;
  losses: number;
  win_rate_pct: number | null;
  profit_factor: number | null;
  gross_profit: number | null;
  gross_loss: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  payoff_ratio: number | null;
  expectancy: number | null;
  best_trade: number | null;
  worst_trade: number | null;
  max_win_streak: number;
  max_loss_streak: number;
  max_drawdown_pct: number | null;
  max_drawdown_abs: number | null;
  recovery_factor: number | null;
  sharpe_per_trade: number | null;
  sortino_per_trade: number | null;
  avg_hold_seconds: number | null;
  exposure_pct: number | null;
  total_fees: number | null;
};

export type RunAnalytics = {
  run_id: string;
  summary: RunAnalyticsSummary;
  equity_curve: { timestamp: number | null; equity: number }[];
  drawdown_curve: { timestamp: number | null; drawdown_pct: number | null }[];
  trade_pnls: {
    index: number;
    side: string;
    entry_timestamp: number | null;
    exit_timestamp: number | null;
    pnl: number | null;
    return_pct: number | null;
    duration_seconds: number | null;
  }[];
  by_side: { side: string; trades: number; wins: number; net_pnl: number | null; win_rate_pct: number | null }[];
};

export type MarketCapGlobal = {
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  market_cap_change_24h_pct: number;
  btc_dominance_pct: number;
  eth_dominance_pct: number;
  active_cryptocurrencies: number;
  last_updated_utc: string;
};

export type MarketCapHyperliquid = {
  is_perp_available: boolean;
  funding_rate: number | null;
  open_interest: number | null;
  mark_price: number | null;
  volume_24h_usd: number | null;
};

export type MarketCapCoin = {
  id: string;
  symbol: string;
  name: string;
  image?: string | null;
  current_price: number | null;
  market_cap: number | null;
  market_cap_rank: number | null;
  fully_diluted_valuation: number | null;
  total_volume: number | null;
  high_24h: number | null;
  low_24h: number | null;
  price_change_24h: number | null;
  price_change_percentage_24h: number | null;
  price_change_percentage_1h: number | null;
  price_change_percentage_7d: number | null;
  circulating_supply: number | null;
  total_supply: number | null;
  max_supply: number | null;
  ath: number | null;
  ath_change_percentage: number | null;
  ath_date: string | null;
  atl: number | null;
  atl_change_percentage: number | null;
  atl_date: string | null;
  sparkline: number[];
  hyperliquid?: MarketCapHyperliquid;
  last_updated?: string | null;
};

export type MarketCapCoinsResponse = {
  coins: MarketCapCoin[];
  total: number;
  page: number;
  limit: number;
  categories: string[];
  last_updated_utc: string;
};
