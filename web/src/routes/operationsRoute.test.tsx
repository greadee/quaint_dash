import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { IngestionQueueStatus, WorkerDiagnostics, WorkerFailure } from "../api";
import { OperationsDiagnostics, OperationsPage } from "./operationsRoute";

const apiMock = vi.hoisted(() => ({
  ingestionJobs: vi.fn(),
  ingestionQueueStatus: vi.fn(),
  ingestionBackgroundStatus: vi.fn(),
  marketFreshnessStatus: vi.fn(),
  dataReadinessStatus: vi.fn(),
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
    const failedJob = {
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
        error_message: "The job failed; details require local review.",
        created_at: "2026-06-18T12:00:00Z",
        updated_at: "2026-06-18T13:00:00Z",
    };
    apiMock.ingestionJobs.mockImplementation((requestedStatus: string) =>
      Promise.resolve(requestedStatus === "pending" ? [] : [failedJob]),
    );
    apiMock.ingestionQueueStatus.mockResolvedValue(emptyQueue);
    apiMock.marketFreshnessStatus.mockResolvedValue({
      ...disabledWorker, last_poll_at: null, last_subscription_count: null,
      last_refreshed_count: null, poll_interval_seconds: 900, lookback_days: 7,
      include_watchlist: false, max_symbols_per_tick: 25,
    });
    apiMock.dataReadinessStatus.mockResolvedValue({
      ...disabledWorker, last_check_at: null, last_target_count: null,
      last_ready_count: null, last_valuation_count: null, last_pending_count: null,
      last_missing: [], poll_interval_seconds: 900,
    });
    apiMock.ingestionBackgroundStatus.mockResolvedValue({
      ...disabledWorker,
      state: "idle",
      enabled: true,
      running: false,
      last_schedule_at: "2026-06-18T12:00:00Z",
      last_schedule_count: 3,
      last_run_at: "2026-06-18T12:05:00Z",
      last_completed_count: 2,
      last_pending_count: 4,
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
    expect(apiMock.ingestionQueueStatus).toHaveBeenCalled();
    expect(apiMock.ingestionJobs).not.toHaveBeenCalledWith("pending", "", 500);
    const routineHeading = await screen.findByText("Routine ingestion worker");
    expect(routineHeading).toBeInTheDocument();
    expect(screen.getAllByText("Current pending jobs")).toHaveLength(2);
    const routineCard = routineHeading.closest("section");
    expect(routineCard).not.toBeNull();
    expect(within(routineCard as HTMLElement).getByText("0 jobs")).toBeInTheDocument();
    expect(within(routineCard as HTMLElement).getByText("Pending after last cycle")).toBeInTheDocument();
    expect(within(routineCard as HTMLElement).getByText("4 jobs")).toBeInTheDocument();
    expect(await screen.findByText("Social sentiment ingestion")).toBeInTheDocument();
    expect(screen.getByText("Projection input readiness")).toBeInTheDocument();
    expect(screen.getByText("Ranking input readiness")).toBeInTheDocument();
    expect(screen.getAllByText("NVDA")).toHaveLength(2);
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("$AMD earnings thread")).toBeInTheDocument();
    expect(screen.getByText("The job failed; details require local review.")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});

const emptyQueue: IngestionQueueStatus = {
  observed_at: "2026-09-07T12:00:00Z", pending_count: 0, running_count: 0,
  dead_letter_count: 0, failed_count: 0, oldest_backlog_at: null,
  oldest_backlog_age_seconds: null, dead_letter_groups: [], failed_groups: [],
  affected_data_products: [],
};
const disabledWorker = {
  worker_name: "ingestion_background", state: "disabled", enabled: false, running: false,
  current_failures: {}, last_failure: null, failure_count: 0,
} satisfies WorkerDiagnostics & { enabled: boolean; running: boolean };
const schedulerFailure: WorkerFailure = {
  worker_name: "ingestion_background", phase: "schedule", category: "scheduler_query",
  safe_message: "The scheduler could not execute its database query.",
  guidance: "Repair the scheduler query before running another cycle.",
  occurred_at: "2026-09-07T11:00:00Z", count: 3,
};

describe("OperationsDiagnostics", () => {
  it("shows unknown counts after a failed refresh even when previous data exists", () => {
    render(<OperationsDiagnostics queue={{ ...emptyQueue, pending_count: 701 }}
      isLoading={false} error={new Error("private connection path")}
      workers={[{ label: "Routine ingestion", status: disabledWorker, error: new Error("private worker trace"), isLoading: false }]} />);
    expect(screen.getByText(/Queue status unavailable. Counts and backlog age are unknown/)).toBeInTheDocument();
    expect(screen.getByText("Routine ingestion: unavailable")).toBeInTheDocument();
    expect(screen.queryByText("701 jobs")).not.toBeInTheDocument();
    expect(screen.queryByText("0 jobs")).not.toBeInTheDocument();
    expect(screen.queryByText(/private/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Routine ingestion: disabled/)).not.toBeInTheDocument();
  });

  it("shows the full backlog, oldest age, failures and impacted products", () => {
    render(<OperationsDiagnostics queue={{ ...emptyQueue, pending_count: 701,
      oldest_backlog_at: "2026-09-01T12:00:00Z", oldest_backlog_age_seconds: 6 * 86400,
      dead_letter_count: 5, failed_count: 2,
      dead_letter_groups: [{ provider: "fmp", error_category: "provider_rate_limit", count: 5,
        safe_message: "Provider request limit reached.", guidance: "Check provider limits before choosing a bounded retry." }],
      failed_groups: [{ provider: "x", error_category: "provider_configuration", count: 2,
        safe_message: "Provider access or configuration needs attention.", guidance: "Check credentials before retrying." }],
      affected_data_products: ["Fundamentals and valuation inputs"],
    }} isLoading={false} error={null}
      workers={[{ label: "Routine ingestion", status: disabledWorker, error: null, isLoading: false }]} />);
    expect(screen.getByText("701 jobs")).toBeInTheDocument();
    expect(screen.getByText("6 days")).toBeInTheDocument();
    expect(screen.getByText(/Work is waiting and one or more automatic workers are disabled/)).toBeInTheDocument();
    expect(screen.getByText("Dead-letter causes (1 group)")).toBeInTheDocument();
    expect(screen.getByText("Legacy failure causes (1 group)")).toBeInTheDocument();
    expect(screen.getByText(/Affected data products: Fundamentals and valuation inputs/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("distinguishes current failures from a recovered worker's history", () => {
    const { rerender } = render(<OperationsDiagnostics queue={emptyQueue} isLoading={false} error={null}
      workers={[{ label: "Routine ingestion", error: null, isLoading: false,
        status: { ...disabledWorker, state: "failed", current_failures: { schedule: schedulerFailure }, last_failure: schedulerFailure, failure_count: 3 },
      }]} />);
    expect(screen.getByText("Routine ingestion: failed")).toBeInTheDocument();
    expect(screen.getByText(/schedule: The scheduler could not execute/)).toHaveTextContent("3 failures in this phase");
    expect(screen.queryByText(/Previous failure:/)).not.toBeInTheDocument();
    rerender(<OperationsDiagnostics queue={emptyQueue} isLoading={false} error={null}
      workers={[{ label: "Routine ingestion", error: null, isLoading: false,
        status: { ...disabledWorker, state: "idle", enabled: true, last_failure: schedulerFailure, failure_count: 3 },
      }]} />);
    expect(screen.getByText("Routine ingestion: idle")).toBeInTheDocument();
    expect(screen.getByText(/Previous failure:/)).toHaveTextContent("No current failure is recorded.");
    expect(screen.queryByText(/schedule: The scheduler could not execute/)).not.toBeInTheDocument();
  });

  it("keeps loading and unavailable distinct from an empty healthy queue", () => {
    const { rerender } = render(<OperationsDiagnostics isLoading error={null} workers={[]} />);
    expect(screen.queryByText("0 jobs")).not.toBeInTheDocument();
    expect(screen.queryByText("No active backlog")).not.toBeInTheDocument();
    rerender(<OperationsDiagnostics isLoading={false} error={null} workers={[]} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Counts and backlog age are unknown");
    rerender(<OperationsDiagnostics queue={emptyQueue} isLoading={false} error={null} workers={[]} />);
    expect(screen.getByText("No active backlog")).toBeInTheDocument();
    expect(screen.getAllByText("0 jobs")).toHaveLength(4);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
