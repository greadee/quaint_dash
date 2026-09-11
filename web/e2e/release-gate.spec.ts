import { expect, test, type Page } from "@playwright/test";

const now = "2026-09-11T12:00:00Z";

const evidence = (overrides: Record<string, unknown> = {}) => ({
  schema_version: "evidence-display.v1",
  evidence_type: "news",
  source_kind: "real",
  source_name: "local normalized store",
  source_health: "healthy",
  observed_at: now,
  retrieved_at: now,
  freshness_state: "current",
  coverage_state: "complete",
  missing_inputs: [],
  confidence: null,
  effectiveness_sample_size: null,
  action_eligibility: "eligible",
  reason_codes: [],
  ...overrides,
});

const queue = {
  observed_at: now,
  pending_count: 355,
  running_count: 0,
  dead_letter_count: 2,
  failed_count: 0,
  oldest_backlog_at: "2026-09-10T08:00:00Z",
  oldest_backlog_age_seconds: 100800,
  dead_letter_groups: [{
    provider: "fmp",
    error_category: "provider_rate_limit",
    count: 2,
    safe_message: "Provider request limit reached.",
    guidance: "Check provider limits before choosing a bounded retry.",
  }],
  failed_groups: [],
  affected_data_products: ["Earnings and financial statements", "Prices and market history"],
};

const disabledWorker = {
  worker_name: "ingestion_background",
  enabled: false,
  running: false,
  state: "disabled",
  current_failures: {},
  last_failure: null,
  failure_count: 0,
  last_error: null,
  poll_interval_seconds: 900,
  max_assets_per_tick: 10,
  max_jobs_per_batch: 5,
  max_run_batches_per_tick: 2,
  years: 10,
  min_price_rows: 120,
  last_check_at: null,
  last_target_count: null,
  last_ready_count: null,
  last_valuation_count: null,
  last_pending_count: null,
  last_missing: [],
};

const health = {
  observed_at: now,
  status: "critical",
  headline: "Data health needs immediate attention",
  summary: "Provider limits, stale evidence, and blocked queued work affect decision surfaces.",
  incident_count: 6,
  informational_count: 0,
  affected_data_products: [
    "News", "Retail sentiment", "Signals", "Benchmarks", "Fundamentals and valuation inputs",
    "Prices and market history",
  ],
  queue,
  workers: [{ ...disabledWorker, label: "Routine ingestion", affected_data_products: queue.affected_data_products }],
  incidents: [
    {
      code: "dead-letters", severity: "critical", title: "Provider failures need review",
      detail: "FMP requests reached a provider limit.", guidance: "Check provider limits before choosing a bounded retry.",
      affected_data_products: ["News", "Fundamentals and valuation inputs"],
      operations_url: "/operations?incident=dead-letters&status=dead_letter#operations-health",
    },
    {
      code: "social-credentials", severity: "warning", title: "Social sources are unavailable",
      detail: "Reddit and X are not configured and contain zero posts.", guidance: "Configure a supported source before using retail sentiment.",
      affected_data_products: ["Retail sentiment"], operations_url: "/operations?incident=social-credentials#operations-health",
    },
    {
      code: "stale-signals", severity: "warning", title: "Signals are stale",
      detail: "Monthly signal evidence is outside its freshness window.", guidance: "Refresh source inputs before using signal actions.",
      affected_data_products: ["Signals"], operations_url: "/operations?incident=stale-signals#operations-health",
    },
    {
      code: "stale-benchmarks", severity: "warning", title: "Benchmarks are stale or proxy-only",
      detail: "No current direct benchmark observation is available.", guidance: "Treat historical values as audit context.",
      affected_data_products: ["Benchmarks"], operations_url: "/operations?incident=stale-benchmarks#operations-health",
    },
    {
      code: "incomplete-fundamentals", severity: "warning", title: "Fundamental inputs are incomplete",
      detail: "Essential financial-statement inputs are missing.", guidance: "Complete source coverage before decision use.",
      affected_data_products: ["Fundamentals and valuation inputs"], operations_url: "/operations?incident=incomplete-fundamentals#operations-health",
    },
    {
      code: "blocked-backlog", severity: "critical", title: "Old work is waiting without a routine worker",
      detail: "355 jobs are pending while the routine worker is disabled.", guidance: "Review configuration before a bounded run.",
      affected_data_products: ["Prices and market history"], operations_url: "/operations?incident=blocked-backlog&status=pending#operations-health",
    },
  ],
  operations_url: "/operations?incident=dead-letters&status=dead_letter#operations-health",
};

