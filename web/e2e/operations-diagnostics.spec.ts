import { expect, test, type Page } from "@playwright/test";

const failure = {
  worker_name: "ingestion_background", phase: "schedule", category: "scheduler_query",
  safe_message: "The scheduler could not execute its database query.",
  guidance: "Review the server diagnostics before running another cycle.",
  occurred_at: "2026-09-07T11:00:00Z", count: 3,
};
const queue = {
  observed_at: "2026-09-07T12:00:00Z", pending_count: 701, running_count: 1,
  dead_letter_count: 5, failed_count: 2,
  oldest_backlog_at: "2026-09-01T12:00:00Z", oldest_backlog_age_seconds: 6 * 86400,
  dead_letter_groups: [{ provider: "fmp", error_category: "provider_rate_limit", count: 5,
    safe_message: "Provider request limit reached.", guidance: "Check provider limits before choosing a bounded retry." }],
  failed_groups: [{ provider: "x", error_category: "provider_configuration", count: 2,
    safe_message: "Provider access or configuration needs attention.", guidance: "Check credentials before retrying." }],
  affected_data_products: ["Fundamentals and valuation inputs", "Prices and market history"],
};
const disabled = {
  worker_name: "test", enabled: false, running: false, state: "disabled",
  current_failures: {}, last_failure: null, failure_count: 0, last_error: null,
  poll_interval_seconds: 900, max_assets_per_tick: 10, max_jobs_per_batch: 5,
  max_run_batches_per_tick: 2, years: 10, min_price_rows: 120,
  last_check_at: null, last_target_count: null, last_ready_count: null,
  last_valuation_count: null, last_pending_count: null, last_missing: [],
  last_poll_at: null, last_subscription_count: null, last_refreshed_count: null,
  lookback_days: 7, include_watchlist: false, max_symbols_per_tick: 25,
};

async function mockOperations(page: Page) {
  const unexpected: string[] = [];
  const state = { unavailable: false, recovered: false };
  await page.addInitScript(() => {
    localStorage.setItem("quaint_dash_page_features", JSON.stringify({ version: 2, pages: {
      operations: { "operations.retailSentiment": false, "operations.projectionReadiness": false,
        "operations.rankingReadiness": false },
    }, layouts: {} }));
  });
  // Every API request is intercepted, including unexpected/mutating ones. Never use the live DB.
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const payloads: Record<string, unknown> = {
      "/operations/health-summary": {
        observed_at: "2026-09-07T12:00:00Z", status: "critical",
        headline: "Data health needs immediate attention",
        summary: "Old queued work and provider failures need review.", incident_count: 2,
        informational_count: 0, affected_data_products: queue.affected_data_products,
        queue, workers: [], incidents: [], operations_url: "/operations#operations-health",
      },
      "/ingestion/jobs": [], "/ingestion/queue/status": queue,
      "/ingestion/retail-sentiment/status": { providers: [], latest_snapshots: [], recent_posts: [], pending_jobs: 0, running_jobs: 0, failed_jobs: 0 },
      "/ingestion/readiness": { items: [], total: 0, ready_count: 0 },
      "/ingestion/ranking-readiness": { universe: "tracked", items: [], total: 0, ready_count: 0 },
      "/market/freshness/status": disabled, "/data/readiness/status": disabled,
      "/ingestion/background/status": { ...disabled, worker_name: "ingestion_background",
        enabled: true, running: true, state: state.recovered ? "idle" : "failed",
        current_failures: state.recovered ? {} : { schedule: failure }, last_failure: failure,
        failure_count: 3, last_error: state.recovered ? null : failure.safe_message,
        schedule_interval_seconds: 3600, run_interval_seconds: 300, max_jobs_per_tick: 5,
        max_assets_per_schedule: 25, prices_only: false,
        last_schedule_at: null, last_schedule_count: null, last_run_at: null,
        last_completed_count: null },
    };
    if (route.request().method() !== "GET" || !(path in payloads)) {
      unexpected.push(`${route.request().method()} ${path}`);
      await route.abort();
      return;
    }
    const unavailable = state.unavailable && path === "/ingestion/queue/status";
    await route.fulfill({ status: unavailable ? 503 : 200, contentType: "application/json",
      body: JSON.stringify(unavailable ? { detail: "Queue diagnostics are unavailable." } : payloads[path]) });
  });
  return { state, unexpected };
}

test("full queue and phase-specific failure diagnostics fit desktop and mobile", async ({ page }, testInfo) => {
  const { unexpected } = await mockOperations(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/operations");
  const diagnostics = page.getByRole("region", { name: "Queue and worker status" });
  await expect(diagnostics.getByText("701 jobs", { exact: true })).toBeVisible();
  await expect(diagnostics.getByText("6 days", { exact: true })).toBeVisible();
  await expect(diagnostics.getByText("Routine ingestion: failed", { exact: true })).toBeVisible();
  await expect(diagnostics.getByText(/schedule: The scheduler could not execute/)).toBeVisible();
  await diagnostics.getByText("Dead-letter causes (1 group)", { exact: true }).click();
  await expect(diagnostics.getByText(/Provider request limit reached/)).toBeVisible();
  await expect(diagnostics.getByRole("button")).toHaveCount(0);
  expect(await diagnostics.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("operations-diagnostics.png"), fullPage: true });
  await diagnostics.screenshot({ path: testInfo.outputPath("diagnostic-panel.png") });
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
});

test("read-only refresh distinguishes recovered history and unavailable queue", async ({ page }) => {
  const { state, unexpected } = await mockOperations(page);
  await page.goto("/operations");
  const diagnostics = page.getByRole("region", { name: "Queue and worker status" });
  await expect(diagnostics.getByText("Routine ingestion: failed", { exact: true })).toBeVisible();
  state.recovered = true;
  state.unavailable = true;
  await page.getByRole("button", { name: "Refresh status", exact: true }).click();
  await expect(diagnostics.getByText(/Counts and backlog age are unknown/)).toBeVisible({ timeout: 15000 });
  await expect(diagnostics.getByText("Routine ingestion: idle", { exact: true })).toBeVisible();
  await expect(diagnostics.getByText(/Previous failure:/)).toBeVisible();
  await expect(diagnostics.getByText("701 jobs", { exact: true })).toHaveCount(0);
  await expect(diagnostics.getByText("0 jobs", { exact: true })).toHaveCount(0);
  expect(unexpected).toEqual([]);
});
