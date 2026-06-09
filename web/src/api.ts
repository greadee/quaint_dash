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
  weight: number | null;
  broker_linked: boolean;
  broker_account_count: number;
};

export type Asset = {
  asset_id: string;
  symbol: string;
  is_cdr: boolean;
  underlying_asset_id: string | null;
  name: string | null;
  description: string | null;
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
  dataset: string;
  status: string;
  attempt_count: number;
  error_message: string | null;
  updated_at: string;
};

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
  transactions: (id: number) => request<Page<Transaction>>(`/portfolios/${id}/transactions?limit=8`),
  aggregateTransactions: () => request<Page<Transaction>>("/portfolios/aggregate/transactions?limit=8"),
  portfolioAnalytics: (id: number) => request<Record<string, unknown>>(`/portfolios/${id}/analytics`),
  createPortfolio: (name: string) =>
    request<Portfolio>("/portfolios", { method: "POST", body: JSON.stringify({ name }) }),
  updatePortfolio: (id: number, name: string) =>
    request<Portfolio>(`/portfolios/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deletePortfolio: (id: number) => request(`/portfolios/${id}`, { method: "DELETE" }),
  deletePosition: (portfolioId: number, assetId: string) =>
    request(`/portfolios/${portfolioId}/positions/${assetId}`, { method: "DELETE" }),
  asset: (id: string) => request<Asset>(`/assets/${id}`),
  prices: (id: string) => request<PricePoint[]>(`/assets/${id}/prices?limit=365`),
  assetAnalytics: (id: string) => request<Record<string, unknown>>(`/assets/${id}/analytics`),
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
  brokerPortal: (userKey: string) =>
    request<{ url: string }>("/brokers/snaptrade/portal", {
      method: "POST",
      body: JSON.stringify({ user_key: userKey }),
    }),
  brokerSync: (userKey: string) =>
    request("/brokers/snaptrade/sync", {
      method: "POST",
      body: JSON.stringify({ user_key: userKey }),
    }),
  mapBrokerAccount: (accountId: string, portfolioId: number) =>
    request(`/brokers/accounts/${accountId}/mapping`, {
      method: "POST",
      body: JSON.stringify({ portfolio_id: portfolioId }),
    }),
  importBrokerTransactions: () =>
    request("/brokers/import-transactions", { method: "POST", body: JSON.stringify({}) }),
  ingestionJobs: (status?: string, domain?: string) => {
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    if (domain) params.set("domain", domain);
    return request<IngestionJob[]>(`/ingestion/jobs?${params.toString()}`);
  },
  scheduleIngestion: () =>
    request("/ingestion/schedule", { method: "POST", body: JSON.stringify({ pipeline: "all" }) }),
  runIngestion: () =>
    request("/ingestion/run", { method: "POST", body: JSON.stringify({ domain: "all", max_jobs: 1 }) }),
  retryFailedIngestion: (domain?: string) =>
    request("/ingestion/retry-failed", {
      method: "POST",
      body: JSON.stringify({ domain: domain || null, max_jobs: 25 }),
    }),
};
