import { expect, test, type Page } from "@playwright/test";

const observedAt = "2026-09-10T12:00:00Z";

const queue = {
  observed_at: observedAt,
  pending_count: 12,
  running_count: 1,
  dead_letter_count: 2,
  failed_count: 1,
  oldest_backlog_at: "2026-09-10T09:00:00Z",
  oldest_backlog_age_seconds: 10800,
  dead_letter_groups: [],
  failed_groups: [],
  affected_data_products: ["Prices and market history"],
};

const worker = {
  worker_name: "visual_fixture",
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
  observed_at: observedAt,
  status: "critical",
  headline: "Data health needs immediate attention",
  summary: "12 queued jobs include old work while a routine worker is disabled.",
  incident_count: 2,
  informational_count: 0,
  affected_data_products: ["Prices and market history"],
  queue,
  workers: [{ ...worker, label: "Routine ingestion", affected_data_products: ["Prices and market history"] }],
  incidents: [{
    code: "blocked-backlog",
    severity: "critical",
    title: "Old work is waiting without a routine worker",
    detail: "12 queued jobs include work older than one hour.",
    guidance: "Confirm provider access before a bounded run.",
    affected_data_products: ["Prices and market history"],
    operations_url: "/operations?incident=blocked-backlog#operations-health",
  }],
  operations_url: "/operations?incident=blocked-backlog#operations-health",
};

const account = {
  provider: "snaptrade",
  provider_account_id: "acct-visual",
  provider_connection_id: "conn-visual",
  masked_account_number: "****1234",
  account_name: "Long-term TFSA",
  account_type: "investment",
  currency: "CAD",
  balance: 126500,
  cash_balance: 6500,
  holdings_value: 120000,
  total_value: 126500,
  position_count: 8,
  latest_position_date: "2026-09-10",
  portfolio_id: 1,
  portfolio_name: "Core Growth",
  available_transaction_count: 24,
  imported_transaction_count: 20,
  unsupported_transaction_count: 1,
  latest_activity_date: "2026-09-10",
  last_imported_at: "2026-09-10T11:45:00Z",
  updated_at: observedAt,
};

const instrument = {
  symbol: "NVDA",
  name: "NVIDIA Corporation",
  exchange: "NASDAQ",
  currency: "USD",
  local_asset_id: "NVDA",
  resolution_status: "resolved",
  display_label: "NVDA - NVIDIA Corporation",
};

const importItem = {
  provider: "snaptrade",
  provider_transaction_id: "txn-visual",
  provider_account_id: account.provider_account_id,
  institution_name: "Demo Brokerage",
  account_name: account.account_name,
  masked_account_number: account.masked_account_number,
  portfolio_id: 1,
  portfolio_name: "Core Growth",
  trade_date: "2026-09-10",
  source_type: "BUY",
  category: "buys",
  status: "ready",
  symbol: "NVDA",
  quantity: 2,
  price: 175,
  amount: 350,
  currency: "USD",
  normalization_result: "Ready for idempotent import.",
  instrument,
};

const benchmarkSummaries = [
  {
    index_id: "DEV_INTL", index_name: "Developed International Equity", index_family: "MSCI/FTSE",
    index_category: "core_geo", region: "Developed ex-North America", country_code: null, currency: "USD",
    is_core: true, is_active: true, notes: "Broad developed market benchmark", latest_metric_date: "2026-09-10",
    latest_close: 101, return_1d: 0.01, return_21d: 0.03, return_252d: 0.12, volatility_252d_ann: 0.16,
    latest_composition_date: "2026-09-10", constituent_count: 1500, composition_quality: "exact",
    daily_price_last_success_at: observedAt, composition_last_success_at: observedAt, last_error: null,
    primary_provider: "yfinance", primary_symbol: "VEA", primary_is_proxy: false,
  },
  {
    index_id: "IND_SEMICONDUCTORS", index_name: "Semiconductors Industry", index_family: "iShares",
    index_category: "industry", region: "Global", country_code: null, currency: "USD", is_core: false,
    is_active: true, notes: "ETF proxy for semiconductor industry benchmark", latest_metric_date: "2026-08-01",
    latest_close: 250, return_1d: -0.01, return_21d: 0.06, return_252d: 0.32, volatility_252d_ann: 0.28,
    latest_composition_date: "2026-08-01", constituent_count: 30, composition_quality: "proxy",
    daily_price_last_success_at: "2026-08-01T20:00:00Z", composition_last_success_at: "2026-08-01T21:00:00Z",
    last_error: null, primary_provider: "yfinance", primary_symbol: "SOXX", primary_is_proxy: true,
  },
];

