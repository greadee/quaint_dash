export type Portfolio = {
  portfolio_id: number;
  name: string;
  base_ccy: string;
  position_count: number;
  market_value: number;
  book_cost: number;
  unrealized_gain: number | null;
  projected_value: number | null;
  projected_value_low: number | null;
  projected_value_high: number | null;
  projected_horizon_years: number | null;
};

export type Position = {
  asset_id: string;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string;
  quantity: number;
  book_cost: number;
  latest_price: number | null;
  market_value: number | null;
  unrealized_gain: number | null;
  total_return_percent: number | null;
  weight: number | null;
  broker_linked: boolean;
  broker_account_count: number;
};

export type AssetHolding = Position & {
  portfolio_id: number;
  portfolio_name: string;
};

export type AssetActivity = {
  source: string;
  provider: string | null;
  provider_account_id: string | null;
  provider_transaction_id: string | null;
  transaction_id: number | null;
  portfolio_id: number | null;
  portfolio_name: string | null;
  timestamp: string;
  transaction_type: string;
  asset_id: string;
  symbol: string;
  quantity: number | null;
  price: number | null;
  currency: string | null;
  cash_amount: number | null;
};

export type Asset = {
  asset_id: string;
  symbol: string;
  is_cdr: boolean;
  underlying_asset_id: string | null;
  exchange_code: string | null;
  asset_type: string | null;
  asset_subtype: string | null;
  name: string | null;
  description: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  region: string | null;
  size: string | null;
  currency: string;
  market_cap: number | null;
  shares_outstanding: number | null;
  market_beta: number | null;
  latest_price: number | null;
};

export type AssetSearchResult = {
  asset_id: string;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string;
  latest_price: number | null;
};

