export type Portfolio = {
  portfolio_id: number;
  name: string;
  base_ccy: string;
  position_count: number;
  market_value: number;
  book_cost: number;
  unrealized_gain: number | null;
};

export type Position = {
  asset_id: string;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  currency: string;
  quantity: number;
  book_cost: number;
  latest_price: number | null;
  market_value: number | null;
  unrealized_gain: number | null;
  weight: number | null;
};

export type Asset = {
  asset_id: string;
  symbol: string;
  name: string | null;
  description: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string;
  latest_price: number | null;
};

export type PricePoint = { date: string; close: number };
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
  account_name: string | null;
  account_type: string | null;
  currency: string | null;
  balance: number | null;
  portfolio_id: number | null;
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
  portfolios: () => request<Portfolio[]>("/portfolios"),
  positions: (id: number) => request<Position[]>(`/portfolios/${id}/positions`),
  transactions: (id: number) => request<Page<Transaction>>(`/portfolios/${id}/transactions?limit=8`),
  portfolioAnalytics: (id: number) => request<Record<string, unknown>>(`/portfolios/${id}/analytics`),
  createPortfolio: (name: string) =>
    request<Portfolio>("/portfolios", { method: "POST", body: JSON.stringify({ name }) }),
  asset: (id: string) => request<Asset>(`/assets/${id}`),
  prices: (id: string) => request<PricePoint[]>(`/assets/${id}/prices?limit=365`),
  assetAnalytics: (id: string) => request<Record<string, unknown>>(`/assets/${id}/analytics`),
  brokerAccounts: () => request<BrokerAccount[]>("/brokers/accounts"),
  mapBrokerAccount: (accountId: string, portfolioId: number) =>
    request(`/brokers/accounts/${accountId}/mapping`, {
      method: "POST",
      body: JSON.stringify({ portfolio_id: portfolioId }),
    }),
  importBrokerTransactions: () =>
    request("/brokers/import-transactions", { method: "POST", body: JSON.stringify({}) }),
  ingestionJobs: () => request<IngestionJob[]>("/ingestion/jobs?limit=100"),
  scheduleIngestion: () =>
    request("/ingestion/schedule", { method: "POST", body: JSON.stringify({ pipeline: "all" }) }),
  runIngestion: () =>
    request("/ingestion/run", { method: "POST", body: JSON.stringify({ domain: "all", max_jobs: 1 }) }),
};
