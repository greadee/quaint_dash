import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import App from "./App";

const apiMock = vi.hoisted(() => ({
  overviewUpdates: vi.fn(),
  news: vi.fn(),
  latestNews: vi.fn(),
  breakingNews: vi.fn(),
  newsSearch: vi.fn(),
  newsArticle: vi.fn(),
  markNewsRead: vi.fn(),
  saveNewsArticle: vi.fn(),
  unsaveNewsArticle: vi.fn(),
  newsProviders: vi.fn(),
  newsCategories: vi.fn(),
  signals: vi.fn(),
  signalDetail: vi.fn(),
  updateSignalUserState: vi.fn(),
  createSignalAlert: vi.fn(),
  addWatchlistAsset: vi.fn(),
  portfolios: vi.fn(),
  portfolio: vi.fn(),
  positions: vi.fn(),
  portfolioAnalytics: vi.fn(),
  portfolioPerformance: vi.fn(),
  portfolioRisk: vi.fn(),
  portfolioFundamentals: vi.fn(),
  portfolioNews: vi.fn(),
  aggregatePortfolio: vi.fn(),
  aggregatePositions: vi.fn(),
  transactions: vi.fn(),
  aggregateTransactions: vi.fn(),
  optimizePortfolio: vi.fn(),
  createPortfolio: vi.fn(),
  updatePortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
  deletePosition: vi.fn(),
  comparison: vi.fn(),
  comparisonWorkspace: vi.fn(),
  benchmarks: vi.fn(),
  benchmark: vi.fn(),
  benchmarkPrices: vi.fn(),
  benchmarkMetrics: vi.fn(),
  benchmarkConstituents: vi.fn(),
  benchmarkExposures: vi.fn(),
  assetDefaultBenchmark: vi.fn(),
  portfolioDefaultBenchmark: vi.fn(),
  seedBenchmarks: vi.fn(),
  refreshBenchmark: vi.fn(),
  refreshBenchmarks: vi.fn(),
  hardenBenchmark: vi.fn(),
  hardenBenchmarks: vi.fn(),
  assetBenchmarkAssociations: vi.fn(),
  assets: vi.fn(),
  asset: vi.fn(),
  prices: vi.fn(),
  assetPrices: vi.fn(),
  assetActivity: vi.fn(),
  assetNews: vi.fn(),
  assetAnalytics: vi.fn(),
  assetHoldings: vi.fn(),
  brokerStatus: vi.fn(),
  brokerAccounts: vi.fn(),
  brokerConnections: vi.fn(),
  brokerImportPreview: vi.fn(),
  brokerReconciliation: vi.fn(),
  brokerSyncHistory: vi.fn(),
  registerBrokerUser: vi.fn(),
  saveExistingBrokerUser: vi.fn(),
  brokerPortal: vi.fn(),
  brokerSync: vi.fn(),
  brokerSyncDue: vi.fn(),
  brokerSmokeTest: vi.fn(),
  mapBrokerAccount: vi.fn(),
  importBrokerTransactions: vi.fn(),
  setBrokerRawPayloadStorage: vi.fn(),
  ingestionJobs: vi.fn(),
  clearIngestionHistory: vi.fn(),
  ingestionBackgroundStatus: vi.fn(),
  startIngestionBackground: vi.fn(),
  stopIngestionBackground: vi.fn(),
  tickIngestionBackground: vi.fn(),
  ingestionReadiness: vi.fn(),
  rankingReadiness: vi.fn(),
  scheduleIngestion: vi.fn(),
  runIngestion: vi.fn(),
  retryFailedIngestion: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

vi.mock("recharts", () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    AreaChart: passthrough,
    Area: passthrough,
    LineChart: passthrough,
    Line: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    PieChart: passthrough,
    Pie: passthrough,
    Cell: passthrough,
    CartesianGrid: passthrough,
    Legend: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

function renderApp(route = "/settings") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const portfolio = {
  portfolio_id: 1,
  name: "Core Growth",
  base_ccy: "CAD",
  position_count: 2,
  market_value: 125000,
  book_cost: 100000,
  unrealized_gain: 25000,
  projected_value: null,
  projected_value_low: null,
  projected_value_high: null,
  projected_horizon_years: null,
  as_of: "2026-06-19T12:00:00Z",
  source: "test",
  display_currency: "CAD",
  fx_missing: [],
};

const position = {
  portfolio_id: 1,
  portfolio_name: "Core Growth",
  asset_id: "NVDA",
  symbol: "NVDA",
  name: "NVIDIA",
  asset_type: "Equity",
  allocation_class: "Equity",
  sector: "Technology",
  industry: "Semiconductors",
  country: "US",
  currency: "USD",
  quantity: 10,
  latest_price: 120,
  market_value: 70000,
  book_cost: 50000,
  unrealized_gain: 20000,
  weight: 0.56,
  total_return_percent: 0.4,
  stale_price: false,
  stale_reason: null,
  data_status: "fresh",
  broker_linked: false,
  broker_account_count: 0,
};

const fundamentals = {
  portfolio_id: 1,
  base_currency: "CAD",
  horizon_years: 5,
  weighted_expected_cagr: { value: 0.12, reason: null, coverage: 1 },
  pe_ratio: { value: 28, reason: null, coverage: 1 },
  price_to_free_cash_flow: { value: 22, reason: null, coverage: 1 },
  dividend_yield: { value: 0.01, reason: null, coverage: 1 },
  margin_of_safety: { value: 0.18, reason: null, coverage: 1 },
  valuation_mix: { undervalued_weight: 0.4, fair_value_weight: 0.5, overvalued_weight: 0.1 },
  holdings: [{
    asset_id: "NVDA",
    symbol: "NVDA",
    market_value: 70000,
    weight: 0.56,
    expected_cagr: 0.14,
    expected_cagr_contribution: 0.0784,
    pe_ratio: 32,
    price_to_free_cash_flow: 24,
    coverage_status: "ready",
    missing_inputs: [],
  }],
  missing_inputs: [],
};

const comparisonAsset = (assetId: string, symbol: string) => ({
  asset_id: assetId,
  symbol,
  name: symbol === "NVDA" ? "NVIDIA" : "Advanced Micro Devices",
  sector: "Technology",
  industry: "Semiconductors",
  country: "US",
  currency: "USD",
  latest_price: symbol === "NVDA" ? 120 : 160,
  market_cap: symbol === "NVDA" ? 3_000_000_000_000 : 250_000_000_000,
  market_beta: 1.4,
  returns: { return_1d: 0.01, return_5d: 0.03, return_21d: 0.08, return_252d: 0.42 },
  fundamentals: { revenue: 100_000_000_000, net_income: 30_000_000_000, eps: 2.5, pe_ratio: 32, price_to_sales: 18 },
  valuation: {
    historical_pe_average: 28,
    historical_pe_discount: 0.12,
    sector_pe_average: 30,
    sector_pe_premium: 0.06,
    industry_pe_average: 31,
    industry_pe_premium: 0.03,
  },
});

const signalRow = {
  signal_id: "sig-nvda-momentum",
  definition_id: "momentum_breakout",
  asset_id: "NVDA",
  ticker: "NVDA",
  company_name: "NVIDIA",
  exchange: "NASDAQ",
  signal_name: "Momentum breakout",
  summary: "Price momentum is above the configured confirmation threshold.",
  category: "momentum",
  direction: "positive" as const,
  status: "active",
  strength: 0.81,
  confidence: 0.76,
  portfolio_priority: 0.72,
  raw_observed_value: 12.4,
  normalized_value: 0.8,
  trigger_threshold: 10,
  lookback_period: "21d",
  first_detected_at: "2026-06-18T12:00:00Z",
  confirmation_at: "2026-06-18T13:00:00Z",
  last_evaluated_at: "2026-06-19T12:00:00Z",
  data_as_of: "2026-06-19T00:00:00Z",
  expires_at: null,
  resolved_at: null,
  resolution_reason: null,
  methodology_version: "test-v1",
  source: "local",
  missing_data_status: "complete",
  supporting_evidence: [{
    label: "21d momentum",
    metric: "return_21d",
    value: 0.14,
    score: 0.8,
    detail: "Return exceeds peer baseline.",
    source: "prices",
    as_of: "2026-06-19",
  }],
  contradicting_evidence: [],
  affected_portfolios: [{
    portfolio_id: 1,
    portfolio_name: "Core Growth",
    weight: 0.56,
    market_value: 70000,
    currency: "CAD",
    concentration_note: "Large position",
  }],
  current_portfolio_weight: 0.56,
  historical_efficacy: {
    label: "Momentum history",
    sample_size: 12,
    prior_occurrences: 5,
    median_forward_return: 0.04,
    median_excess_return: 0.02,
    hit_rate: 0.6,
    max_adverse_excursion: -0.08,
    benchmark: "SP500",
    methodology_version: "test-v1",
    warning: null,
  },
  related_signal_ids: [],
  reviewed: false,
  muted: false,
};

const signalDetail = {
  ...signalRow,
  lifecycle: [{ status: "active", timestamp: "2026-06-18T13:00:00Z", label: "Confirmed", detail: "Momentum confirmed." }],
  strength_history: [{ date: "2026-06-19", strength: 0.81, confidence: 0.76, raw_value: 12.4, action: "confirmed" }],
  related_news: [{ title: "NVIDIA shipment update", symbol: "NVDA", provider: "local", published_at: "2026-06-19T10:00:00Z", url: "https://example.test/nvda" }],
  methodology: "Local signal fixture for route coverage.",
  links: {},
  user_state: { reviewed_at: null, muted_until: null, dismissed_until: null, note: null, alert_rule_id: null },
};

const newsArticle = {
  article_id: 1,
  provider_code: "mock_news",
  provider_name: "Mock News",
  provider_article_id: "mock-nvda-1",
  headline: "NVIDIA raises guidance after data center revenue beats expectations",
  summary: "NVIDIA reported stronger data center revenue and raised guidance.",
  canonical_url: "https://example.test/nvda",
  source_name: "Mock Markets",
  author: null,
  language: "en",
  published_at: "2026-06-30T14:30:00Z",
  updated_at: "2026-06-30T14:31:00Z",
  importance_score: 0.88,
  relevance_score: 0.79,
  sentiment_score: null,
  sentiment_label: null,
  is_breaking: true,
  is_press_release: false,
  is_correction: false,
  is_retracted: false,
  is_paywalled: false,
  is_read: false,
  is_saved: false,
  assets: [{ asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", relevance_score: 0.96, confidence_score: 0.95, match_method: "provider_symbol", is_primary_entity: true }],
  categories: [{ category_code: "earnings", category_name: "Earnings", confidence_score: 0.9, is_primary: true }],
  cluster: { cluster_id: 1, cluster_key: "abc", article_count: 1, importance_score: 0.88, first_published_at: "2026-06-30T14:30:00Z", last_updated_at: "2026-06-30T14:31:00Z" },
};

function resetApiMocks() {
  vi.clearAllMocks();
  window.localStorage.clear();
  apiMock.overviewUpdates.mockResolvedValue({
    total_market_value: 125000,
    position_count: 2,
    mover_count: 9,
    news_count: 1,
    price_movers: [
      { asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", change: 1800, change_percent: 0.024, market_value: 70000, weight: 0.56 },
      { asset_id: "AMD", symbol: "AMD", name: "Advanced Micro Devices", change: -300, change_percent: -0.01, market_value: 55000, weight: 0.44 },
      ...Array.from({ length: 7 }, (_, index) => ({
        asset_id: `T${index}`,
        symbol: `T${index}`,
        name: `Test Holding ${index}`,
        change: 10 + index,
        change_percent: 0.001 * index,
        market_value: 1000,
        weight: 0.01,
      })),
    ],
    news: [{ title: "NVIDIA updates outlook", symbol: "NVDA", provider: "local", published_at: "2026-06-19T12:00:00Z", url: "https://example.test/news" }],
  });
  apiMock.news.mockResolvedValue({ items: [newsArticle], total: 1, limit: 25, offset: 0, sort: "recency", generated_at: "2026-06-30T14:40:00Z" });
  apiMock.newsProviders.mockResolvedValue([{ provider_code: "mock_news", provider_name: "Mock News", provider_type: "fixture", is_enabled: true, supports_latest_news: true, supports_symbol_news: true, supports_full_text: false, supports_sentiment: true, supports_categories: true, last_attempted_at: "2026-06-30T14:40:00Z", last_succeeded_at: "2026-06-30T14:40:00Z", last_error_at: null, last_error_message: null, sync_status: "success" }]);
  apiMock.newsCategories.mockResolvedValue([{ category_code: "earnings", category_name: "Earnings", default_importance_weight: 0.75, article_count: 1 }]);
  apiMock.markNewsRead.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: false, saved_at: null });
  apiMock.saveNewsArticle.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: true, saved_at: "2026-06-30T14:41:00Z" });
  apiMock.unsaveNewsArticle.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: false, saved_at: null });
  apiMock.portfolios.mockResolvedValue([portfolio]);
  apiMock.aggregatePortfolio.mockResolvedValue(portfolio);
  apiMock.portfolio.mockResolvedValue(portfolio);
  apiMock.positions.mockResolvedValue([position]);
  apiMock.aggregatePositions.mockResolvedValue([position]);
  apiMock.portfolioPerformance.mockResolvedValue({
    portfolio_id: 1,
    benchmark: "SP500",
    range: "3Y",
    observation_count: 2,
    actual_twr_cagr: 0.13,
    benchmark_cagr: 0.1,
    excess_cagr: 0.03,
    coverage: 1,
    missing_inputs: [],
    points: [
      { date: "2026-06-18", portfolio_value: 125000, portfolio_return_index: 100, benchmark_return_index: 100 },
      { date: "2026-06-19", portfolio_value: 126250, portfolio_return_index: 101, benchmark_return_index: 100.5 },
    ],
  });
  apiMock.portfolioRisk.mockResolvedValue({
    portfolio_id: 1,
    benchmark: "SP500",
    lookback: "3Y",
    risk_free_rate: 0.02,
    annualized_return: 0.13,
    annualized_volatility: 0.22,
    sharpe_ratio: 0.5,
    sortino_ratio: 0.7,
    beta: 1.1,
    alpha: 0.02,
    correlation: 0.8,
    maximum_drawdown: -0.18,
    downside_deviation: 0.12,
    observation_count: 252,
    effective_number_of_holdings: 2,
    hhi: 0.5,
    weight_balance_score: 80,
    sector_concentration: { Technology: 1 },
    geographic_concentration: { US: 1 },
    currency_concentration: { USD: 1 },
    asset_class_concentration: { Equity: 1 },
    missing_inputs: [],
  });
  apiMock.portfolioFundamentals.mockResolvedValue(fundamentals);
  apiMock.portfolioNews.mockResolvedValue({ items: [newsArticle], total: 1, limit: 5, offset: 0, sort: "relevance", generated_at: "2026-06-30T14:40:00Z" });
  apiMock.transactions.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
  apiMock.aggregateTransactions.mockResolvedValue({ items: [], total: 0, limit: 8, offset: 0 });
  apiMock.assets.mockResolvedValue([
    { asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", asset_type: "Equity", sector: "Technology", industry: "Semiconductors", country: "US", currency: "USD" },
    { asset_id: "AMD", symbol: "AMD", name: "Advanced Micro Devices", asset_type: "Equity", sector: "Technology", industry: "Semiconductors", country: "US", currency: "USD" },
  ]);
  apiMock.assetBenchmarkAssociations.mockResolvedValue({
    asset: { asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", asset_type: "Equity", sector: "Technology", industry: "Semiconductors", country: "US", currency: "USD" },
    associations: [{ role: "core", benchmark_index_id: "SP500", index_name: "S&P 500", index_category: "core", reason: "core market baseline", confidence: 0.9 }],
  });
  apiMock.comparison.mockResolvedValue({
    left: comparisonAsset("NVDA", "NVDA"),
    right: comparisonAsset("AMD", "AMD"),
    benchmark: { index_id: "SP500", name: "S&P 500", category: "core", currency: "USD", return_1d: 0.002, return_21d: 0.04, return_252d: 0.18, volatility_252d: 0.16 },
    sector_context: {
      sector: "Technology",
      median: { pe_ratio: 30, price_to_sales: 8, market_cap: 500_000_000_000, beta: 1.2, return_1d: 0.003, return_21d: 0.05, return_252d: 0.25 },
      left_diff_to_median: { pe_ratio: 2, price_to_sales: 10, market_cap: 2_500_000_000_000, beta: 0.2, return_1d: 0.007, return_21d: 0.03, return_252d: 0.17 },
      right_diff_to_median: { pe_ratio: 1, price_to_sales: 2, market_cap: -250_000_000_000, beta: 0.1, return_1d: 0.002, return_21d: 0.01, return_252d: 0.08 },
      benchmark: { index_id: "XLK", name: "Technology Select Sector SPDR", category: "sector", currency: "USD", return_1d: 0.004, return_21d: 0.06, return_252d: 0.2, volatility_252d: 0.19 },
    },
    insights: ["NVDA has stronger 252 day return than the selected benchmark."],
  });
  apiMock.comparisonWorkspace.mockResolvedValue({
    requested_symbols: ["NVDA", "AMD"],
    assets: [comparisonAsset("NVDA", "NVDA"), comparisonAsset("AMD", "AMD")],
    failed_symbols: [],
    benchmark: { index_id: "SP500", name: "S&P 500", category: "core", currency: "USD", return_1d: 0.002, return_21d: 0.04, return_252d: 0.18, volatility_252d: 0.16 },
    historical_series: [
      {
        asset_id: "NVDA",
        symbol: "NVDA",
        mode: "total-return",
        currency: "USD",
        start_date: "2026-06-18",
        end_date: "2026-06-19",
        observation_count: 2,
        source: "test",
        warnings: [],
        points: [
          { date: "2026-06-18", value: 100, close: 118, cumulative_return: 0 },
          { date: "2026-06-19", value: 102, close: 120, cumulative_return: 0.02 },
        ],
      },
      {
        asset_id: "AMD",
        symbol: "AMD",
        mode: "total-return",
        currency: "USD",
        start_date: "2026-06-18",
        end_date: "2026-06-19",
        observation_count: 2,
        source: "test",
        warnings: [],
        points: [
          { date: "2026-06-18", value: 100, close: 150, cumulative_return: 0 },
          { date: "2026-06-19", value: 101, close: 152, cumulative_return: 0.01 },
        ],
      },
    ],
    freshness: {
      NVDA: { latest_price_date: "2026-06-19", latest_price_source: "test", latest_price_ingested_at: "2026-06-19T12:00:00Z", latest_fiscal_period: "2026-03-31", latest_fundamental_source: "test", latest_fundamental_ingested_at: "2026-06-19T12:00:00Z", calculation_timestamp: "2026-06-19T12:00:00Z", provider: "local duckdb", stale: false, stale_reason: null },
      AMD: { latest_price_date: "2026-06-19", latest_price_source: "test", latest_price_ingested_at: "2026-06-19T12:00:00Z", latest_fiscal_period: "2026-03-31", latest_fundamental_source: "test", latest_fundamental_ingested_at: "2026-06-19T12:00:00Z", calculation_timestamp: "2026-06-19T12:00:00Z", provider: "local duckdb", stale: false, stale_reason: null },
    },
    coverage: {
      requested_symbols: ["NVDA", "AMD"],
      resolved_symbols: ["NVDA", "AMD"],
      failed_symbols: [],
      common_start_date: "2026-06-18",
      start_date: "2026-06-18",
      end_date: "2026-06-19",
      benchmark: "SP500",
      currency: "native",
      mode: "total-return",
      calculation_version: "comparison.workspace.v1",
      warnings: [],
    },
    insights: ["Historical series are normalized to 100 at the latest common valid start date using adjusted close where available."],
  });
  apiMock.benchmarks.mockResolvedValue([]);
  apiMock.signals.mockResolvedValue({
    items: [signalRow],
    total: 1,
    limit: 25,
    offset: 0,
    metrics: [{ key: "active", label: "Active", value: 1, filter_params: { status: "active" } }],
    needs_attention: [signalRow],
    top_opportunities: [signalRow],
    generated_at: "2026-06-19T12:00:00Z",
    data_as_of: "2026-06-19T00:00:00Z",
    last_successful_computation_at: "2026-06-19T12:00:00Z",
    partial_provider_failures: [],
    stale_cached_results: false,
    model_version: "test-v1",
    methodology: "Signals use stored local market, sentiment, and portfolio inputs.",
  });
  apiMock.signalDetail.mockResolvedValue(signalDetail);
  apiMock.updateSignalUserState.mockResolvedValue({ reviewed_at: "2026-06-19T12:00:00Z", muted_until: null, dismissed_until: null, note: null, alert_rule_id: null });
  apiMock.createSignalAlert.mockResolvedValue({ alert_rule_id: 1, signal_id: "sig-nvda-momentum", definition_id: "momentum_breakout", asset_id: "NVDA", condition: "status_active", threshold: null, channel: "in_app", is_active: true });
  apiMock.addWatchlistAsset.mockResolvedValue({ asset_id: "NVDA", symbol: "NVDA", is_watchlisted: true });
  apiMock.brokerStatus.mockResolvedValue({
    provider: "snaptrade",
    configured: true,
    broker_profile_ready: true,
    broker_profile_status: "active",
    broker_profile_key: "connor-local",
    raw_payload_storage_enabled: true,
    scheduled_refresh_enabled: false,
    freshness_window_hours: 1,
    max_users_per_run: null,
    last_refresh_at: "2026-06-19T12:00:00Z",
    last_successful_refresh_at: "2026-06-19T12:00:00Z",
    last_scheduled_run_at: null,
    next_eligible_refresh_at: "2026-06-20T12:00:00Z",
    provider_message: null,
  });
  apiMock.brokerConnections.mockResolvedValue([{
    provider: "snaptrade",
    connection_id: 1,
    provider_connection_id: "conn-1",
    institution_name: "Demo Brokerage",
    status: "ACTIVE",
    account_count: 1,
    last_attempted_refresh_at: "2026-06-19T12:00:00Z",
    last_successful_refresh_at: "2026-06-19T12:00:00Z",
    last_error: null,
  }]);
  apiMock.brokerAccounts.mockResolvedValue([{
    provider: "snaptrade",
    provider_account_id: "acct-1",
    provider_connection_id: "conn-1",
    masked_account_number: "****1234",
    account_name: "TFSA",
    account_type: "investment",
    currency: "CAD",
    balance: 5000,
    cash_balance: 1000,
    holdings_value: 4000,
    total_value: 5000,
    position_count: 2,
    latest_position_date: "2026-06-19",
    portfolio_id: 1,
    portfolio_name: "Core Growth",
    available_transaction_count: 2,
    imported_transaction_count: 1,
    unsupported_transaction_count: 0,
    latest_activity_date: "2026-06-19",
    last_imported_at: "2026-06-19T13:00:00Z",
    updated_at: "2026-06-19T12:00:00Z",
  }]);
  apiMock.brokerImportPreview.mockResolvedValue({
    generated_at: "2026-06-19T12:00:00Z",
    total_transactions: 2,
    ready_count: 2,
    already_imported_count: 1,
    unsupported_count: 0,
    needs_review_count: 0,
    unresolved_asset_count: 0,
    failed_validation_count: 0,
    date_start: "2026-06-01",
    date_end: "2026-06-19",
    groups: [],
  });
  apiMock.brokerReconciliation.mockResolvedValue({ generated_at: "2026-06-19T12:00:00Z", items: [] });
  apiMock.brokerSyncHistory.mockResolvedValue([]);
  apiMock.brokerPortal.mockResolvedValue({ url: "https://broker.example.test/portal" });
  apiMock.brokerSync.mockResolvedValue({ status: "ok", result: { synced: 1 } });
  apiMock.brokerSyncDue.mockResolvedValue({ status: "ok", result: { synced: 1 } });
  apiMock.brokerSmokeTest.mockResolvedValue({ status: "ok", result: { configured: true } });
  apiMock.importBrokerTransactions.mockResolvedValue({ status: "ok", result: { imported: 1 } });
  apiMock.setBrokerRawPayloadStorage.mockResolvedValue({ raw_payload_storage_enabled: false });
  apiMock.ingestionJobs.mockResolvedValue([{ job_id: 1, asset_id: "NVDA", domain: "market", job_type: "prices", dataset: "daily", status: "failed", priority: 1, requested_start_date: null, requested_end_date: null, attempt_count: 1, error_message: "provider timeout", created_at: "2026-06-19T12:00:00Z", updated_at: "2026-06-19T12:00:00Z" }]);
  apiMock.ingestionBackgroundStatus.mockResolvedValue({
    enabled: true,
    running: false,
    last_schedule_at: "2026-06-19T12:00:00Z",
    last_schedule_count: 4,
    last_run_at: "2026-06-19T12:10:00Z",
    last_completed_count: 3,
    last_error: null,
    schedule_interval_seconds: 3600,
    run_interval_seconds: 600,
    max_jobs_per_tick: 25,
    max_assets_per_schedule: 50,
    years: 10,
    prices_only: false,
  });
  apiMock.ingestionReadiness.mockResolvedValue({
    total: 1,
    ready_count: 1,
    items: [{ asset_id: "NVDA", symbol: "NVDA", asset_type: "Equity", ready: true, missing: [], requirements: [] }],
  });
  apiMock.rankingReadiness.mockResolvedValue({
    universe: "tracked",
    total: 1,
    ready_count: 1,
    items: [{ asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", universe: "tracked", ready: true, complete_factor_count: 5, total_factor_count: 5, missing: [], requirements: [] }],
  });
  apiMock.scheduleIngestion.mockResolvedValue({ status: "ok", result: { queued: 2 } });
  apiMock.runIngestion.mockResolvedValue({ status: "ok", result: { completed: 1 } });
  apiMock.retryFailedIngestion.mockResolvedValue({ status: "ok", result: { retried: 1 } });
  apiMock.asset.mockResolvedValue({
    asset_id: "NVDA",
    symbol: "NVDA",
    name: "NVIDIA",
    asset_type: "Equity",
    sector: "Technology",
    industry: "Semiconductors",
    country: "US",
    currency: "USD",
    latest_price: 120,
    latest_price_date: "2026-06-19",
    market_cap: 3_000_000_000_000,
    exchange: "NASDAQ",
  });
  apiMock.prices.mockResolvedValue([{ date: "2026-06-18", close: 118 }, { date: "2026-06-19", close: 120 }]);
  apiMock.assetActivity.mockResolvedValue({ items: [{ transaction_id: 1, provider_transaction_id: null, timestamp: "2026-06-19T12:00:00Z", transaction_type: "BUY", source: "local", portfolio_name: "Core Growth", provider_account_id: null, asset_id: "NVDA", quantity: 1, price: 120, cash_amount: null, currency: "USD", fee_amount: null, batch_id: 1 }], total: 1, limit: 10, offset: 0 });
  apiMock.assetNews.mockResolvedValue({ items: [newsArticle], total: 1, limit: 10, offset: 0, sort: "recency", generated_at: "2026-06-30T14:40:00Z" });
  apiMock.assetAnalytics.mockResolvedValue({
    beta: 1.2,
    dcf_fair_value: 135,
    ddm_fair_value: null,
    expected_cagr: 0.14,
    margin_of_safety: 0.13,
    quality_score: 82,
    data_quality: { status: "ready", missing_inputs: [] },
  });
}

describe("App shell", () => {
  beforeEach(() => {
    resetApiMocks();
  });

  it("renders navigation and settings route", async () => {
    renderApp("/settings");

    expect(screen.getByText("Quaint Dash")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Overview/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /News/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Default holdings shown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comfortable" })).toBeInTheDocument();
  });

  it("persists settings changes", async () => {
    const user = userEvent.setup();
    renderApp("/settings");

    await user.selectOptions(screen.getByLabelText(/Default holdings shown/i), "all");
    await user.click(screen.getByLabelText(/Use color for feature icons/i));

    expect(window.localStorage.getItem("quaint_dash_app_settings")).toContain('"moverDefault":"all"');
    expect(window.localStorage.getItem("quaint_dash_app_settings")).toContain('"featureColor":false');
  });

  it("renders overview data and expands the mover list", async () => {
    const user = userEvent.setup();
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(await screen.findByText("Total market value")).toBeInTheDocument();
    expect(screen.getByText("Attention items")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "See all" }));

    expect(screen.getByRole("button", { name: "Show 8" })).toBeInTheDocument();
    expect(screen.getByText("Test Holding 6")).toBeInTheDocument();
  });

  it("renders the news terminal route", async () => {
    renderApp("/news");

    expect(await screen.findByRole("heading", { name: "News Terminal" })).toBeInTheDocument();
    expect((await screen.findAllByText(/NVIDIA raises guidance/)).length).toBeGreaterThan(0);
    expect(screen.getByText("Affected assets")).toBeInTheDocument();
  });

  it("renders aggregate portfolio coverage", async () => {
    renderApp("/portfolios");

    expect(await screen.findByRole("heading", { name: "Portfolios" })).toBeInTheDocument();
    expect(await screen.findByText("Combined market value")).toBeInTheDocument();
    expect(screen.getByText("Asset class allocation")).toBeInTheDocument();
    expect(screen.getByText("Equity")).toBeInTheDocument();
  });

  it("renders portfolio detail analytics tabs", async () => {
    const user = userEvent.setup();
    renderApp("/portfolios/1?tab=overview");

    expect(await screen.findByRole("heading", { name: "Core Growth" })).toBeInTheDocument();
    expect(await screen.findByText("Historical TWR CAGR")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Holdings" }));

    expect(await screen.findByRole("heading", { name: "Positions" })).toBeInTheDocument();
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
  });

  it("renders comparison workspace results with benchmark context", async () => {
    const user = userEvent.setup();
    renderApp("/compare?symbols=NVDA,AMD&benchmark=SP500");

    expect(await screen.findByRole("heading", { name: "Compare" })).toBeInTheDocument();
    expect(await screen.findByText("Actual price comparison")).toBeInTheDocument();
    expect(screen.getByText("Key performance and risk metrics")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Add asset"), "MSFT");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect((await screen.findAllByText("MSFT")).length).toBeGreaterThan(0);
  });

  it("redirects legacy compare route with query state", async () => {
    renderApp("/compare-?symbols=NVDA,AMD&period=1Y");

    expect(await screen.findByRole("heading", { name: "Compare" })).toBeInTheDocument();
    expect(apiMock.comparisonWorkspace).toHaveBeenCalledWith(expect.objectContaining({ symbols: ["AMD", "NVDA"], period: "1Y" }));
  });

  it("renders signals and opens evidence actions", async () => {
    const user = userEvent.setup();
    renderApp("/signals");

    expect(await screen.findByRole("heading", { name: "Signals" })).toBeInTheDocument();
    expect((await screen.findAllByText("Momentum breakout")).length).toBeGreaterThan(0);
    expect(screen.getByText("Needs attention")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Evidence" }));
    expect((await screen.findAllByText("Supporting evidence")).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /Mark reviewed/i })[0]);
    expect(apiMock.updateSignalUserState).toHaveBeenCalledWith("sig-nvda-momentum", { reviewed: true });
  });

  it("renders signal detail lifecycle", async () => {
    renderApp("/signals/sig-nvda-momentum");

    expect(await screen.findByRole("heading", { name: /NVDA/i })).toBeInTheDocument();
    expect(await screen.findByText("Lifecycle")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA shipment update")).toBeInTheDocument();
  });

  it("renders asset detail tabs", async () => {
    const user = userEvent.setup();
    renderApp("/assets/NVDA");

    expect(await screen.findByRole("heading", { level: 1, name: /NVDA/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "NVDA price" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "News" }));
    expect(await screen.findByRole("heading", { name: "News" })).toBeInTheDocument();
    expect(screen.getAllByText(/NVIDIA raises guidance/).length).toBeGreaterThan(0);
  });

  it("renders broker setup and mapped account state", async () => {
    renderApp("/brokers");

    expect(await screen.findByRole("heading", { name: "Brokers" })).toBeInTheDocument();
    expect(await screen.findByText("Demo Brokerage")).toBeInTheDocument();
    expect(screen.getAllByText("TFSA").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mapped Import Ready").length).toBeGreaterThan(0);
  });

  it("renders operations readiness and failed jobs", async () => {
    renderApp("/operations");

    expect(await screen.findByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect((await screen.findAllByText("Routine ingestion")).length).toBeGreaterThan(0);
    expect(screen.getByText("provider timeout")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });
});
