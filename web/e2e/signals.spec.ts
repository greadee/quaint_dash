import { expect, test, type Page, type Route } from "@playwright/test";

const signal = {
  signal_id: "ranking.share_price_momentum.monthly.NVDA",
  definition_id: "ranking.share_price_momentum.monthly",
  asset_id: "NVDA",
  ticker: "NVDA",
  company_name: "NVIDIA",
  exchange: "NASDAQ",
  signal_name: "Price momentum threshold crossed",
  summary: "NVDA price trend improved enough to merit review with 86% input confidence.",
  category: "momentum",
  direction: "positive",
  status: "active",
  strength: 0.82,
  confidence: 0.86,
  portfolio_priority: 0.79,
  raw_observed_value: 22.4,
  normalized_value: 0.82,
  trigger_threshold: 6,
  lookback_period: "monthly",
  first_detected_at: "2026-06-18T12:00:00Z",
  confirmation_at: "2026-06-18T13:00:00Z",
  last_evaluated_at: "2026-06-19T12:00:00Z",
  data_as_of: "2026-06-19T00:00:00Z",
  expires_at: null,
  resolved_at: null,
  resolution_reason: null,
  methodology_version: "signals.rankings.v1",
  source: "stored local ranking inputs",
  missing_data_status: "complete",
  supporting_evidence: [
    {
      label: "Price trend",
      metric: "monthly return",
      value: 0.18,
      score: 22.4,
      detail: "Stored close prices show positive monthly momentum.",
      source: "asset_quote_daily",
      as_of: "2026-06-19",
    },
  ],
  contradicting_evidence: [
    {
      label: "Risk",
      metric: "volatility",
      value: 0.41,
      score: -7.2,
      detail: "Realized volatility is elevated.",
      source: "asset_quote_daily",
      as_of: "2026-06-19",
    },
  ],
  affected_portfolios: [
    {
      portfolio_id: 1,
      portfolio_name: "Core Growth",
      weight: 0.18,
      market_value: 42000,
      currency: "CAD",
      concentration_note: "High concentration: at least 15% of this portfolio.",
    },
  ],
  current_portfolio_weight: 0.18,
  historical_efficacy: {
    label: "Backtested from stored point-in-time snapshots",
    sample_size: 4,
    prior_occurrences: 4,
    median_forward_return: 0.05,
    median_excess_return: null,
    hit_rate: 0.75,
    max_adverse_excursion: -0.04,
    benchmark: null,
    methodology_version: "signals.rankings.v1",
    warning: null,
  },
  related_signal_ids: [],
  reviewed: false,
  muted: false,
};

const detail = {
  ...signal,
  lifecycle: [
    { status: "candidate", timestamp: "2026-06-18T12:00:00Z", label: "Candidate", detail: "Signal appeared in stored model inputs." },
    { status: "active", timestamp: "2026-06-18T13:00:00Z", label: "Active", detail: "Current lifecycle state after checks." },
  ],
  strength_history: [
    { date: "2026-06-16", strength: 0.52, confidence: 0.78, raw_value: 11.2, action: "Buy" },
    { date: "2026-06-19", strength: 0.82, confidence: 0.86, raw_value: 22.4, action: "Strong Buy" },
  ],
  related_news: [
    { title: "NVIDIA shipment update", provider: "local", published_at: "2026-06-19T10:00:00Z", url: "https://example.test/nvda", asset_id: "NVDA", symbol: "NVDA", sentiment: "positive" },
  ],
  methodology: "Signals use stored local market, sentiment, and portfolio inputs.",
  links: {},
  user_state: { reviewed_at: null, muted_until: null, dismissed_until: null, note: null, alert_rule_id: null },
};