const healthyQueue = {
  ...queue,
  pending_count: 0,
  dead_letter_count: 0,
  oldest_backlog_at: null,
  oldest_backlog_age_seconds: null,
  dead_letter_groups: [],
  affected_data_products: [],
};

const healthyHealth = {
  ...health,
  status: "healthy",
  headline: "Data health is clear",
  summary: "Current real sources and workers have no active incidents.",
  incident_count: 0,
  affected_data_products: [],
  queue: healthyQueue,
  workers: [{ ...disabledWorker, enabled: true, state: "idle", label: "Routine ingestion", affected_data_products: [] }],
  incidents: [],
  operations_url: "/operations#operations-health",
};

const instrument = {
  symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", currency: "USD", local_asset_id: null,
  resolution_status: "unresolved", display_label: "AAPL - Apple Inc.",
};

function productPayload(path: string): unknown {
  if (path === "/operations/health-summary") return health;
  if (path === "/overview/updates") return {
    total_market_value: 100000, position_count: 1, mover_count: 0, news_count: 1,
    price_movers: [], news: [{ title: "Stored market note", symbol: "AAPL", provider: "local", published_at: now, url: null }],
  };
  if (path === "/news") return {
    items: [{
      article_id: 1, provider_code: "mock_news", provider_name: "Mock News", provider_article_id: "sample-1",
      headline: "Sample market story", summary: "Fixture content retained for interface validation.",
      canonical_url: "https://example.test/sample", source_name: "Sample feed", author: null, language: "en",
      published_at: "2026-08-01T12:00:00Z", updated_at: null, importance_score: 0.8, relevance_score: 0.7,
      sentiment_score: null, sentiment_label: null, is_breaking: false, is_press_release: false,
      is_correction: false, is_retracted: false, is_paywalled: false, is_read: false, is_saved: false,
      assets: [], categories: [], cluster: null,
      evidence: evidence({ evidence_type: "news", source_kind: "fixture", source_name: "mock_news", source_health: "degraded", observed_at: "2026-08-01T12:00:00Z", freshness_state: "stale", action_eligibility: "blocked", reason_codes: ["evidence.source.fixture", "evidence.freshness.news.stale"] }),
    }],
    total: 1, limit: 25, offset: 0, sort: "recency", generated_at: now,
    last_successful_sync_at: "2026-08-01T12:00:00Z", provider_status: "degraded",
    provider_message: "FMP is rate limited; showing stale sample records.", is_cached: true,
  };
  if (path === "/news/providers") return [{
    provider_code: "fmp", provider_name: "Financial Modeling Prep", provider_type: "api", is_enabled: true,
    supports_latest_news: true, supports_symbol_news: true, supports_full_text: false, supports_sentiment: false,
    supports_categories: true, last_attempted_at: now, last_succeeded_at: "2026-08-01T12:00:00Z",
    last_error_at: now, last_error_message: "Provider request limit reached.", sync_status: "failed",
  }];
  if (path === "/news/categories") return [];
  if (path === "/retail-sentiment") return {
    generated_at: now, methodology: "Retail sentiment is unavailable.",
    summary: { holding_count: 29, holding_with_sentiment_count: 29, popular_count: 8, total_recent_posts: 150 },
    holdings: [], popular: [],
    evidence: evidence({ evidence_type: "retail_sentiment", source_kind: "unknown", source_name: null, source_health: "blocked", observed_at: null, freshness_state: "blocked", coverage_state: "missing", missing_inputs: ["configured Reddit or X provider"], action_eligibility: "blocked", reason_codes: ["evidence.source_health.blocked"] }),
  };
  if (path === "/rankings/stocks") return { items: [], methodology: "Retail sentiment is excluded." };
  if (path === "/signals/sig-stale") return {
    signal_id: "sig-stale", definition_id: "momentum", asset_id: "AAPL", ticker: "AAPL", company_name: "Apple Inc.", exchange: "NASDAQ",
    signal_name: "Monthly momentum", summary: "Historical signal retained for audit.", category: "momentum", direction: "positive",
    status: "active", strength: 0.9, confidence: 0.99, portfolio_priority: 0.8, raw_observed_value: 12,
    normalized_value: 0.9, trigger_threshold: 10, lookback_period: "1m", first_detected_at: "2026-07-01T00:00:00Z",
    confirmation_at: "2026-07-01T01:00:00Z", last_evaluated_at: "2026-07-01T01:00:00Z", data_as_of: "2026-07-01T00:00:00Z",
    expires_at: null, resolved_at: null, resolution_reason: null, methodology_version: "v1", source: "local", missing_data_status: "complete",
    supporting_evidence: [], contradicting_evidence: [], affected_portfolios: [], current_portfolio_weight: null,
    historical_efficacy: { label: "No efficacy history", sample_size: 0, prior_occurrences: null, median_forward_return: null, median_excess_return: null, hit_rate: null, max_adverse_excursion: null, benchmark: null, methodology_version: "v1", warning: "No historical efficacy sample" },
    related_signal_ids: [], reviewed: false, muted: false, lifecycle: [], strength_history: [], related_news: [],
    methodology: "Stored monthly inputs.", links: {}, user_state: { reviewed_at: null, muted_until: null, dismissed_until: null, note: null, alert_rule_id: null },
    evidence: evidence({ evidence_type: "monthly_signal", source_kind: "inferred", source_name: "signal engine", observed_at: "2026-07-01T00:00:00Z", freshness_state: "stale", effectiveness_sample_size: 0, action_eligibility: "blocked", reason_codes: ["evidence.freshness.monthly_signal.stale", "evidence.effectiveness.no_sample"] }),
  };
  if (path === "/benchmarks") return [{
    index_id: "PROXY", index_name: "Proxy-only benchmark", index_family: "ETF", index_category: "industry", region: "Global",
    country_code: null, currency: "USD", is_core: false, is_active: true, notes: "ETF proxy", latest_metric_date: "2026-06-18",
    latest_close: 250, return_1d: 0.1, return_21d: 0.2, return_252d: 0.8, volatility_252d_ann: 0.3,
    latest_composition_date: "2026-06-18", constituent_count: 30, composition_quality: "proxy",
    daily_price_last_success_at: "2026-06-18T20:00:00Z", composition_last_success_at: "2026-06-18T21:00:00Z",
    last_error: null, primary_provider: "yfinance", primary_symbol: "PROXY", primary_is_proxy: true,
    evidence: evidence({ evidence_type: "benchmark", source_kind: "proxy", source_name: "yfinance", observed_at: "2026-06-18T00:00:00Z", freshness_state: "stale", action_eligibility: "blocked", reason_codes: ["evidence.source.proxy", "evidence.freshness.benchmark.stale"] }),
  }];
  if (path === "/assets/AAPL") return { asset_id: "AAPL", symbol: "AAPL", name: "Apple Inc.", sector: "Technology", latest_price: 200, currency: "USD", evidence: evidence({ evidence_type: "price", observed_at: "2026-08-01T00:00:00Z", freshness_state: "stale", action_eligibility: "blocked", reason_codes: ["evidence.freshness.price.stale"] }) };
  if (path === "/assets/AAPL/analytics") return {
    price_evidence: evidence({ evidence_type: "price", freshness_state: "stale", action_eligibility: "blocked", reason_codes: ["evidence.freshness.price.stale"] }),
    fundamental_evidence: evidence({ evidence_type: "financial_statement", source_kind: "inferred", freshness_state: "unknown", coverage_state: "missing", missing_inputs: ["cash flow statement", "shares outstanding"], action_eligibility: "blocked", reason_codes: ["evidence.coverage.missing"] }),
    report: { forecast: { blended_expected_cagr: 0.2, simulation: { expected_value: 250, expected_cagr: 0.18 } }, discounted_cash_flow: { intrinsic_value_per_share: 240, margin_of_safety: 0.1, inputs_used: {} }, dividend_discount: { intrinsic_value_per_share: null, inputs_used: {} }, valuation_depth: {}, risk: {}, relative: {} }, ai_context: { anomalies: [] },
  };
  if (path === "/assets/AAPL/business-strength") return {
    analysis_run_id: null, asset_id: "AAPL", symbol: "AAPL", name: "Apple Inc.", sector: "Technology", industry: "Hardware",
    template_code: "general", template_name: "General", template_version: 1, methodology_version: "v1", analysis_date: "2026-09-11",
    source_data_as_of: "2026-07-01T00:00:00Z", overall_score: 95, score_10: 9.5, classification: "Strong",
    confidence_score: 100, completeness_score: 100, easy_hold_score: 95, easy_hold_label: "Easy hold", status: "complete",
    missing_critical_metrics: ["cash flow statement"], stale_metrics: [], estimated_metrics: [],
    category_scores: [{
      category_code: "quality", label: "Quality", raw_score: null, adjusted_score: 90, category_weight: 1,
      confidence_score: 100, completeness_score: 100,
      explanation: "Component evidence is incomplete despite the stored aggregate.", metrics: [],
    }],
    strengths: ["Stored aggregate score"], weaknesses: [], peer_group: [], warnings: ["Missing critical evidence"],
    future_research_enabled: false,
    evidence: evidence({ evidence_type: "financial_statement", source_kind: "inferred", source_name: "stored scorecard", observed_at: "2026-07-01T00:00:00Z", freshness_state: "stale", coverage_state: "missing", missing_inputs: ["cash flow statement"], confidence: 1, action_eligibility: "blocked", reason_codes: ["evidence.coverage.missing"] }),
  };
  if (path === "/assets/AAPL/prices") return [];
  if (path === "/assets/AAPL/activity") return { items: [], total: 0, limit: 20, offset: 0 };
  if (path === "/assets/AAPL/news") return { items: [], total: 0, limit: 10, offset: 0, sort: "recency", generated_at: now };
  if (path === "/portfolios") return [];
  if (path === "/brokers/status") return { provider: "snaptrade", configured: true, broker_profile_ready: true, broker_profile_status: "active", broker_profile_key: "s9", raw_payload_storage_enabled: false, scheduled_refresh_enabled: false, freshness_window_hours: 1, max_users_per_run: null, last_refresh_at: now, last_successful_refresh_at: now, last_scheduled_run_at: null, next_eligible_refresh_at: null, provider_message: null };
  if (path === "/brokers/connections") return [{ provider: "snaptrade", connection_id: 1, provider_connection_id: "conn-1", institution_name: "Demo Brokerage", status: "ACTIVE", account_count: 1, last_attempted_refresh_at: now, last_successful_refresh_at: now, last_error: null }];
  if (path === "/brokers/accounts") return [{ provider: "snaptrade", provider_account_id: "acct-1", provider_connection_id: "conn-1", masked_account_number: "****1234", account_name: "TFSA", account_type: "investment", currency: "USD", balance: 450, cash_balance: 0, holdings_value: 450, total_value: 450, position_count: 1, latest_position_date: "2026-09-11", portfolio_id: null, portfolio_name: null, available_transaction_count: 1, imported_transaction_count: 0, unsupported_transaction_count: 0, latest_activity_date: "2026-09-11", last_imported_at: null, updated_at: now }];
  if (path === "/brokers/import-preview") return { generated_at: now, total_transactions: 2806, ready_count: 0, already_imported_count: 0, unsupported_count: 0, needs_review_count: 1, unresolved_asset_count: 2805, failed_validation_count: 0, date_start: "2022-01-01", date_end: "2026-09-11", groups: [] };
  if (path === "/brokers/review-queue") return { generated_at: now, selected_blocker: "unresolved_asset", account_filter: null, counts: { unassigned_account: 1, unresolved_asset: 2805, unsupported_transaction: 0, ready_to_import: 0 }, total: 1, limit: 10, offset: 0, has_more: false, items: [{ blocker: "unresolved_asset", provider: "snaptrade", provider_account_id: "acct-1", provider_transaction_id: "txn-1", institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234", portfolio_id: null, portfolio_name: null, trade_date: "2026-09-11", category: "buys", status: "unresolved_asset", normalization_result: "Needs a resolved local asset before import.", quantity: 1, price: 150, amount: 150, currency: "USD", instrument }] };
  if (path === "/brokers/reconciliation") return { generated_at: now, items: [{ institution_name: "Demo Brokerage", account_name: "TFSA", masked_account_number: "****1234", ticker: "AAPL", asset_id: null, broker_quantity: 3, local_quantity: null, quantity_difference: null, broker_market_value: 450, local_market_value: null, value_difference: null, currency: "USD", broker_data_timestamp: now, local_ledger_timestamp: null, status: "unresolved_asset", instrument }] };
  if (path === "/brokers/sync-history") return [];
  if (path === "/ingestion/jobs") return [];
  if (path === "/ingestion/queue/status") return queue;
  if (path === "/ingestion/background/status") return { ...disabledWorker, schedule_interval_seconds: 3600, run_interval_seconds: 300, max_jobs_per_tick: 5, max_assets_per_schedule: 25, prices_only: false, last_schedule_at: null, last_schedule_count: null, last_run_at: null, last_completed_count: null };
  if (path === "/market/freshness/status") return { ...disabledWorker, worker_name: "market_freshness", lookback_days: 7, include_watchlist: false, max_symbols_per_tick: 25, last_poll_at: null, last_subscription_count: null, last_refreshed_count: null };
  if (path === "/data/readiness/status") return { ...disabledWorker, worker_name: "data_readiness", last_scheduled_count: null, last_completed_count: null };
  if (path === "/ingestion/retail-sentiment/status") return { providers: [{ provider: "reddit", configured: false, post_count: 0 }, { provider: "x", configured: false, post_count: 0 }], latest_snapshots: [], recent_posts: [], pending_jobs: 0, running_jobs: 0, failed_jobs: 0 };
  if (path === "/ingestion/readiness") return { items: [], total: 0, ready_count: 0 };
  if (path === "/ingestion/ranking-readiness") return { universe: "tracked", items: [], total: 0, ready_count: 0 };
  return undefined;
}

async function installReleaseFixtures(page: Page, mode: "critical" | "healthy" = "critical") {
  const unexpected: string[] = [];
  await page.addInitScript(() => localStorage.setItem("quaint_dash_page_features", JSON.stringify({ version: 2, pages: { operations: { "operations.retailSentiment": false, "operations.projectionReadiness": false, "operations.rankingReadiness": false } }, layouts: {} })));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    let payload = productPayload(path);
    if (mode === "healthy") {
      if (path === "/operations/health-summary") payload = healthyHealth;
      if (path === "/ingestion/queue/status") payload = healthyQueue;
      if (path === "/ingestion/background/status") payload = { ...disabledWorker, enabled: true, state: "idle", schedule_interval_seconds: 3600, run_interval_seconds: 300, max_jobs_per_tick: 5, max_assets_per_schedule: 25, prices_only: false, last_schedule_at: now, last_schedule_count: 0, last_run_at: now, last_completed_count: 0 };
    }
    if (request.method() !== "GET" || payload === undefined) {
      unexpected.push(`${request.method()} ${path}`);
      await route.abort();
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
  });
  return unexpected;
}

test.describe("S9 end-to-end release matrix", () => {
  test("current real-source fixture reports a clear system without false incidents", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page, "healthy");
    await page.goto("/");
    await expect(page.getByText("Data health is clear").first()).toBeVisible();
    await expect(page.getByText("0", { exact: true }).first()).toBeVisible();
    await page.goto("/operations");
    await expect(page.getByRole("heading", { name: "Data health is clear" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Queue and worker status" }).getByText("0 jobs", { exact: true }).first()).toBeVisible();
    expect(unexpected).toEqual([]);
  });

  test("critical source state stays consistent from Overview to Operations", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page);
    await page.goto("/");
    await expect(page.getByText("Data health needs immediate attention").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review data health" })).toBeVisible();
    await page.getByRole("link", { name: "Open read-only status" }).click();
    await expect(page).toHaveURL(/\/operations\?incident=dead-letters/);
    await expect(page.getByRole("heading", { name: "Data health needs immediate attention" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Queue and worker status" }).getByText("355 jobs", { exact: true })).toBeVisible();
    expect(unexpected).toEqual([]);
  });

  test("rate-limited news and missing social sources remain visibly non-decisioning", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page);
    await page.goto("/news");
    await expect(page.getByText(/FMP is rate limited/)).toBeVisible();
    await expect(page.getByText(/Sample or fixture story/)).toBeVisible();
    await expect(page.getByRole("link", { name: /Original source/i })).toHaveCount(0);
    await page.goto("/retail-sentiment");
    await expect(page.getByText(/no usable configured Reddit or X evidence/i)).toBeVisible();
    await expect(page.getByRole("checkbox", { name: /Include retail/i })).toBeDisabled();
    await expect(page.getByText("150 recent posts counted")).toHaveCount(0);
    expect(unexpected).toEqual([]);
  });

  test("stale signals, proxy benchmarks, and incomplete models cannot present as actionable", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page);
    await page.goto("/signals/sig-stale");
    await expect(page.getByText(/retained for audit history/i)).toBeVisible();
    await expect(page.getByText(/No historical efficacy sample/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Create alert/i }).first()).toBeDisabled();
    await page.goto("/benchmarks");
    await expect(page.getByText("Benchmark evidence blocked", { exact: true })).toBeVisible();
    await expect(page.getByText(/Metrics remain available for audit/)).toBeVisible();
    await page.goto("/assets/AAPL?tab=fundamentals");
    await expect(page.getByText(/blocks decision use/i).first()).toBeVisible();
    await expect(page.getByText(/calculation audit/i).first()).toBeVisible();
    await page.goto("/assets/AAPL?tab=business-strength");
    await expect(page.getByText(/scorecard ineligible for decision use/i)).toBeVisible();
    await expect(page.getByText("secondary", { exact: true })).toBeVisible();
    await expect(page.getByText(/missing critical inputs/i)).toBeVisible();
    expect(unexpected).toEqual([]);
  });

  test("broker review keeps resolver paths and excludes adversarial provider fields", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page);
    await page.goto("/brokers?tab=import&queue=unresolved_asset");
    await expect(page.getByRole("heading", { name: "Resolve one blocker at a time" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open asset resolver" })).toBeVisible();
    await expect(page.getByText("AAPL - Apple Inc.").first()).toBeVisible();
    await expect(page.getByText(/FIGI|logo_url|provider-position|secret/i)).toHaveCount(0);
    await page.getByRole("button", { name: /Assign accounts/i }).click();
    await expect(page).toHaveURL(/queue=unassigned_account/);
    expect(unexpected).toEqual([]);
  });

  test("every seeded release route stays within the viewport", async ({ page }) => {
    const unexpected = await installReleaseFixtures(page);
    for (const url of ["/", "/operations", "/news", "/retail-sentiment", "/signals/sig-stale", "/benchmarks", "/assets/AAPL?tab=fundamentals", "/assets/AAPL?tab=business-strength", "/brokers?tab=import&queue=unresolved_asset"]) {
      await page.goto(url);
      await expect(page.locator("h1")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), url).toBe(true);
    }
    expect(unexpected).toEqual([]);
  });
});
