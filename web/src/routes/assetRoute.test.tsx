import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AssetDetailPage } from "./assetRoute";

const apiMock = vi.hoisted(() => ({
  asset: vi.fn(),
  prices: vi.fn(),
  assetAnalytics: vi.fn(),
  assetActivity: vi.fn(),
  assetNews: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

vi.mock("recharts", () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    LineChart: passthrough,
    Line: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

function renderAsset(route = "/assets/NVDA") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/assets/:assetId" element={<AssetDetailPage notify={vi.fn()} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AssetDetailPage", () => {
  it("renders asset identity and stored price chart", async () => {
    apiMock.asset.mockResolvedValue({
      asset_id: "NVDA",
      symbol: "NVDA",
      name: "NVIDIA",
      sector: "Technology",
      latest_price: 120,
      currency: "USD",
    });
    apiMock.prices.mockResolvedValue([
      { date: "2026-06-18", close: 118 },
      { date: "2026-06-19", close: 120 },
    ]);
    apiMock.assetAnalytics.mockResolvedValue({});
    apiMock.assetActivity.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
    apiMock.assetNews.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0, sort: "recency", generated_at: "2026-06-30T14:40:00Z" });

    renderAsset();

    expect(await screen.findByRole("heading", { level: 1, name: /NVDA/i })).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NVDA price" })).toBeInTheDocument();
    expect(apiMock.prices).toHaveBeenCalledWith("NVDA", { range: "1Y" });
    expect(screen.getByRole("link", { name: /Compare/i })).toHaveAttribute("href", "/compare?symbols=NVDA");
  });

  it("marks stale price and incomplete valuation outputs as audit-only", async () => {
    apiMock.asset.mockResolvedValue({
      asset_id: "NVDA",
      symbol: "NVDA",
      name: "NVIDIA",
      sector: "Technology",
      latest_price: 120,
      currency: "USD",
      evidence: {
        evidence_type: "price", freshness_state: "stale", action_eligibility: "blocked",
      },
    });
    apiMock.prices.mockResolvedValue([]);
    apiMock.assetAnalytics.mockResolvedValue({
      price_evidence: { evidence_type: "price", freshness_state: "stale", action_eligibility: "blocked" },
      fundamental_evidence: { evidence_type: "financial_statement", freshness_state: "unknown", action_eligibility: "blocked" },
      report: {
        forecast: { blended_expected_cagr: 0.12, simulation: { expected_value: 175, expected_cagr: 0.08 } },
        discounted_cash_flow: { intrinsic_value_per_share: 140, margin_of_safety: 0.14, inputs_used: {} },
        dividend_discount: { intrinsic_value_per_share: null, inputs_used: {} },
        valuation_depth: {}, risk: {}, relative: {},
      },
      ai_context: { anomalies: [] },
    });
    apiMock.assetActivity.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
    apiMock.assetNews.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0, sort: "recency", generated_at: "2026-06-30T14:40:00Z" });

    renderAsset("/assets/NVDA?tab=fundamentals");

    expect(await screen.findByText(/Missing, stale, or non-production financial evidence blocks decision use/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Audit only/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Not decision eligible/i).length).toBeGreaterThan(0);
  });

  it("keeps news headlines and publication dates together", async () => {
    apiMock.asset.mockResolvedValue({
      asset_id: "NVDA",
      symbol: "NVDA",
      name: "NVIDIA Corporation with a deliberately descriptive company name",
      sector: "Technology",
      latest_price: 120,
      currency: "USD",
    });
    apiMock.assetNews.mockResolvedValue({
      items: [{
        article_id: 1,
        headline: "A long asset headline stays paired with its publication timestamp",
        summary: null,
        body_text: null,
        url: null,
        canonical_url: null,
        image_url: null,
        language: "en",
        published_at: "2026-06-30T14:40:00Z",
        ingested_at: "2026-06-30T14:41:00Z",
        source_name: "Local feed",
        provider: "local",
        provider_article_id: "news-1",
        is_press_release: false,
        is_breaking: false,
        categories: [],
        assets: [],
        user_state: { is_read: false, is_saved: false },
      }],
      total: 1,
      limit: 10,
      offset: 0,
      sort: "recency",
      generated_at: "2026-06-30T14:41:00Z",
    });

    renderAsset("/assets/NVDA?tab=news");

    expect(await screen.findByRole("heading", { name: "News" })).toBeInTheDocument();
    const copy = screen.getByText(/long asset headline/i).closest(".asset-news-copy");
    expect(copy?.querySelector("time")).toHaveAttribute("datetime", "2026-06-30T14:40:00Z");
  });
});
