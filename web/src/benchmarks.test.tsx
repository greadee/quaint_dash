import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { BenchmarkDetailPage, BenchmarksWorkspacePage } from "./benchmarks";
import type {
  ActionResult,
  BenchmarkConstituent,
  BenchmarkExposure,
  BenchmarkIndexDetail,
  BenchmarkIndexSummary,
  BenchmarkPricePoint,
} from "./api";

const apiMock = vi.hoisted(() => ({
  benchmarks: vi.fn(),
  benchmark: vi.fn(),
  benchmarkPrices: vi.fn(),
  benchmarkMetrics: vi.fn(),
  benchmarkConstituents: vi.fn(),
  benchmarkExposures: vi.fn(),
  seedBenchmarks: vi.fn(),
  refreshBenchmark: vi.fn(),
  hardenBenchmarks: vi.fn(),
}));

vi.mock("./api", () => ({ api: apiMock }));

vi.mock("recharts", () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    LineChart: passthrough,
    Line: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    CartesianGrid: passthrough,
    Legend: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

const summaries: BenchmarkIndexSummary[] = [
  {
    index_id: "DEV_INTL",
    index_name: "Developed International Equity",
    index_family: "MSCI/FTSE",
    index_category: "core_geo",
    region: "Developed ex-North America",
    country_code: null,
    currency: "USD",
    is_core: true,
    is_active: true,
    notes: "Broad developed market benchmark",
    latest_metric_date: "2026-06-18",
    latest_close: 101,
    return_1d: 0.01,
    return_21d: 0.03,
    return_252d: 0.12,
    volatility_252d_ann: 0.16,
    latest_composition_date: "2026-06-18",
    constituent_count: 1500,
    composition_quality: "exact",
    daily_price_last_success_at: "2026-06-18T20:00:00",
    composition_last_success_at: "2026-06-18T21:00:00",
    last_error: null,
  },
  {
    index_id: "IND_SEMICONDUCTORS",
    index_name: "Semiconductors Industry",
    index_family: "iShares",
    index_category: "industry",
    region: "Global",
    country_code: null,
    currency: "USD",
    is_core: false,
    is_active: true,
    notes: "ETF proxy for semiconductor industry benchmark",
    latest_metric_date: "2026-06-18",
    latest_close: 250,
    return_1d: -0.01,
    return_21d: 0.06,
    return_252d: 0.32,
    volatility_252d_ann: 0.28,
    latest_composition_date: "2026-06-18",
    constituent_count: 30,
    composition_quality: "proxy",
    daily_price_last_success_at: "2026-06-18T20:00:00",
    composition_last_success_at: "2026-06-18T21:00:00",
    last_error: null,
  },
];

const prices: Record<string, BenchmarkPricePoint[]> = {
  DEV_INTL: [
    price("DEV_INTL", "2026-06-17", 100),
    price("DEV_INTL", "2026-06-18", 101),
  ],
  IND_SEMICONDUCTORS: [
    price("IND_SEMICONDUCTORS", "2026-06-17", 200, true),
    price("IND_SEMICONDUCTORS", "2026-06-18", 250, true),
  ],
};

function price(indexId: string, date: string, close: number, isProxy = false): BenchmarkPricePoint {
  return {
    date,
    open: close,
    high: close,
    low: close,
    close,
    adj_close: close,
    volume: null,
    source: "test",
    source_symbol: indexId,
    is_proxy: isProxy,
  };
}

const detail: BenchmarkIndexDetail = {
  ...summaries[1],
  symbols: [
    { provider: "yfinance", provider_symbol: "SMH", symbol_purpose: "price_daily", is_primary: true, is_proxy: true },
  ],
  sync_state: {
    daily_price: {
      job_type: "daily_price",
      last_success_at: "2026-06-18T20:00:00",
      last_attempt_at: "2026-06-18T20:00:00",
      last_success_date: "2026-06-18",
      last_error: null,
      updated_at: "2026-06-18T20:00:00",
    },
  },
  available_snapshot_dates: ["2026-06-18"],
  available_price_range: { first_price_date: "2026-06-17", last_price_date: "2026-06-18" },
  available_metric_range: { first_metric_date: "2026-06-18", last_metric_date: "2026-06-18" },
};

const exposures: BenchmarkExposure[] = [
  {
    index_id: "IND_SEMICONDUCTORS",
    snapshot_date: "2026-06-18",
    dimension_type: "sector",
    dimension_value: "Technology",
    weight_pct: 100,
    source: "test",
    source_type: "etf_proxy",
    is_proxy: true,
  },
];

const constituents: BenchmarkConstituent[] = [
  {
    index_id: "IND_SEMICONDUCTORS",
    snapshot_date: "2026-06-18",
    source: "test",
    constituent_symbol: "NVDA",
    constituent_name: "NVIDIA",
    exchange_code: "XNAS",
    country_code: "US",
    currency: "USD",
    sector: "Technology",
    industry: "Semiconductors",
    weight_pct: 10,
    market_cap: 3000000000000,
    is_proxy: true,
  },
];

function renderWithProviders(route: string, element: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/benchmarks" element={element} />
          <Route path="/benchmarks/:benchmarkId" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BenchmarksWorkspacePage", () => {
  beforeEach(() => {
    apiMock.benchmarks.mockResolvedValue(summaries);
    apiMock.benchmarkPrices.mockImplementation((id: string) => Promise.resolve(prices[id] ?? []));
    apiMock.seedBenchmarks.mockResolvedValue({ status: "ok", result: {} } satisfies ActionResult);
    apiMock.hardenBenchmarks.mockResolvedValue({ status: "ok", result: {} } satisfies ActionResult);
  });

  it("renders the workspace, summary, actual chart copy, and explorer rows", async () => {
    renderWithProviders("/benchmarks", <BenchmarksWorkspacePage notify={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Benchmarks" })).toBeInTheDocument();
    expect(screen.getByText("Benchmark price comparison")).toBeInTheDocument();
    expect(screen.getByText(/Stored closes/)).toBeInTheDocument();
    expect(await screen.findAllByText("Developed International Equity")).not.toHaveLength(0);
    expect(screen.getAllByText("Semiconductors Industry")).not.toHaveLength(0);
    expect(screen.getAllByText(/Proxy \/ ETF proxy/)).not.toHaveLength(0);
  });

  it("updates query-driven filters and can add a benchmark to comparison", async () => {
    const user = userEvent.setup();
    renderWithProviders("/benchmarks?selected=DEV_INTL", <BenchmarksWorkspacePage notify={vi.fn()} />);

    await screen.findByRole("heading", { name: "Benchmarks" });
    await user.selectOptions(screen.getByLabelText(/Proxy/i), "proxy");
    await user.selectOptions(screen.getByLabelText(/Freshness/i), "proxy");
    await user.click(screen.getAllByRole("button", { name: "Add" })[0]);

    expect(screen.getByRole("button", { name: /IND_SEMICONDUCTORS/i })).toBeInTheDocument();
    await waitFor(() => expect(apiMock.benchmarkPrices).toHaveBeenCalled());
  });
});

describe("BenchmarkDetailPage", () => {
  beforeEach(() => {
    apiMock.benchmark.mockResolvedValue(detail);
    apiMock.benchmarkPrices.mockResolvedValue(prices.IND_SEMICONDUCTORS);
    apiMock.benchmarkMetrics.mockResolvedValue([
      {
        metric_date: "2026-06-18",
        return_1d: 0.01,
        return_5d: 0.02,
        return_21d: 0.06,
        return_63d: 0.1,
        return_126d: 0.2,
        return_252d: 0.32,
        return_ytd: 0.22,
        volatility_21d_ann: 0.24,
        volatility_63d_ann: 0.26,
        volatility_252d_ann: 0.28,
        sma_50: 220,
        sma_200: 190,
        high_52w: 260,
        low_52w: 140,
        drawdown_from_52w_high: -0.04,
      },
    ]);
    apiMock.benchmarkExposures.mockResolvedValue(exposures);
    apiMock.benchmarkConstituents.mockResolvedValue({ items: constituents, total: 1, limit: 25, offset: 0 });
    apiMock.refreshBenchmark.mockResolvedValue({ status: "ok", result: {} } satisfies ActionResult);
  });

  it("renders identity, risk, proxy disclosure, exposures, and constituents", async () => {
    renderWithProviders("/benchmarks/IND_SEMICONDUCTORS", <BenchmarkDetailPage notify={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: /Semiconductors Industry/ })).toBeInTheDocument();
    expect(screen.getByText("SMH")).toBeInTheDocument();
    expect(screen.getByText(/ETF proxy data/)).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("Computed metrics")).toBeInTheDocument();
  });

  it("runs a section-level refresh action", async () => {
    const notify = vi.fn();
    const user = userEvent.setup();
    renderWithProviders("/benchmarks/IND_SEMICONDUCTORS", <BenchmarkDetailPage notify={notify} />);

    await screen.findByRole("heading", { name: /Semiconductors Industry/ });
    const actions = screen.getByRole("heading", { name: "Data actions" }).closest("section");
    expect(actions).not.toBeNull();
    await user.click(within(actions as HTMLElement).getByRole("button", { name: /Prices/i }));

    await waitFor(() => expect(apiMock.refreshBenchmark).toHaveBeenCalledWith("IND_SEMICONDUCTORS", { job_type: "daily_price" }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith("IND_SEMICONDUCTORS refresh finished."));
  });
});
