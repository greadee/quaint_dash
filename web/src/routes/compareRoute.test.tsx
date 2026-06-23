import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ComparePage } from "./compareRoute";

const apiMock = vi.hoisted(() => ({
  assetBenchmarkAssociations: vi.fn(),
  comparisonWorkspace: vi.fn(),
  assets: vi.fn(),
  benchmarks: vi.fn(),
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
    CartesianGrid: passthrough,
    Legend: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

const comparisonAsset = (assetId: string, symbol: string) => ({
  asset_id: assetId,
  symbol,
  name: symbol === "NVDA" ? "NVIDIA" : "Advanced Micro Devices",
  sector: "Technology",
  industry: "Semiconductors",
  country: "US",
  currency: "USD",
  latest_price: symbol === "NVDA" ? 120 : 160,
  market_cap: symbol === "NVDA" ? 3_000_000_000_000 : 250_000_000_000,
  market_beta: 1.4,
  returns: { return_1d: 0.01, return_5d: 0.03, return_21d: 0.08, return_252d: 0.42 },
  fundamentals: { revenue: 100_000_000_000, net_income: 30_000_000_000, eps: 2.5, pe_ratio: 32, price_to_sales: 18 },
  valuation: {
    historical_pe_average: 28,
    historical_pe_discount: 0.12,
    sector_pe_average: 30,
    sector_pe_premium: 0.06,
    industry_pe_average: 31,
    industry_pe_premium: 0.03,
  },
});

function renderCompare(route = "/compare?symbols=NVDA,AMD&benchmark=SP500") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <ComparePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ComparePage", () => {
  it("renders actual comparison data from the workspace endpoint", async () => {
    apiMock.assets.mockResolvedValue([]);
    apiMock.benchmarks.mockResolvedValue([]);
    apiMock.assetBenchmarkAssociations.mockResolvedValue({ asset: { asset_id: "NVDA", symbol: "NVDA" }, associations: [] });
    apiMock.comparisonWorkspace.mockResolvedValue({
      requested_symbols: ["NVDA", "AMD"],
      assets: [comparisonAsset("NVDA", "NVDA"), comparisonAsset("AMD", "AMD")],
      failed_symbols: [],
      benchmark: { index_id: "SP500", name: "S&P 500", category: "core", currency: "USD", return_1d: 0.002, return_21d: 0.04, return_252d: 0.18, volatility_252d: 0.16 },
      historical_series: [
        {
          asset_id: "NVDA",
          symbol: "NVDA",
          mode: "total-return",
          currency: "USD",
          start_date: "2026-06-18",
          end_date: "2026-06-19",
          observation_count: 2,
          source: "test",
          warnings: [],
          points: [
            { date: "2026-06-18", value: 100, close: 118, cumulative_return: 0 },
            { date: "2026-06-19", value: 102, close: 120, cumulative_return: 0.02 },
          ],
        },
        {
          asset_id: "AMD",
          symbol: "AMD",
          mode: "total-return",
          currency: "USD",
          start_date: "2026-06-18",
          end_date: "2026-06-19",
          observation_count: 2,
          source: "test",
          warnings: [],
          points: [
            { date: "2026-06-18", value: 100, close: 150, cumulative_return: 0 },
            { date: "2026-06-19", value: 101, close: 152, cumulative_return: 0.01 },
          ],
        },
      ],
      freshness: {
        NVDA: { latest_price_date: "2026-06-19", latest_fiscal_period: "2026-03-31", provider: "local duckdb", stale: false, stale_reason: null },
        AMD: { latest_price_date: "2026-06-19", latest_fiscal_period: "2026-03-31", provider: "local duckdb", stale: false, stale_reason: null },
      },
      coverage: {
        requested_symbols: ["NVDA", "AMD"],
        resolved_symbols: ["NVDA", "AMD"],
        failed_symbols: [],
        common_start_date: "2026-06-18",
        start_date: "2026-06-18",
        end_date: "2026-06-19",
        benchmark: "SP500",
        currency: "native",
        mode: "total-return",
        calculation_version: "comparison.workspace.v1",
        warnings: [],
      },
      insights: ["Historical series use stored adjusted close where available."],
    });

    renderCompare();

    expect(await screen.findByRole("heading", { name: "Compare" })).toBeInTheDocument();
    expect(await screen.findByText("Actual price comparison")).toBeInTheDocument();
    expect(screen.getByText("Key performance and risk metrics")).toBeInTheDocument();
    expect(apiMock.comparisonWorkspace).toHaveBeenCalledWith(expect.objectContaining({ symbols: ["AMD", "NVDA"], benchmark: "SP500" }));
  });
});