const payloadFor = (path: string): unknown => {
  if (path === "/operations/health-summary") return health;
  if (path === "/overview/updates") return {
    total_market_value: 245000, position_count: 9, mover_count: 2, news_count: 1,
    price_movers: [
      { asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA", change: 1120, change_percent: 0.031, market_value: 42000, weight: 0.171 },
      { asset_id: "MSFT", symbol: "MSFT", name: "Microsoft", change: -240, change_percent: -0.006, market_value: 36000, weight: 0.147 },
    ],
    news: [{ title: "Stored market note for held assets", symbol: "NVDA", provider: "local", published_at: observedAt, url: null }],
  };
  if (path === "/portfolios") return [{ portfolio_id: 1, name: "Core Growth", base_ccy: "CAD", position_count: 8, market_value: 245000, book_cost: 190000, unrealized_gain: 55000, as_of: observedAt, display_currency: "CAD", fx_missing: [] }];
  if (path === "/brokers/accounts") return [account];
  if (path === "/brokers/connections") return [{ provider: "snaptrade", connection_id: 1, provider_connection_id: "conn-visual", institution_name: "Demo Brokerage", status: "ACTIVE", account_count: 1, last_attempted_refresh_at: observedAt, last_successful_refresh_at: observedAt, last_error: null }];
  if (path === "/brokers/status") return { provider: "snaptrade", configured: true, broker_profile_ready: true, broker_profile_status: "active", broker_profile_key: "visual-fixture", raw_payload_storage_enabled: false, scheduled_refresh_enabled: false, freshness_window_hours: 1, max_users_per_run: null, last_refresh_at: observedAt, last_successful_refresh_at: observedAt, last_scheduled_run_at: null, next_eligible_refresh_at: null, provider_message: null };
  if (path === "/brokers/import-preview") return {
    generated_at: observedAt, total_transactions: 24, ready_count: 3, already_imported_count: 20,
    unsupported_count: 1, needs_review_count: 0, unresolved_asset_count: 0, failed_validation_count: 0,
    date_start: "2026-08-01", date_end: "2026-09-10",
    groups: [{ provider: "snaptrade", provider_account_id: account.provider_account_id, institution_name: "Demo Brokerage", account_name: account.account_name, masked_account_number: account.masked_account_number, portfolio_id: 1, portfolio_name: "Core Growth", ready_count: 3, already_imported_count: 20, unsupported_count: 1, needs_review_count: 0, unresolved_asset_count: 0, failed_validation_count: 0, category_counts: { buys: 3 }, items: [importItem] }],
  };
  if (path === "/brokers/review-queue") return { generated_at: observedAt, selected_blocker: "unassigned_account", account_filter: null, counts: { unassigned_account: 0, unresolved_asset: 0, unsupported_transaction: 1, ready_to_import: 3 }, total: 0, limit: 10, offset: 0, has_more: false, items: [] };
  if (path === "/brokers/reconciliation") return { generated_at: observedAt, items: [] };
  if (path === "/brokers/sync-history") return [];
  if (path === "/benchmarks") return benchmarkSummaries;
  if (path === "/signals") return {
    items: [], total: 0, limit: 25, offset: 0,
    metrics: [
      { key: "blocked", label: "Blocked or stale", value: 4, filter_params: { completeness: "incomplete" } },
      { key: "active", label: "Decision eligible", value: 2, filter_params: { status: "active" } },
      { key: "review", label: "Needs review", value: 3, filter_params: { reviewed: "false" } },
      { key: "coverage", label: "Coverage gaps", value: 1, filter_params: { completeness: "incomplete" } },
    ],
    needs_attention: [], top_opportunities: [], generated_at: observedAt, data_as_of: "2026-08-01T00:00:00Z",
    last_successful_computation_at: "2026-08-01T12:00:00Z", partial_provider_failures: ["sentiment input coverage"],
    stale_cached_results: true, model_version: "signals.rankings.v1", methodology: "Stored local ranking inputs.",
  };
  if (path === "/assets/NVDA") return { asset_id: "NVDA", symbol: "NVDA", name: "NVIDIA Corporation with a descriptive company name", sector: "Technology", latest_price: 175.32, currency: "USD", evidence: { freshness_state: "warning", action_eligibility: "caution" } };
  if (path === "/assets/NVDA/news") return {
    items: [{ article_id: 1, headline: "A long asset headline stays paired with its publication timestamp on every breakpoint", published_at: observedAt, source_name: "Local normalized feed", provider: "local", categories: [], assets: [], evidence: { freshness_state: "warning", action_eligibility: "caution" } }],
    total: 1, limit: 10, offset: 0, sort: "recency", generated_at: observedAt,
  };
  if (path === "/ingestion/jobs") return [];
  if (path === "/ingestion/queue/status") return queue;
  if (path === "/ingestion/background/status") return { ...worker, worker_name: "ingestion_background", enabled: false, schedule_interval_seconds: 3600, run_interval_seconds: 300, max_jobs_per_tick: 5, max_assets_per_schedule: 25, prices_only: false, last_schedule_at: null, last_schedule_count: null, last_run_at: null, last_completed_count: null };
  if (path === "/market/freshness/status") return { ...worker, worker_name: "market_freshness", lookback_days: 7, include_watchlist: false, max_symbols_per_tick: 25, last_poll_at: null, last_subscription_count: null, last_refreshed_count: null };
  if (path === "/data/readiness/status") return { ...worker, worker_name: "data_readiness", last_scheduled_count: null, last_completed_count: null };
  if (path === "/ingestion/retail-sentiment/status") return { providers: [], latest_snapshots: [], recent_posts: [], pending_jobs: 0, running_jobs: 0, failed_jobs: 0 };
  if (path === "/ingestion/readiness") return { items: [], total: 0, ready_count: 0 };
  if (path === "/ingestion/ranking-readiness") return { universe: "tracked", items: [], total: 0, ready_count: 0 };
  return undefined;
};

async function installVisualFixtures(page: Page) {
  const unexpected: string[] = [];
  await page.addInitScript(() => {
    localStorage.setItem("quaint_dash_app_settings", JSON.stringify({ theme: "dark", moverDefault: "8", density: "comfortable", featureColor: true }));
    localStorage.setItem("quaint_dash_page_features", JSON.stringify({ version: 2, pages: {
      operations: { "operations.retailSentiment": false, "operations.projectionReadiness": false, "operations.rankingReadiness": false },
    }, layouts: {} }));
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const payload = payloadFor(path);
    if (request.method() !== "GET" || payload === undefined) {
      unexpected.push(`${request.method()} ${path}`);
      await route.abort();
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(payload) });
  });
  return unexpected;
}

