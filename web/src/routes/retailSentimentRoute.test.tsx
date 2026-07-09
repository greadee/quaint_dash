import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RetailSentimentPage } from "./retailSentimentRoute";

const apiMock = vi.hoisted(() => ({
  retailSentimentOverview: vi.fn(),
  stockRankings: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

function renderRetailSentiment() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RetailSentimentPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RetailSentimentPage", () => {
  it("renders holdings, social labels, and signal integration link", async () => {
    apiMock.retailSentimentOverview.mockResolvedValue({
      generated_at: "2026-07-08T12:00:00Z",
      methodology: "Retail sentiment is a social-attention layer.",
      summary: {
        holding_count: 1,
        holding_with_sentiment_count: 1,
        popular_count: 1,
        total_recent_posts: 12,
      },
      holdings: [{
        asset_id: "AMD",
        symbol: "AMD",
        name: "Advanced Micro Devices",
        is_held: true,
        is_watchlisted: false,
        market_value: 1200,
        portfolio_names: ["Core"],
        snapshot_date: "2026-07-08",
        retail_sentiment_score: 0.42,
        sentiment_label: "Strongly bullish",
        confidence: 0.75,
        reddit_post_count: 8,
        x_post_count: 4,
        bullish_count: 9,
        neutral_count: 1,
        bearish_count: 2,
        sentiment_momentum_1d: 0.08,
        unusual_volume_flag: true,
        source_count: 12,
        latest_posts: [{
          provider: "reddit",
          source_name: "r/stocks",
          title: "$AMD breakout thread",
          url: "https://reddit.test/amd",
          published_at: "2026-07-08T11:00:00Z",
          score: 24,
          comment_count: 6,
        }],
      }],
      popular: [],
    });
    apiMock.stockRankings.mockResolvedValue({
      factor: "aggregate",
      universe: "tracked",
      direction: "buy",
      timeframe: "monthly",
      as_of_date: "2026-07-08",
      include_retail_sentiment: false,
      methodology: "Retail sentiment is excluded.",
      total: 1,
      data_complete_count: 1,
      items: [{
        asset_id: "AMD",
        symbol: "AMD",
        name: "Advanced Micro Devices",
        exchange_code: "NASDAQ",
        currency: "USD",
        latest_price: 180,
        market_value: 1200,
        is_tracked: true,
        is_held: true,
        is_watchlisted: false,
        score: 18,
        score_strength: 18,
        action: "Buy",
        confidence: 0.8,
        data_status: "complete",
        latest_data_date: "2026-07-08",
        missing_inputs: [],
        components: [],
      }],
    });

    renderRetailSentiment();

    expect(await screen.findByRole("heading", { name: "Retail sentiment" })).toBeInTheDocument();
    expect((await screen.findAllByText("AMD")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Strongly bullish").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Signals with retail/i })).toHaveAttribute("href", "/signals?include_retail_sentiment=true");
    expect(await screen.findByText("Retail as an optional add-on")).toBeInTheDocument();
    expect(apiMock.stockRankings).toHaveBeenCalledWith(expect.objectContaining({ include_retail_sentiment: false }));
    expect(apiMock.retailSentimentOverview).toHaveBeenCalledWith(30);
  });
});
