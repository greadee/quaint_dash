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
  comparison: (left: string, right?: string, benchmarkIndexId?: string) => {
    const params = new URLSearchParams({ left });
    if (right) params.set("right", right);
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    return request<ComparisonResponse>(`/comparison?${params.toString()}`);
  },
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
  asset: (id: string) => request<Asset>(`/assets/${id}`),
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
  ingestionBackgroundStatus: () => request<IngestionBackgroundStatus>("/ingestion/background/status"),
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
