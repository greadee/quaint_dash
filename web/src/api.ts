export type Portfolio = {
  portfolio_id: number;
  name: string;
  base_ccy: string;
  position_count: number;
  market_value: number;
  book_cost: number;
  unrealized_gain: number | null;
  unrealized_return_percent: number | null;
  total_gain: number | null;
  total_return_percent: number | null;
  total_gain_source: string;
  projected_value: number | null;
  projected_value_low: number | null;
  projected_value_high: number | null;
  projected_horizon_years: number | null;
  as_of?: string | null;
  source?: string;
  display_currency?: string | null;
  fx_missing?: string[];
};

export type Position = {
  asset_id: string;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  allocation_class: string;
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
  native_market_value?: number | null;
  base_market_value?: number | null;
  native_book_cost?: number | null;
  base_book_cost?: number | null;
  price_timestamp?: string | null;
  price_source?: string | null;
  price_session?: string | null;
  stale_price?: boolean;
  stale_reason?: string | null;
  data_status?: string;
  sector_exposure?: Record<string, number>;
  industry_exposure?: Record<string, number>;
  country_exposure?: Record<string, number>;
  currency_exposure?: Record<string, number>;
};

export type PortfolioPerformancePoint = {
  date: string;
  portfolio_value: number | null;
  portfolio_return_index: number | null;
  benchmark_return_index: number | null;
};
export type PortfolioPerformance = {
  portfolio_id: number;
  benchmark: string | null;
  base_currency: string;
  start_date: string | null;
  end_date: string | null;
  range: string;
  methodology: string;
  calendar_alignment: string;
  normalized_initial_value: number;
  actual_twr_cagr: number | null;
  historical_cumulative_return: number | null;
  benchmark_cagr: number | null;
  excess_cagr: number | null;
  observation_count: number;
  coverage: number | null;
  missing_inputs: string[];
  points: PortfolioPerformancePoint[];
  as_of: string;
};
export type PortfolioRisk = {
  portfolio_id: number;
  benchmark: string | null;
  risk_free_rate: number;
  risk_free_rate_source: string;
  annualized_return: number | null;
  annualized_volatility: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  beta: number | null;
  alpha: number | null;
  correlation: number | null;
  maximum_drawdown: number | null;
  downside_deviation: number | null;
  observation_count: number;
  effective_number_of_holdings: number | null;
  largest_position: number | null;
  hhi: number | null;
  weight_balance_score: number | null;
  sector_concentration: Record<string, number>;
  geographic_concentration: Record<string, number>;
  currency_concentration: Record<string, number>;
  asset_class_concentration: Record<string, number>;
  average_pairwise_correlation: number | null;
  risk_contribution_concentration: number | null;
  missing_inputs: string[];
  as_of: string;
};
export type PortfolioMetricValue = { value: number | null; reason: string | null; coverage: number | null };
export type PortfolioFundamentalHolding = {
  asset_id: string;
  symbol: string;
  market_value: number | null;
  weight: number | null;
  expected_cagr: number | null;
  expected_cagr_contribution: number | null;
  pe_ratio: number | null;
  price_to_free_cash_flow: number | null;
  dividend_yield: number | null;
  margin_of_safety: number | null;
  coverage_status: string;
  missing_inputs: string[];
};
export type PortfolioFundamentals = {
  portfolio_id: number;
  base_currency: string;
  horizon_years: number;
  weighted_expected_cagr: PortfolioMetricValue;
  pe_ratio: PortfolioMetricValue;
  price_to_free_cash_flow: PortfolioMetricValue;
  dividend_yield: PortfolioMetricValue;
  margin_of_safety: PortfolioMetricValue;
  holdings: PortfolioFundamentalHolding[];
  missing_inputs: string[];
  as_of: string;
};
export type OptimizationConstraints = {
  max_weight?: number;
  max_turnover?: number | null;
  locked_assets?: string[];
  excluded_assets?: string[];
};
export type OptimizationPreview = {
  portfolio_id: number;
  objective: "max_expected_cagr" | "max_risk_adjusted_return";
  status: string;
  solver_message: string;
  current_weights: Record<string, number>;
  optimized_weights: Record<string, number>;
  weight_deltas: Record<string, number>;
  before: { expected_cagr: number | null; expected_volatility: number | null; expected_sharpe: number | null; concentration_hhi: number | null };
  after: { expected_cagr: number | null; expected_volatility: number | null; expected_sharpe: number | null; concentration_hhi: number | null };
  estimated_turnover: number | null;
  binding_constraints: string[];
  excluded_assets: string[];
  input_coverage: Record<string, number>;
  warnings: string[];
  assumptions: string[];
  calculation_timestamp: string;
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
export type NewsArticleAsset = {
  asset_id: string;
  symbol: string;
  name: string | null;
  relevance_score: number;
  confidence_score: number;
  match_method: string;
  is_primary_entity: boolean;
};
export type NewsArticleCategory = {
  category_code: string;
  category_name: string;
  confidence_score: number;
  is_primary: boolean;
};
export type NewsStoryCluster = {
  cluster_id: number;
  cluster_key: string;
  article_count: number;
  importance_score: number;
  first_published_at: string | null;
  last_updated_at: string | null;
};
export type NewsArticle = {
  article_id: number;
  provider_code: string;
  provider_name: string | null;
  provider_article_id: string | null;
  headline: string;
  summary: string | null;
  canonical_url: string | null;
  source_name: string;
  author: string | null;
  language: string | null;
  published_at: string | null;
  updated_at: string | null;
  importance_score: number | null;
  relevance_score: number | null;
  sentiment_score: number | null;
  sentiment_label: string | null;
  is_breaking: boolean;
  is_press_release: boolean;
  is_correction: boolean;
  is_retracted: boolean;
  is_paywalled: boolean;
  is_read: boolean;
  is_saved: boolean;
  assets: NewsArticleAsset[];
  categories: NewsArticleCategory[];
  cluster: NewsStoryCluster | null;
};
export type NewsFeed = {
  items: NewsArticle[];
  total: number;
  limit: number;
  offset: number;
  sort: string;
  generated_at: string;
};
export type NewsProvider = {
  provider_code: string;
  provider_name: string;
  provider_type: string;
  is_enabled: boolean;
  supports_latest_news: boolean;
  supports_symbol_news: boolean;
  supports_full_text: boolean;
  supports_sentiment: boolean;
  supports_categories: boolean;
  last_attempted_at: string | null;
  last_succeeded_at: string | null;
  last_error_at: string | null;
  last_error_message: string | null;
  sync_status: string | null;
};
export type NewsCategory = {
  category_code: string;
  category_name: string;
  default_importance_weight: number;
  article_count: number;
};
export type NewsUserState = {
  article_id: number;
  user_id: string;
  is_read: boolean;
  read_at: string | null;
  is_saved: boolean;
  saved_at: string | null;
};
export type NewsFilters = {
  q?: string;
  provider?: string;
  source?: string;
  asset_id?: string;
  portfolio_id?: number;
  category?: string;
  sentiment?: string;
  breaking?: boolean;
  press_release?: boolean;
  start_date?: string;
  end_date?: string;
  sort?: "recency" | "relevance";
  limit?: number;
  offset?: number;
};
export type OverviewUpdates = {
  total_market_value: number;
  position_count: number;
  mover_count: number;
  news_count: number;
  price_movers: PriceMover[];
  news: NewsItem[];
};
export type StockRankingComponent = {
  name: string;
  metric: string;
  value: number | null;
  score: number | null;
  available: boolean;
  detail: string;
};
export type StockRankingItem = {
  asset_id: string;
  symbol: string;
  name: string | null;
  exchange_code: string | null;
  currency: string;
  latest_price: number | null;
  market_value: number | null;
  is_tracked: boolean;
  is_held: boolean;
  is_watchlisted: boolean;
  score: number;
  score_strength: number;
  action: string;
  confidence: number;
  data_status: string;
  latest_data_date: string | null;
  missing_inputs: string[];
  components: StockRankingComponent[];
};
export type StockRankingsResponse = {
  factor: string;
  universe: string;
  direction: string;
  timeframe: string;
  as_of_date: string;
  include_retail_sentiment: boolean;
  methodology: string;
  total: number;
  data_complete_count: number;
  items: StockRankingItem[];
};
export type StockRankingSnapshotRefreshPayload = {
  factor: string;
  universe: string;
  timeframe?: string;
  limit?: number;
};
export type StockRankingSnapshotRefreshResponse = {
  factor: string;
  universe: string;
  snapshot_date: string;
  refreshed_count: number;
};
export type HoldingSignalComponent = {
  name: string;
  metric: string;
  value: number | null;
  contribution: number | null;
  score: number | null;
  grade: string | null;
  available: boolean;
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
  grade: string;
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
export type WatchlistAssetResponse = {
  asset_id: string;
  symbol: string;
  is_watchlisted: boolean;
};
export type SignalEvidenceItem = {
  label: string;
  metric: string;
  value: number | null;
  score: number | null;
  detail: string;
  source: string;
  as_of: string | null;
};
export type SignalPortfolioImpact = {
  portfolio_id: number;
  portfolio_name: string;
  weight: number | null;
  market_value: number | null;
  currency: string;
  concentration_note: string;
};
export type SignalEfficacyMetadata = {
  label: string;
  sample_size: number;
  prior_occurrences: number | null;
  median_forward_return: number | null;
  median_excess_return: number | null;
  hit_rate: number | null;
  max_adverse_excursion: number | null;
  benchmark: string | null;
  methodology_version: string;
  warning: string | null;
};
export type SignalRow = {
  signal_id: string;
  definition_id: string;
  asset_id: string;
  ticker: string;
  company_name: string | null;
  exchange: string | null;
  signal_name: string;
  summary: string;
  category: string;
  direction: "positive" | "negative" | "neutral";
  status: string;
  strength: number;
  confidence: number;
  portfolio_priority: number;
  raw_observed_value: number | null;
  normalized_value: number | null;
  trigger_threshold: number | null;
  lookback_period: string;
  first_detected_at: string | null;
  confirmation_at: string | null;
  last_evaluated_at: string;
  data_as_of: string | null;
  expires_at: string | null;
  resolved_at: string | null;
  resolution_reason: string | null;
  methodology_version: string;
  source: string;
  missing_data_status: string;
  supporting_evidence: SignalEvidenceItem[];
  contradicting_evidence: SignalEvidenceItem[];
  affected_portfolios: SignalPortfolioImpact[];
  current_portfolio_weight: number | null;
  historical_efficacy: SignalEfficacyMetadata;
  related_signal_ids: string[];
  reviewed: boolean;
  muted: boolean;
};
export type SignalSummaryMetric = {
  key: string;
  label: string;
  value: number;
  filter_params: Record<string, string>;
};
export type SignalHistoryPoint = {
  date: string;
  strength: number;
  confidence: number;
  raw_value: number;
  action: string;
};
export type SignalLifecycleEvent = {
  status: string;
  timestamp: string | null;
  label: string;
  detail: string;
};
export type SignalUserState = {
  reviewed_at: string | null;
  muted_until: string | null;
  dismissed_until: string | null;
  note: string | null;
  alert_rule_id: number | null;
};
export type SignalsSummaryResponse = {
  items: SignalRow[];
  total: number;
  limit: number;
  offset: number;
  metrics: SignalSummaryMetric[];
  needs_attention: SignalRow[];
  top_opportunities: SignalRow[];
  generated_at: string;
  data_as_of: string | null;
  last_successful_computation_at: string | null;
  partial_provider_failures: string[];
  stale_cached_results: boolean;
  model_version: string;
  methodology: string;
};
export type SignalDetailResponse = SignalRow & {
  lifecycle: SignalLifecycleEvent[];
  strength_history: SignalHistoryPoint[];
  related_news: NewsItem[];
  methodology: string;
  links: Record<string, string>;
  user_state: SignalUserState;
};
export type SignalUserStatePayload = {
  reviewed?: boolean;
  muted_until?: string | null;
  dismissed_until?: string | null;
  note?: string | null;
};
export type SignalAlertRulePayload = {
  condition?: string;
  threshold?: number | null;
  channel?: string;
};
export type SignalAlertRuleResponse = {
  alert_rule_id: number;
  signal_id: string;
  definition_id: string;
  asset_id: string;
  condition: string;
  threshold: number | null;
  channel: string;
  is_active: boolean;
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
  forward_eps: number | null;
  forward_revenue: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  price_to_sales: number | null;
  free_cash_flow: number | null;
  free_cash_flow_yield: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  cash: number | null;
  total_debt: number | null;
  net_debt: number | null;
  net_debt_to_ebitda: number | null;
  current_ratio: number | null;
  debt_to_equity: number | null;
  shares_outstanding: number | null;
  dividend_yield: number | null;
  buyback_yield: number | null;
  stock_based_compensation: number | null;
  acquisition_intensity: number | null;
  reinvestment_rate: number | null;
  roic: number | null;
  roic_on_reinvestment: number | null;
  customer_concentration: number | null;
  revenue_concentration: number | null;
  latest_period_end: string | null;
  estimate_as_of: string | null;
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
  fundamental_asset_id?: string | null;
  fundamental_status?: string;
  missing_fundamental_metrics?: string[];
  name: string | null;
  asset_type: string | null;
  exchange_code: string | null;
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
export type SectorComparisonValues = {
  pe_ratio: number | null;
  price_to_sales: number | null;
  market_cap: number | null;
  beta: number | null;
  return_1d: number | null;
  return_21d: number | null;
  return_252d: number | null;
};
export type SectorComparisonContext = {
  sector: string;
  median: SectorComparisonValues;
  left_diff_to_median: SectorComparisonValues;
  right_diff_to_median: SectorComparisonValues | null;
  benchmark: BenchmarkComparison | null;
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
export type BenchmarkHardenPayload = {
  lookback_days?: number;
  include_composition?: boolean;
  include_relative_metrics?: boolean;
  comparison_index_id?: string;
};
export type BenchmarkBulkHardenPayload = BenchmarkHardenPayload & {
  category: "core_geo" | "sector" | "industry" | "theme" | "non_core" | "all";
};
export type ComparisonResponse = {
  left: ComparisonAsset;
  right: ComparisonAsset | null;
  benchmark: BenchmarkComparison | null;
  sector_context: SectorComparisonContext | null;
  insights: string[];
};
export type ComparisonHistoryPoint = {
  date: string;
  value: number | null;
  close: number | null;
  cumulative_return: number | null;
};
export type ComparisonHistorySeries = {
  asset_id: string;
  symbol: string;
  mode: string;
  currency: string;
  start_date: string | null;
  end_date: string | null;
  observation_count: number;
  source: string | null;
  points: ComparisonHistoryPoint[];
  warnings: string[];
};
export type ComparisonFreshness = {
  latest_price_date: string | null;
  latest_price_source: string | null;
  latest_price_ingested_at: string | null;
  latest_fiscal_period: string | null;
  latest_fundamental_source: string | null;
  latest_fundamental_ingested_at: string | null;
  calculation_timestamp: string;
  provider: string;
  stale: boolean;
  stale_reason: string | null;
};
export type ComparisonCoverage = {
  requested_symbols: string[];
  resolved_symbols: string[];
  failed_symbols: string[];
  common_start_date: string | null;
  start_date: string | null;
  end_date: string | null;
  benchmark: string | null;
  currency: string;
  mode: string;
  calculation_version: string;
  warnings: string[];
};
export type ComparisonFxPolicy = {
  display_currency: string;
  native_currency_count: number;
  historical: boolean;
  source: string | null;
  rate_count: number;
  as_of: string | null;
  missing_pairs: string[];
  warnings: string[];
};
export type ComparisonWorkspaceResponse = {
  requested_symbols: string[];
  assets: ComparisonAsset[];
  failed_symbols: string[];
  benchmark: BenchmarkComparison | null;
  historical_series: ComparisonHistorySeries[];
  freshness: Record<string, ComparisonFreshness>;
  coverage: ComparisonCoverage;
  fx_policy: ComparisonFxPolicy;
  insights: string[];
};

export type BusinessStrengthMetric = {
  category_code: string;
  metric_code: string;
  label: string;
  raw_value: number | null;
  normalized_value: number | null;
  metric_score: number | null;
  metric_weight: number;
  contribution: number | null;
  unit: string;
  direction: string;
  value_status: string;
  source: string;
  source_timestamp: string | null;
  peer_percentile: number | null;
  historical_percentile: number | null;
  confidence: number;
  explanation: string;
};

export type BusinessStrengthCategory = {
  category_code: string;
  label: string;
  raw_score: number | null;
  adjusted_score: number | null;
  category_weight: number;
  confidence_score: number;
  completeness_score: number;
  explanation: string;
  metrics: BusinessStrengthMetric[];
};

export type BusinessStrengthScorecard = {
  analysis_run_id: number | null;
  asset_id: string;
  symbol: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  template_code: string;
  template_name: string;
  template_version: number;
  methodology_version: string;
  analysis_date: string;
  source_data_as_of: string | null;
  overall_score: number | null;
  score_10: number | null;
  classification: string;
  confidence_score: number;
  completeness_score: number;
  easy_hold_score: number | null;
  easy_hold_label: string;
  status: string;
  missing_critical_metrics: string[];
  stale_metrics: string[];
  estimated_metrics: string[];
  category_scores: BusinessStrengthCategory[];
  strengths: string[];
  weaknesses: string[];
  peer_group: string[];
  warnings: string[];
  future_research_enabled: boolean;
};

export type BusinessStrengthCompare = {
  methodology_version: string;
  assets: BusinessStrengthScorecard[];
  failed_symbols: string[];
  mixed_templates: boolean;
  common_metric_codes: string[];
  warning: string | null;
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
  masked_account_number: string | null;
  account_name: string | null;
  account_type: string | null;
  currency: string | null;
  balance: number | null;
  cash_balance: number | null;
  holdings_value: number | null;
  total_value: number | null;
  position_count: number;
  latest_position_date: string | null;
  portfolio_id: number | null;
  portfolio_name: string | null;
  available_transaction_count: number;
  imported_transaction_count: number;
  unsupported_transaction_count: number;
  latest_activity_date: string | null;
  last_imported_at: string | null;
  updated_at: string | null;
};
export type BrokerConnection = {
  provider: string;
  connection_id: number | null;
  provider_connection_id: string;
  institution_name: string;
  status: string;
  account_count: number;
  last_attempted_refresh_at: string | null;
  last_successful_refresh_at: string | null;
  last_error: string | null;
};
export type BrokerStatus = {
  provider: string;
  configured: boolean;
  broker_profile_ready: boolean;
  broker_profile_status: string;
  broker_profile_key: string | null;
  raw_payload_storage_enabled: boolean;
  scheduled_refresh_enabled: boolean;
  freshness_window_hours: number;
  max_users_per_run: number | null;
  last_refresh_at: string | null;
  last_successful_refresh_at: string | null;
  last_scheduled_run_at: string | null;
  next_eligible_refresh_at: string | null;
  provider_message: string | null;
};
export type BrokerSyncHistoryItem = {
  sync_run_id: number;
  provider: string;
  user_key: string | null;
  connection_label: string | null;
  trigger_type: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  accounts_processed: number;
  positions_stored: number;
  activities_stored: number;
  status: string;
  error_summary: string | null;
};
export type BrokerImportPreviewItem = {
  provider_transaction_id: string;
  institution_name: string | null;
  account_name: string | null;
  masked_account_number: string | null;
  portfolio_id: number | null;
  portfolio_name: string | null;
  trade_date: string;
  source_type: string;
  category: string;
  status: string;
  symbol: string | null;
  quantity: number | null;
  price: number | null;
  amount: number | null;
  currency: string | null;
  normalization_result: string;
};
export type BrokerImportPreviewGroup = {
  institution_name: string | null;
  account_name: string | null;
  masked_account_number: string | null;
  portfolio_id: number | null;
  portfolio_name: string | null;
  ready_count: number;
  already_imported_count: number;
  unsupported_count: number;
  needs_review_count: number;
  unresolved_asset_count: number;
  failed_validation_count: number;
  category_counts: Record<string, number>;
  items: BrokerImportPreviewItem[];
};
export type BrokerImportPreview = {
  generated_at: string;
  total_transactions: number;
  ready_count: number;
  already_imported_count: number;
  unsupported_count: number;
  needs_review_count: number;
  unresolved_asset_count: number;
  failed_validation_count: number;
  date_start: string | null;
  date_end: string | null;
  groups: BrokerImportPreviewGroup[];
};
export type BrokerReconciliationItem = {
  institution_name: string | null;
  account_name: string | null;
  masked_account_number: string | null;
  ticker: string | null;
  asset_id: string | null;
  broker_quantity: number | null;
  local_quantity: number | null;
  quantity_difference: number | null;
  broker_market_value: number | null;
  local_market_value: number | null;
  value_difference: number | null;
  currency: string | null;
  broker_data_timestamp: string | null;
  local_ledger_timestamp: string | null;
  status: string;
};
export type BrokerReconciliation = {
  generated_at: string;
  items: BrokerReconciliationItem[];
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
  last_pending_count: number | null;
  last_error: string | null;
  schedule_interval_seconds: number;
  run_interval_seconds: number;
  max_jobs_per_tick: number;
  max_run_batches_per_tick: number;
  max_assets_per_schedule: number;
  years: number;
  prices_only: boolean;
};
export type MarketFreshnessStatus = {
  enabled: boolean;
  running: boolean;
  last_poll_at: string | null;
  last_refreshed_count: number | null;
  last_subscription_count: number | null;
  last_error: string | null;
  poll_interval_seconds: number;
  lookback_days: number;
  max_symbols_per_tick: number;
  include_watchlist: boolean;
};
export type DataReadinessWorkerStatus = {
  enabled: boolean;
  running: boolean;
  last_check_at: string | null;
  last_target_count: number | null;
  last_ready_count: number | null;
  last_valuation_count: number | null;
  last_scheduled_count: number | null;
  last_completed_count: number | null;
  last_pending_count: number | null;
  last_missing: string[];
  last_error: string | null;
  poll_interval_seconds: number;
  max_assets_per_tick: number;
  max_jobs_per_batch: number;
  max_run_batches_per_tick: number;
  years: number;
  min_price_rows: number;
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
export type StockRankingReadinessItem = {
  asset_id: string;
  symbol: string;
  name: string | null;
  universe: string;
  ready: boolean;
  complete_factor_count: number;
  total_factor_count: number;
  missing: string[];
  requirements: IngestionRequirementStatus[];
};
export type StockRankingReadiness = {
  universe: string;
  items: StockRankingReadinessItem[];
  total: number;
  ready_count: number;
};
export type ActionResult = { status: string; result: Record<string, unknown> };
export type BrokerPortalPayload = { user_key?: string | null; broker?: string | null; reconnect?: string | null };
export type IngestionSchedulePayload = {
  pipeline: string;
  asset_id?: string | null;
  max_assets: number;
  years: number;
  prices_only: boolean;
  ranking_factor?: string;
  ranking_universe?: string;
  ranking_timeframe?: string;
  missing_only?: boolean;
  stale_only?: boolean;
};
export type IngestionRunPayload = { domain: string; max_jobs: number };
export type IngestionRetryPayload = { domain?: string | null; max_jobs: number };
export type RetailSentimentProviderStatus = {
  provider: string;
  configured: boolean;
  post_count: number;
  latest_post_at: string | null;
  open_jobs: number;
  failed_jobs: number;
  latest_error: string | null;
};
export type RetailSentimentDailySnapshot = {
  asset_id: string;
  ticker: string;
  date: string;
  retail_sentiment_score: number | null;
  reddit_post_count: number;
  x_post_count: number;
  bullish_count: number;
  neutral_count: number;
  bearish_count: number;
  sentiment_momentum_1d: number | null;
  unusual_volume_flag: boolean;
};
export type RetailSentimentPost = {
  provider: string;
  source_name: string;
  ticker: string;
  asset_id: string;
  title: string | null;
  body: string | null;
  url: string | null;
  published_at: string | null;
  score: number | null;
  comment_count: number | null;
  like_count: number | null;
  repost_count: number | null;
  reply_count: number | null;
  relevance_score: number;
};
export type RetailSentimentStatus = {
  providers: RetailSentimentProviderStatus[];
  latest_snapshots: RetailSentimentDailySnapshot[];
  recent_posts: RetailSentimentPost[];
  pending_jobs: number;
  running_jobs: number;
  failed_jobs: number;
};
export type RetailSentimentOverviewPost = {
  provider: string;
  source_name: string;
  title: string | null;
  url: string | null;
  published_at: string | null;
  score: number | null;
  comment_count: number | null;
};
export type RetailSentimentOverviewItem = {
  asset_id: string;
  symbol: string;
  name: string | null;
  is_held: boolean;
  is_watchlisted: boolean;
  market_value: number | null;
  portfolio_names: string[];
  snapshot_date: string | null;
  retail_sentiment_score: number | null;
  sentiment_label: string;
  confidence: number;
  reddit_post_count: number;
  x_post_count: number;
  bullish_count: number;
  neutral_count: number;
  bearish_count: number;
  sentiment_momentum_1d: number | null;
  unusual_volume_flag: boolean;
  source_count: number;
  latest_posts: RetailSentimentOverviewPost[];
};
export type RetailSentimentOverview = {
  generated_at: string;
  methodology: string;
  summary: Record<string, number>;
  holdings: RetailSentimentOverviewItem[];
  popular: RetailSentimentOverviewItem[];
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
  news: (filters: NewsFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    });
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<NewsFeed>(`/news${suffix}`);
  },
  latestNews: (limit = 25, offset = 0) => request<NewsFeed>(`/news/latest?limit=${limit}&offset=${offset}`),
  breakingNews: (limit = 25, offset = 0) => request<NewsFeed>(`/news/breaking?limit=${limit}&offset=${offset}`),
  newsSearch: (params: { q: string; provider?: string; start_date?: string; end_date?: string; sort?: "recency" | "relevance"; limit?: number; offset?: number }) => {
    const query = new URLSearchParams({
      q: params.q,
      sort: params.sort ?? "relevance",
      limit: String(params.limit ?? 25),
      offset: String(params.offset ?? 0),
    });
    if (params.provider) query.set("provider", params.provider);
    if (params.start_date) query.set("start_date", params.start_date);
    if (params.end_date) query.set("end_date", params.end_date);
    return request<NewsFeed>(`/news/search?${query.toString()}`);
  },
  newsArticle: (articleId: number) => request<NewsArticle>(`/news/articles/${articleId}`),
  markNewsRead: (articleId: number) => request<NewsUserState>(`/news/articles/${articleId}/read`, { method: "POST" }),
  saveNewsArticle: (articleId: number) => request<NewsUserState>(`/news/articles/${articleId}/save`, { method: "POST" }),
  unsaveNewsArticle: (articleId: number) => request<NewsUserState>(`/news/articles/${articleId}/save`, { method: "DELETE" }),
  newsProviders: () => request<NewsProvider[]>("/news/providers"),
  newsCategories: () => request<NewsCategory[]>("/news/categories"),
  signals: (params: Record<string, string | number | null | undefined> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<SignalsSummaryResponse>(`/signals${suffix}`);
  },
  signalDetail: (signalId: string) => request<SignalDetailResponse>(`/signals/${encodeURIComponent(signalId)}`),
  updateSignalUserState: (signalId: string, payload: SignalUserStatePayload) =>
    request<SignalUserState>(`/signals/${encodeURIComponent(signalId)}/user-state`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  createSignalAlert: (signalId: string, payload: SignalAlertRulePayload) =>
    request<SignalAlertRuleResponse>(`/signals/${encodeURIComponent(signalId)}/alerts`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  stockRankings: (params: { factor: string; universe: string; direction: string; timeframe?: string; include_retail_sentiment?: boolean; limit?: number; offset?: number }) => {
    const query = new URLSearchParams({
      factor: params.factor,
      universe: params.universe,
      direction: params.direction,
      timeframe: params.timeframe ?? "monthly",
      include_retail_sentiment: String(Boolean(params.include_retail_sentiment)),
      limit: String(params.limit ?? 25),
      offset: String(params.offset ?? 0),
    });
    return request<StockRankingsResponse>(`/rankings/stocks?${query.toString()}`);
  },
  refreshStockRankingSnapshots: (payload: StockRankingSnapshotRefreshPayload) =>
    request<StockRankingSnapshotRefreshResponse>("/rankings/stocks/snapshots", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  addWatchlistAsset: (assetId: string) =>
    request<WatchlistAssetResponse>(`/watchlist/assets/${encodeURIComponent(assetId)}`, {
      method: "POST",
    }),
  comparison: (left: string, right?: string, benchmarkIndexId?: string) => {
    const params = new URLSearchParams({ left });
    if (right) params.set("right", right);
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    return request<ComparisonResponse>(`/comparison?${params.toString()}`);
  },
  comparisonWorkspace: (params: { symbols: string[]; benchmark?: string; period?: string; mode?: string; currency?: string }) => {
    const query = new URLSearchParams({ symbols: params.symbols.join(",") });
    if (params.benchmark) query.set("benchmark", params.benchmark);
    if (params.period) query.set("period", params.period);
    if (params.mode) query.set("mode", params.mode);
    if (params.currency) query.set("currency", params.currency);
    return request<ComparisonWorkspaceResponse>(`/comparison/workspace?${query.toString()}`);
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
  hardenBenchmark: (id: string, payload: BenchmarkHardenPayload) =>
    request<ActionResult>(`/benchmarks/${encodeURIComponent(id)}/harden`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  hardenBenchmarks: (payload: BenchmarkBulkHardenPayload) =>
    request<ActionResult>("/benchmarks/harden", { method: "POST", body: JSON.stringify(payload) }),
  portfolios: () => request<Portfolio[]>("/portfolios"),
  aggregatePortfolio: () => request<Portfolio>("/portfolios/aggregate/overview"),
  portfolio: (id: number) => request<Portfolio>(`/portfolios/${id}`),
  positions: (id: number) => request<Position[]>(`/portfolios/${id}/positions`),
  aggregatePositions: () => request<Position[]>("/portfolios/aggregate/positions"),
  holdingSignals: (timeframe = "1m", portfolioId?: number) => {
    const params = new URLSearchParams({ timeframe });
    if (portfolioId != null) params.set("portfolio_id", String(portfolioId));
    return request<HoldingSignalsResponse>(`/holdings/signals?${params.toString()}`);
  },
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
  portfolioPerformance: (id: number, params: { benchmark?: string; range?: string } = {}) => {
    const query = new URLSearchParams({ range: params.range ?? "1Y" });
    if (params.benchmark) query.set("benchmark", params.benchmark);
    return request<PortfolioPerformance>(`/portfolios/${id}/performance?${query.toString()}`);
  },
  portfolioRisk: (id: number, params: { benchmark?: string; riskFreeRate?: number; lookback?: string } = {}) => {
    const query = new URLSearchParams({ lookback: params.lookback ?? "1Y", risk_free_rate: String(params.riskFreeRate ?? 0) });
    if (params.benchmark) query.set("benchmark", params.benchmark);
    return request<PortfolioRisk>(`/portfolios/${id}/risk?${query.toString()}`);
  },
  portfolioFundamentals: (id: number, horizonYears = 5) =>
    request<PortfolioFundamentals>(`/portfolios/${id}/fundamentals?horizon_years=${horizonYears}`),
  portfolioNews: (id: number, params: { category?: string; sort?: "recency" | "relevance"; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams({
      limit: String(params.limit ?? 10),
      offset: String(params.offset ?? 0),
      sort: params.sort ?? "relevance",
    });
    if (params.category) query.set("category", params.category);
    return request<NewsFeed>(`/portfolios/${id}/news?${query.toString()}`);
  },
  optimizePortfolio: (id: number, objective: OptimizationPreview["objective"], constraints: OptimizationConstraints = {}) =>
    request<OptimizationPreview>(`/portfolios/${id}/optimization/preview`, {
      method: "POST",
      body: JSON.stringify({ objective, constraints }),
    }),
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
  assetNews: (id: string, params: { category?: string; sort?: "recency" | "relevance"; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams({
      limit: String(params.limit ?? 10),
      offset: String(params.offset ?? 0),
      sort: params.sort ?? "recency",
    });
    if (params.category) query.set("category", params.category);
    return request<NewsFeed>(`/assets/${encodeURIComponent(id)}/news?${query.toString()}`);
  },
  prices: (id: string, params: { limit?: number; range?: string } = {}) => {
    const query = new URLSearchParams({ limit: String(params.limit ?? 5000), range: params.range ?? "1Y" });
    return request<PricePoint[]>(`/assets/${id}/prices?${query.toString()}`);
  },
  assetAnalytics: (id: string, benchmarkIndexId?: string) => {
    const params = new URLSearchParams();
    if (benchmarkIndexId) params.set("benchmark_index_id", benchmarkIndexId);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<Record<string, unknown>>(`/assets/${id}/analytics${suffix}`);
  },
  assetBusinessStrength: (id: string) => request<BusinessStrengthScorecard>(`/assets/${encodeURIComponent(id)}/business-strength`),
  recalculateBusinessStrength: (id: string) =>
    request<BusinessStrengthScorecard>(`/assets/${encodeURIComponent(id)}/business-strength/recalculate`, { method: "POST" }),
  compareBusinessStrength: (symbols: string[]) =>
    request<BusinessStrengthCompare>("/compare/business-strength", { method: "POST", body: JSON.stringify({ symbols }) }),
  brokerConnections: () => request<BrokerConnection[]>("/brokers/connections"),
  brokerAccounts: () => request<BrokerAccount[]>("/brokers/accounts"),
  brokerStatus: () => request<BrokerStatus>("/brokers/status"),
  brokerImportPreview: (itemLimit = 25) => request<BrokerImportPreview>(`/brokers/import-preview?item_limit=${itemLimit}`),
  brokerReconciliation: () => request<BrokerReconciliation>("/brokers/reconciliation"),
  brokerSyncHistory: () => request<BrokerSyncHistoryItem[]>("/brokers/sync-history"),
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
  brokerSync: (userKey?: string | null) =>
    request<ActionResult>("/brokers/snaptrade/sync", {
      method: "POST",
      body: JSON.stringify({ user_key: userKey }),
    }),
  brokerSyncDue: (payload: { max_users?: number | null; min_age_hours?: number; force?: boolean } = {}) =>
    request<ActionResult>("/brokers/snaptrade/sync-due", {
      method: "POST",
      body: JSON.stringify({
        max_users: payload.max_users ?? null,
        min_age_hours: payload.min_age_hours ?? 1,
        force: payload.force ?? false,
      }),
    }),
  brokerSmokeTest: () => request<ActionResult>("/brokers/snaptrade/smoke-test", { method: "POST" }),
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
  setBrokerRawPayloadStorage: (enabled: boolean) =>
    request<{ raw_payload_storage_enabled: boolean }>("/brokers/settings/raw-payload-storage", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  ingestionJobs: (status?: string, domain?: string, limit = 100) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set("status", status);
    if (domain) params.set("domain", domain);
    return request<IngestionJob[]>(`/ingestion/jobs?${params.toString()}`);
  },
  retailSentimentStatus: (limit = 10) => request<RetailSentimentStatus>(`/ingestion/retail-sentiment/status?limit=${limit}`),
  retailSentimentOverview: (limit = 25) => request<RetailSentimentOverview>(`/retail-sentiment?limit=${limit}`),
  clearIngestionHistory: () => request<ActionResult>("/ingestion/jobs", { method: "DELETE" }),
  ingestionBackgroundStatus: () => request<IngestionBackgroundStatus>("/ingestion/background/status"),
  startIngestionBackground: () => request<ActionResult>("/ingestion/background/start", { method: "POST" }),
  stopIngestionBackground: () => request<ActionResult>("/ingestion/background/stop", { method: "POST" }),
  tickIngestionBackground: () => request<ActionResult>("/ingestion/background/tick", { method: "POST" }),
  marketFreshnessStatus: () => request<MarketFreshnessStatus>("/market/freshness/status"),
  startMarketFreshness: () => request<ActionResult>("/market/freshness/start", { method: "POST" }),
  stopMarketFreshness: () => request<ActionResult>("/market/freshness/stop", { method: "POST" }),
  tickMarketFreshness: () => request<ActionResult>("/market/freshness/tick", { method: "POST" }),
  dataReadinessStatus: () => request<DataReadinessWorkerStatus>("/data/readiness/status"),
  startDataReadiness: () => request<ActionResult>("/data/readiness/start", { method: "POST" }),
  stopDataReadiness: () => request<ActionResult>("/data/readiness/stop", { method: "POST" }),
  tickDataReadiness: () => request<ActionResult>("/data/readiness/tick", { method: "POST" }),
  ingestionReadiness: () => request<IngestionReadiness>("/ingestion/readiness"),
  rankingReadiness: (params: { universe: string; limit?: number }) => {
    const query = new URLSearchParams({
      universe: params.universe,
      limit: String(params.limit ?? 50),
    });
    return request<StockRankingReadiness>(`/ingestion/ranking-readiness?${query.toString()}`);
  },
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