export type PricePoint = { date: string; close: number };
export type PriceMover = {
  asset_id: string;
  symbol: string;
  name: string | null;
  latest_price: number | null;
  previous_price: number | null;
  change: number | null;
  change_percent: number | null;
  market_value: number | null;
  weight: number | null;
};
export type NewsItem = {
  title: string;
  provider: string | null;
  published_at: string | null;
  url: string | null;
  asset_id: string | null;
  symbol: string | null;
  sentiment: string | null;
};
export type OverviewUpdates = {
  total_market_value: number;
  position_count: number;
  mover_count: number;
  news_count: number;
  price_movers: PriceMover[];
  news: NewsItem[];
};
export type HoldingSignalComponent = {
  name: string;
  metric: string;
  value: number | null;
  contribution: number | null;
  detail: string;
};
export type HoldingSignal = {
  asset_id: string;
  symbol: string;
  name: string | null;
  currency: string;
  market_value: number | null;
  weight: number | null;
  latest_price: number | null;
  timeframe: string;
  return_value: number | null;
  signal_score: number;
  signal_strength: number;
  action: string;
  confidence: number;
  data_points: number;
  components: HoldingSignalComponent[];
};
export type HoldingSignalsResponse = {
  timeframe: string;
  methodology: string;
  items: HoldingSignal[];
};
export type ComparisonReturns = {
  return_1d: number | null;
  return_5d: number | null;
  return_21d: number | null;
  return_252d: number | null;
};
export type ComparisonFundamentals = {
  revenue: number | null;
  net_income: number | null;
  eps: number | null;
  pe_ratio: number | null;
  price_to_sales: number | null;
};
export type ValuationContext = {
  historical_pe_average: number | null;
  historical_pe_discount: number | null;
  sector_pe_average: number | null;
  sector_pe_premium: number | null;
  industry_pe_average: number | null;
  industry_pe_premium: number | null;
};
export type ComparisonAsset = {
  asset_id: string;
  symbol: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string;
  latest_price: number | null;
  market_cap: number | null;
  market_beta: number | null;
  returns: ComparisonReturns;
  fundamentals: ComparisonFundamentals;
  valuation: ValuationContext;
};
export type BenchmarkComparison = {
  index_id: string;
  name: string;
  category: string;
  currency: string;
  return_1d: number | null;
  return_21d: number | null;
  return_252d: number | null;
  volatility_252d: number | null;
};
export type BenchmarkIndexSummary = {
  index_id: string;
  index_name: string;
  index_family: string;
  index_category: string;
  region: string | null;
  country_code: string | null;
  currency: string;
  is_core: boolean;
  is_active: boolean;
  notes: string | null;
  latest_metric_date: string | null;
  latest_close: number | null;
  return_1d: number | null;
  return_21d: number | null;
  return_252d: number | null;
  volatility_252d_ann: number | null;
  latest_composition_date: string | null;
  constituent_count: number | null;
  composition_quality: string | null;
  daily_price_last_success_at: string | null;
  composition_last_success_at: string | null;
  last_error: string | null;
};
export type BenchmarkSymbol = {
  provider: string;
  provider_symbol: string;
  symbol_purpose: string;
  is_primary: boolean;
  is_proxy: boolean;
};
export type BenchmarkSyncState = {
  job_type: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_success_date: string | null;
  last_error: string | null;
  updated_at: string | null;
};
export type BenchmarkIndexDetail = BenchmarkIndexSummary & {
  symbols: BenchmarkSymbol[];
  sync_state: Record<string, BenchmarkSyncState>;
  available_snapshot_dates: string[];
  available_price_range: { first_price_date: string | null; last_price_date: string | null };
  available_metric_range: { first_metric_date: string | null; last_metric_date: string | null };
};
export type BenchmarkPricePoint = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close: number | null;
  volume: number | null;
  source: string;
  source_symbol: string;
  is_proxy: boolean;
};
export type BenchmarkDailyMetric = {
  metric_date: string;
  return_1d: number | null;
  return_5d: number | null;
  return_21d: number | null;
  return_63d: number | null;
  return_126d: number | null;
  return_252d: number | null;
  return_ytd: number | null;
  volatility_21d_ann: number | null;
  volatility_63d_ann: number | null;
  volatility_252d_ann: number | null;
  sma_50: number | null;
  sma_200: number | null;
  high_52w: number | null;
  low_52w: number | null;
  drawdown_from_52w_high: number | null;
};
export type BenchmarkConstituent = {
  index_id: string;
  snapshot_date: string;
  source: string;
  constituent_symbol: string;
  constituent_name: string | null;
  exchange_code: string | null;
  country_code: string | null;
  currency: string | null;
  sector: string | null;
  industry: string | null;
  weight_pct: number | null;
  market_cap: number | null;
  is_proxy: boolean;
};
export type BenchmarkExposure = {
  index_id: string;
  snapshot_date: string;
  dimension_type: string;
  dimension_value: string;
  weight_pct: number;
  source: string;
  source_type: string;
  is_proxy: boolean;
};
export type BenchmarkDefaultResponse = {
  subject_type: string;
  subject_id: string;
  benchmark_index_id: string | null;
  reason: string;
  fallback_used: boolean;
};
export type BenchmarkAssociation = {
  role: string;
  benchmark_index_id: string;
  index_name: string;
  index_category: string;
  reason: string;
  confidence: number;
};
export type AssetBenchmarkAssociationResponse = {
  asset: AssetSearchResult;
  associations: BenchmarkAssociation[];
};
export type BenchmarkFilters = {
  q?: string;
  category?: string;
  currency?: string;
  is_core?: boolean;
  is_active?: boolean;
  limit?: number;
  offset?: number;
};
export type BenchmarkRefreshPayload = {
  job_type: "daily_price" | "intraday_price" | "composition" | "metrics" | "relative_metrics";
  lookback_days?: number;
  interval?: string;
  comparison_index_id?: string;
};
export type BenchmarkBulkRefreshPayload = BenchmarkRefreshPayload & {
  category: "core_geo" | "sector" | "industry" | "theme" | "non_core" | "all";
};
export type ComparisonResponse = {
  left: ComparisonAsset;
  right: ComparisonAsset | null;
  benchmark: BenchmarkComparison | null;
  insights: string[];
};
export type Transaction = {
  transaction_id: number;
  portfolio_id: number;
  timestamp: string;
  transaction_type: string;
  asset_id: string | null;
  quantity: number | null;
  price: number | null;
  currency: string | null;
  cash_amount: number | null;
  fee_amount: number | null;
  batch_id: number;
};
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export type BrokerAccount = {
  provider: string;
  provider_account_id: string;
  provider_connection_id: string;
  account_name: string | null;
  account_type: string | null;
  currency: string | null;
  balance: number | null;
  portfolio_id: number | null;
};
export type BrokerConnection = {
  provider: string;
  connection_id: number | null;
  provider_connection_id: string;
  institution_name: string;
  status: string;
};
export type IngestionJob = {
  job_id: number;
  asset_id: string | null;
  domain: string;
  job_type: string;
  dataset: string;
  status: string;
  priority: number;
  requested_start_date: string | null;
  requested_end_date: string | null;
  attempt_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};
