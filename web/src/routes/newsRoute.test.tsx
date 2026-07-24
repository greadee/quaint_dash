import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NewsTerminalPage } from "./newsRoute";

const apiMock = vi.hoisted(() => ({
  news: vi.fn(),
  newsProviders: vi.fn(),
  newsCategories: vi.fn(),
  markNewsRead: vi.fn(),
  saveNewsArticle: vi.fn(),
  unsaveNewsArticle: vi.fn(),
  refreshNews: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

const newsItem = {
  article_id: 1,
  provider_code: "fmp_news",
  provider_name: "Financial Modeling Prep News",
  provider_article_id: "fmp-nvda-1",
  headline: "NVIDIA raises guidance after data center revenue beats expectations",
  summary: "NVIDIA reported stronger data center revenue and raised guidance.",
  canonical_url: "https://example.test/nvda",
  source_name: "Reuters via FMP",
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

function renderNews(route = "/news") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <NewsTerminalPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NewsTerminalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.news.mockResolvedValue({ items: [newsItem], total: 1, limit: 25, offset: 0, sort: "recency", generated_at: "2026-06-30T14:40:00Z", last_successful_sync_at: "2026-06-30T14:40:00Z", provider_status: "healthy", provider_message: null, is_cached: true });
    apiMock.newsProviders.mockResolvedValue([{ provider_code: "fmp_news", provider_name: "Financial Modeling Prep News", provider_type: "api", is_enabled: true, supports_latest_news: true, supports_symbol_news: true, supports_full_text: false, supports_sentiment: false, supports_categories: true, last_attempted_at: "2026-06-30T14:40:00Z", last_succeeded_at: "2026-06-30T14:40:00Z", last_error_at: null, last_error_message: null, sync_status: "success" }]);
    apiMock.newsCategories.mockResolvedValue([{ category_code: "earnings", category_name: "Earnings", default_importance_weight: 0.75, article_count: 1 }]);
    apiMock.markNewsRead.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: false, saved_at: null });
    apiMock.saveNewsArticle.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: true, saved_at: "2026-06-30T14:41:00Z" });
    apiMock.unsaveNewsArticle.mockResolvedValue({ article_id: 1, user_id: "local", is_read: true, read_at: "2026-06-30T14:41:00Z", is_saved: false, saved_at: null });
    apiMock.refreshNews.mockResolvedValue({ status: "success", generated_at: "2026-06-30T14:41:00Z", results: [] });
  });

  it("renders feed filters, story detail, and save action", async () => {
    const user = userEvent.setup();
    renderNews();

    expect(await screen.findByRole("heading", { name: "News Terminal" })).toBeInTheDocument();
    expect((await screen.findAllByText(/NVIDIA raises guidance/)).length).toBeGreaterThan(0);
    expect(screen.getByText("Affected assets")).toBeInTheDocument();
    expect(screen.getAllByText("NVDA").length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: "Save story" })[0]);

    expect(apiMock.saveNewsArticle).toHaveBeenCalledWith(1);
  });

  it("passes search and sort filters to the API", async () => {
    const user = userEvent.setup();
    renderNews("/news?sort=relevance");

    await screen.findByRole("heading", { name: "News Terminal" });
    await user.type(screen.getByPlaceholderText("Search headlines, tickers, companies"), "NVDA");

    expect(apiMock.news).toHaveBeenLastCalledWith(expect.objectContaining({ q: "NVDA", sort: "relevance" }));
  });

  it("requests a backend news refresh from the toolbar", async () => {
    const user = userEvent.setup();
    renderNews();

    await screen.findByRole("heading", { name: "News Terminal" });
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(apiMock.refreshNews).toHaveBeenCalled();
  });
});
