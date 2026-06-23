import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OverviewPage } from "./overviewRoute";

const apiMock = vi.hoisted(() => ({
  overviewUpdates: vi.fn(),
  portfolios: vi.fn(),
  brokerAccounts: vi.fn(),
  ingestionJobs: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

function renderOverview(moverDefault: "8" | "all" = "8") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OverviewPage moverDefault={moverDefault} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OverviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.overviewUpdates.mockResolvedValue({
      total_market_value: 100000,
      position_count: 9,
      mover_count: 9,
      news_count: 1,
      price_movers: Array.from({ length: 9 }, (_, index) => ({
        asset_id: `asset-${index}`,
        symbol: `T${index}`,
        name: `Test Holding ${index}`,
        change: index === 0 ? 1200 : 10,
        change_percent: index === 0 ? 0.03 : 0.001,
        market_value: 1000,
        weight: index === 0 ? 0.2 : 0.01,
      })),
      news: [{ title: "Local market note", symbol: "T0", provider: "local", published_at: "2026-06-19T12:00:00Z", url: null }],
    });
    apiMock.portfolios.mockResolvedValue([{ portfolio_id: 1, name: "Core", base_ccy: "CAD", position_count: 1 }]);
    apiMock.brokerAccounts.mockResolvedValue([{ provider_account_id: "acct-1", portfolio_id: 1 }]);
    apiMock.ingestionJobs.mockResolvedValue([{ job_id: 1, status: "failed" }]);
  });

  it("renders market snapshot and expands movers", async () => {
    const user = userEvent.setup();
    renderOverview();

    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(await screen.findByText("Total market value")).toBeInTheDocument();
    expect(screen.getByText("Attention items")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "See all" }));

    expect(screen.getByText("Test Holding 8")).toBeInTheDocument();
  });
});