export type IngestionBackgroundStatus = {
  enabled: boolean;
  running: boolean;
  last_schedule_at: string | null;
  last_schedule_count: number | null;
  last_run_at: string | null;
  last_completed_count: number | null;
  last_error: string | null;
  schedule_interval_seconds: number;
  run_interval_seconds: number;
  max_jobs_per_tick: number;
  max_assets_per_schedule: number;
  years: number;
  prices_only: boolean;
};
export type IngestionRequirementStatus = {
  key: string;
  label: string;
  ready: boolean;
  detail: string;
  row_count: number;
  latest_date: string | null;
  open_jobs: number;
  last_error: string | null;
};
export type IngestionAssetReadiness = {
  asset_id: string;
  symbol: string;
  asset_type: string | null;
  ready: boolean;
  missing: string[];
  requirements: IngestionRequirementStatus[];
};
export type IngestionReadiness = {
  items: IngestionAssetReadiness[];
  total: number;
  ready_count: number;
};
export type ActionResult = { status: string; result: Record<string, unknown> };
export type BrokerPortalPayload = { user_key: string; broker?: string | null; reconnect?: string | null };
export type IngestionSchedulePayload = {
  pipeline: string;
  asset_id?: string | null;
  max_assets: number;
  years: number;
  prices_only: boolean;
};
export type IngestionRunPayload = { domain: string; max_jobs: number };
export type IngestionRetryPayload = { domain?: string | null; max_jobs: number };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  overviewUpdates: () => request<OverviewUpdates>("/overview/updates"),
  holdingSignals: (timeframe = "1d") =>
    request<HoldingSignalsResponse>(`/holdings/signals?timeframe=${encodeURIComponent(timeframe)}`),
  comparison: (left: string, right?: string, benchmarkIndexId?: string) => {
    const params = new URLSearchParams({ left });
    if (right) params.set("right", right);
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    return request<ComparisonResponse>(`/comparison?${params.toString()}`);
  },
  benchmarks: (filters: BenchmarkFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    });
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<BenchmarkIndexSummary[]>(`/benchmarks${suffix}`);
  },
  benchmark: (id: string) => request<BenchmarkIndexDetail>(`/benchmarks/${encodeURIComponent(id)}`),
  benchmarkPrices: (id: string, params: { limit?: number; start_date?: string; end_date?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<BenchmarkPricePoint[]>(`/benchmarks/${encodeURIComponent(id)}/prices${suffix}`);
  },
  benchmarkMetrics: (id: string, limit = 365) =>
    request<BenchmarkDailyMetric[]>(`/benchmarks/${encodeURIComponent(id)}/metrics?limit=${limit}`),
  benchmarkConstituents: (id: string, params: { limit?: number; offset?: number; snapshot_date?: string; source?: string; sort?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<Page<BenchmarkConstituent>>(`/benchmarks/${encodeURIComponent(id)}/constituents${suffix}`);
  },
  benchmarkExposures: (id: string, params: { snapshot_date?: string; dimension_type?: string } = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<BenchmarkExposure[]>(`/benchmarks/${encodeURIComponent(id)}/exposures${suffix}`);
  },
  assetDefaultBenchmark: (assetId: string) =>
    request<BenchmarkDefaultResponse>(`/benchmarks/defaults/asset/${encodeURIComponent(assetId)}`),
  portfolioDefaultBenchmark: (portfolioId: number) =>
    request<BenchmarkDefaultResponse>(`/benchmarks/defaults/portfolio/${portfolioId}`),
  seedBenchmarks: (payload: { scope: "core" | "non_core" | "all" }) =>
    request<ActionResult>("/benchmarks/seed", { method: "POST", body: JSON.stringify(payload) }),
  refreshBenchmark: (id: string, payload: BenchmarkRefreshPayload) =>
    request<ActionResult>(`/benchmarks/${encodeURIComponent(id)}/refresh`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  refreshBenchmarks: (payload: BenchmarkBulkRefreshPayload) =>
    request<ActionResult>("/benchmarks/refresh", { method: "POST", body: JSON.stringify(payload) }),
  portfolios: () => request<Portfolio[]>("/portfolios"),
  aggregatePortfolio: () => request<Portfolio>("/portfolios/aggregate/overview"),
  positions: (id: number) => request<Position[]>(`/portfolios/${id}/positions`),
  aggregatePositions: () => request<Position[]>("/portfolios/aggregate/positions"),
  transactions: (id: number, limit = 8, offset = 0) =>
    request<Page<Transaction>>(`/portfolios/${id}/transactions?limit=${limit}&offset=${offset}`),
  aggregateTransactions: (limit = 8, offset = 0) =>
    request<Page<Transaction>>(`/portfolios/aggregate/transactions?limit=${limit}&offset=${offset}`),
  portfolioAnalytics: (id: number, benchmarkIndexId?: string) => {
    const params = new URLSearchParams();
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<Record<string, unknown>>(`/portfolios/${id}/analytics${suffix}`);
  },
  createPortfolio: (name: string, baseCcy = "CAD") =>
    request<Portfolio>("/portfolios", { method: "POST", body: JSON.stringify({ name, base_ccy: baseCcy }) }),
  updatePortfolio: (id: number, name: string) =>
    request<Portfolio>(`/portfolios/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deletePortfolio: (id: number) => request(`/portfolios/${id}`, { method: "DELETE" }),
  deletePosition: (portfolioId: number, assetId: string) =>
    request(`/portfolios/${portfolioId}/positions/${assetId}`, { method: "DELETE" }),
  assets: (q?: string, limit = 25) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q?.trim()) params.set("q", q.trim());
    return request<AssetSearchResult[]>(`/assets?${params.toString()}`);
  },
  asset: (id: string) => request<Asset>(`/assets/${id}`),
  assetBenchmarkAssociations: (assetId: string) =>
    request<AssetBenchmarkAssociationResponse>(`/benchmarks/associations/asset/${encodeURIComponent(assetId)}`),
  assetHoldings: (id: string) => request<AssetHolding[]>(`/assets/${id}/holdings`),
  assetActivity: (id: string, limit = 20, offset = 0) =>
    request<Page<AssetActivity>>(`/assets/${id}/activity?limit=${limit}&offset=${offset}`),
  prices: (id: string, limit = 365) => request<PricePoint[]>(`/assets/${id}/prices?limit=${limit}`),
  assetAnalytics: (id: string, benchmarkIndexId?: string) => {
    const params = new URLSearchParams();
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<Record<string, unknown>>(`/assets/${id}/analytics${suffix}`);
  },
  brokerConnections: () => request<BrokerConnection[]>("/brokers/connections"),
  brokerAccounts: () => request<BrokerAccount[]>("/brokers/accounts"),
  registerBrokerUser: (userKey: string) =>
    request("/brokers/snaptrade/users", { method: "POST", body: JSON.stringify({ user_key: userKey }) }),
  saveExistingBrokerUser: (userKey: string, providerUserId: string, userSecret: string) =>
    request("/brokers/snaptrade/existing-user", {
      method: "POST",
      body: JSON.stringify({
        user_key: userKey,
        provider_user_id: providerUserId,
        user_secret: userSecret,
      }),
    }),
  brokerPortal: (payload: BrokerPortalPayload) =>
    request<{ url: string }>("/brokers/snaptrade/portal", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  brokerSync: (userKey: string) =>
    request<ActionResult>("/brokers/snaptrade/sync", {
      method: "POST",
      body: JSON.stringify({ user_key: userKey }),
    }),
  mapBrokerAccount: (accountId: string, portfolioId: number) =>
    request(`/brokers/accounts/${accountId}/mapping`, {
      method: "POST",
      body: JSON.stringify({ portfolio_id: portfolioId }),
    }),
  importBrokerTransactions: (portfolioId?: number | null) =>
    request<ActionResult>("/brokers/import-transactions", {
      method: "POST",
      body: JSON.stringify({ portfolio_id: portfolioId ?? null }),
    }),
  ingestionJobs: (status?: string, domain?: string, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set("status", status);
    if (domain) params.set("domain", domain);
    return request<IngestionJob[]>(`/ingestion/jobs?${params.toString()}`);
  },
  clearIngestionHistory: () => request<ActionResult>("/ingestion/jobs", { method: "DELETE" }),
  ingestionBackgroundStatus: () => request<IngestionBackgroundStatus>("/ingestion/background/status"),
  ingestionReadiness: () => request<IngestionReadiness>("/ingestion/readiness"),
  scheduleIngestion: (payload: IngestionSchedulePayload) =>
    request<ActionResult>("/ingestion/schedule", { method: "POST", body: JSON.stringify(payload) }),
  runIngestion: (payload: IngestionRunPayload) =>
    request<ActionResult>("/ingestion/run", { method: "POST", body: JSON.stringify(payload) }),
  retryFailedIngestion: (payload: IngestionRetryPayload) =>
    request<ActionResult>("/ingestion/retry-failed", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
