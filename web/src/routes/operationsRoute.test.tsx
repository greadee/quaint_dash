import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperationsPage } from "./operationsRoute";

const apiMock = vi.hoisted(() => ({
  ingestionJobs: vi.fn(),
  ingestionBackgroundStatus: vi.fn(),
  ingestionReadiness: vi.fn(),
  rankingReadiness: vi.fn(),
  retailSentimentStatus: vi.fn(),
  scheduleIngestion: vi.fn(),
  runIngestion: vi.fn(),
  retryFailedIngestion: vi.fn(),
  clearIngestionHistory: vi.fn(),
  startIngestionBackground: vi.fn(),
  stopIngestionBackground: vi.fn(),
  tickIngestionBackground: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

function renderOperations() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <OperationsPage />
    </QueryClientProvider>,
  );
}

describe("OperationsPage", () => {
  it("renders worker status, readiness gaps, and ingestion jobs", async () => {
    apiMock.ingestionJobs.mockResolvedValue([
      {
        job_id: 1,
        asset_id: "NVDA",
        domain: "market",
        job_type: "refresh",
        dataset: "prices",
        status: "failed",
        priority: 10,
        requested_start_date: "2026-06-01",
        requested_end_date: "2026-06-18",
        attempt_count: 2,
        error_message: "provider timeout",
        created_at: "2026-06-18T12:00:00Z",
        updated_at: "2026-06-18T13:00:00Z",
      },
    ]);
    apiMock.ingestionBackgroundStatus.mockResolvedValue({
      enabled: true,
      running: false,
      last_schedule_at: "2026-06-18T12:00:00Z",
      last_schedule_count: 3,
      last_run_at: "2026-06-18T12:05:00Z",
      last_completed_count: 2,
      last_error: null,
      schedule_interval_seconds: 3600,
      run_interval_seconds: 300,
      max_jobs_per_tick: 5,
      max_assets_per_schedule: 25,
      years: 10,
      prices_only: false,
    });
    apiMock.ingestionReadiness.mockResolvedValue({
      items: [
        {
          asset_id: "NVDA",
          symbol: "NVDA",
          asset_type: "equity",
          ready: false,
          missing: ["price history"],
          requirements: [
            {
              key: "prices",
              label: "Prices",
              ready: false,
              detail: "missing daily bars",
              row_count: 0,
              latest_date: null,
              open_jobs: 1,
              last_error: null,
            },
          ],
        },
      ],
      total: 1,
      ready_count: 0,
    });
    apiMock.rankingReadiness.mockResolvedValue({
      universe: "tracked",
      items: [
        {
          asset_id: "MSFT",
          symbol: "MSFT",
          name: "Microsoft",
          universe: "tracked",
          ready: false,
          complete_factor_count: 2,
          total_factor_count: 5,
          missing: ["news"],
          requirements: [
            {
              key: "news_sentiment",
              label: "News",
              ready: false,
              detail: "no recent sentiment",
              row_count: 0,
              latest_date: null,
              open_jobs: 0,
              last_error: null,
            },
          ],
        },
      ],
      total: 1,
      ready_count: 0,
    });
    apiMock.retailSentimentStatus.mockResolvedValue({
      providers: [
        {
          provider: "reddit",
          configured: true,
          post_count: 3,
          latest_post_at: "2026-06-18T11:00:00Z",
          open_jobs: 1,
          failed_jobs: 0,
          latest_error: null,
        },
        {
          provider: "x",
          configured: false,
          post_count: 0,
          latest_post_at: null,
          open_jobs: 0,
          failed_jobs: 1,
          latest_error: "X provider requires X_BEARER_TOKEN.",
        },
      ],
      latest_snapshots: [
        {
          asset_id: "AMD",
          ticker: "AMD",
          date: "2026-06-18",
          retail_sentiment_score: 0.42,
          reddit_post_count: 3,
          x_post_count: 0,
          bullish_count: 2,
          neutral_count: 1,
          bearish_count: 0,
          sentiment_momentum_1d: 0.12,
          unusual_volume_flag: false,
        },
      ],
      recent_posts: [
        {
          provider: "reddit",
          source_name: "r/stocks",
          ticker: "AMD",
          asset_id: "AMD",
          title: "$AMD earnings thread",
          body: "Bullish on AMD",
          url: "https://reddit.test/post",
          published_at: "2026-06-18T11:00:00Z",
          score: 42,
          comment_count: 7,
          like_count: null,
          repost_count: null,
          reply_count: null,
          relevance_score: 1,
        },
      ],
      pending_jobs: 1,
      running_jobs: 0,
      failed_jobs: 1,
    });

    renderOperations();

    expect(await screen.findByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect(apiMock.ingestionJobs).toHaveBeenCalledWith("", "", 25);
    expect(await screen.findByText("Routine ingestion worker")).toBeInTheDocument();
    expect(await screen.findByText("Social sentiment ingestion")).toBeInTheDocument();
    expect(screen.getByText("Projection input readiness")).toBeInTheDocument();
    expect(screen.getByText("Ranking input readiness")).toBeInTheDocument();
    expect(screen.getAllByText("NVDA")).toHaveLength(2);
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("$AMD earnings thread")).toBeInTheDocument();
    expect(screen.getByText("provider timeout")).toBeInTheDocument();
  });
});