async function mockSignals(page: Page) {
  const fulfillSignals = async (route: Route) => {
    const url = new URL(route.request().url());
    const noResults = url.searchParams.get("direction") === "negative";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: noResults ? [] : [signal],
        total: noResults ? 0 : 1,
        limit: 25,
        offset: 0,
        metrics: [
          { key: "active", label: "Active signals", value: 1, filter_params: { status: "active" } },
          { key: "incomplete", label: "Stale or incomplete", value: 1, filter_params: { completeness: "incomplete" } },
        ],
        needs_attention: [],
        top_opportunities: [signal],
        generated_at: "2026-06-19T12:00:00Z",
        data_as_of: "2026-06-19T00:00:00Z",
        last_successful_computation_at: "2026-06-19T12:00:00Z",
        partial_provider_failures: ["sentiment input coverage"],
        stale_cached_results: true,
        model_version: "signals.rankings.v1",
        methodology: "Signals use stored local market, sentiment, and portfolio inputs.",
      }),
    });
  };
  await page.route("**/api/v1/signals", fulfillSignals);
  await page.route("**/api/v1/signals?**", fulfillSignals);
  await page.route("**/api/v1/signals/ranking.share_price_momentum.monthly.NVDA", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(detail) });
  });
  await page.route("**/api/v1/signals/ranking.share_price_momentum.monthly.NVDA/user-state", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ reviewed_at: "2026-06-19T12:00:00Z", muted_until: null, dismissed_until: null, note: null, alert_rule_id: null }),
    });
  });
  await page.route("**/api/v1/signals/ranking.share_price_momentum.monthly.NVDA/alerts", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ alert_rule_id: 1, signal_id: signal.signal_id, definition_id: signal.definition_id, asset_id: signal.asset_id, condition: "status_active", threshold: null, channel: "in_app", is_active: true }),
    });
  });
  await page.route("**/api/v1/watchlist/assets/NVDA", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ asset_id: "NVDA", symbol: "NVDA", is_watchlisted: true }) });
  });
}

async function openVisibleEvidenceControl(page: Page) {
  const tableButton = page.getByRole("button", { name: "Evidence" }).first();
  if (await tableButton.isVisible()) {
    await tableButton.click();
    return;
  }

  await page.getByRole("button", { name: /Inspect evidence/i }).first().click();
}

async function hasVisibleText(page: Page, text: string) {
  return page.locator(`text=${text}`).evaluateAll((elements) =>
    elements.some((element) => {
      const htmlElement = element as HTMLElement;
      const rect = htmlElement.getBoundingClientRect();
      const style = window.getComputedStyle(htmlElement);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    }),
  );
}

test.describe("signals workspace", () => {
  test.beforeEach(async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    await mockSignals(page);
    await page.goto("/signals");
    await expect(page.getByRole("heading", { name: "Signals", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  for (const width of [360, 390, 768, 1024, 1440, 1920]) {
    test(`renders without horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.reload();
      await expect(page.getByRole("heading", { name: "Signals", exact: true })).toBeVisible();
      const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      expect(hasOverflow).toBe(false);
    });
  }

  test("filters, opens evidence, navigates to detail, and handles no results", async ({ page }) => {
    await openVisibleEvidenceControl(page);
    await expect.poll(() => hasVisibleText(page, "Supporting evidence")).toBe(true);
    await page.getByRole("button", { name: /Mark reviewed/i }).click();
    await expect(page.getByText("Signal marked reviewed.")).toBeVisible();
    await page.getByRole("link", { name: "Details" }).click();
    await expect(page).toHaveURL(/\/signals\/ranking\.share_price_momentum\.monthly\.NVDA/);
    await expect(page.getByText("Lifecycle", { exact: true })).toBeVisible();
    await page.goto("/signals?direction=negative&min_confidence=0.7&sort=priority");
    await expect(page.getByText("No signals match the selected filters.")).toBeVisible();
  });

  test("supports the primary flow from the keyboard", async ({ page }) => {
    const tableButton = page.getByRole("button", { name: "Evidence" }).first();
    if (await tableButton.isVisible()) {
      await tableButton.focus();
    } else {
      await page.getByRole("button", { name: /Inspect evidence/i }).first().focus();
    }
    await page.keyboard.press("Enter");
    await expect.poll(() => hasVisibleText(page, "Supporting evidence")).toBe(true);
  });
});