const cases = [
  { name: "overview", url: "/", heading: "Overview" },
  { name: "signals", url: "/signals", heading: "Signals" },
  { name: "asset-news", url: "/assets/NVDA?tab=news", heading: /NVDA/ },
  { name: "benchmarks", url: "/benchmarks", heading: "Benchmarks" },
  { name: "brokers", url: "/brokers", heading: "Brokers" },
  { name: "broker-import", url: "/brokers?tab=import", heading: "Brokers" },
  { name: "operations", url: "/operations", heading: "Operations" },
] as const;

test.describe("S8 visual baselines", () => {
  for (const item of cases) {
    test(`${item.name} has stable hierarchy and no viewport overflow`, async ({ page }) => {
      const unexpected = await installVisualFixtures(page);
      await page.goto(item.url);
      await expect(page.getByRole("heading", { level: 1, name: item.heading })).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.fonts.status)).toBe("loaded");
      const overflow = await page.evaluate(() => {
        if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
        return Array.from(document.querySelectorAll<HTMLElement>("body *"))
          .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
          .slice(0, 12)
          .map((element) => ({
            element: `${element.tagName.toLowerCase()}.${element.className}`,
            left: Math.round(element.getBoundingClientRect().left),
            right: Math.round(element.getBoundingClientRect().right),
          }));
      });
      expect(overflow).toEqual([]);
      const unnamedIconActions = await page.locator("button, a").evaluateAll((elements) => elements
        .filter((element) => {
          const html = element as HTMLElement;
          const rect = html.getBoundingClientRect();
          const visible = rect.width > 0 && rect.height > 0 && getComputedStyle(html).visibility !== "hidden";
          const iconOnly = Boolean(html.querySelector("svg, img")) && !html.innerText.trim();
          return visible && iconOnly && !html.getAttribute("aria-label") && !html.getAttribute("title");
        })
        .map((element) => element.outerHTML.slice(0, 180)));
      expect(unnamedIconActions).toEqual([]);
      expect(unexpected).toEqual([]);
      await expect(page).toHaveScreenshot(`${item.name}.png`, { animations: "disabled", caret: "hide", fullPage: false });
    });
  }

  test("mobile navigation is named and keyboard reachable", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "Mobile navigation is only rendered below the shell breakpoint.");
    await installVisualFixtures(page);
    await page.goto("/");
    const menu = page.getByRole("button", { name: "Open navigation" });
    await expect(menu).toBeVisible();
    await menu.focus();
    await expect(menu).toBeFocused();
    expect(await menu.evaluate((element) => getComputedStyle(element).outlineStyle)).not.toBe("none");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Close navigation" })).toBeVisible();
  });

  test("direct New Portfolio path remains visible", async ({ page }) => {
    await installVisualFixtures(page);
    await page.goto("/portfolios");
    await expect(page.getByRole("button", { name: /New portfolio/i })).toBeVisible();
  });

  test("broker import detail groups default closed", async ({ page }) => {
    await installVisualFixtures(page);
    await page.goto("/brokers?tab=import");
    await expect(page.getByRole("heading", { name: "Review eligible activity before importing" })).toBeVisible();
    await expect(page.locator("details.broker-import-scope")).not.toHaveAttribute("open", "");
    await expect(page.locator("details.broker-preview-group")).not.toHaveAttribute("open", "");
  });
});
