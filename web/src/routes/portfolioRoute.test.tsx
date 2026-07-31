import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PortfolioDetailPage, PortfolioWorkspacePage } from "./portfolioRoute";

const apiMock = vi.hoisted(() => ({
  portfolios: vi.fn(),
  aggregatePortfolio: vi.fn(),
  aggregatePositions: vi.fn(),
  portfolio: vi.fn(),
  positions: vi.fn(),
  holdingSignals: vi.fn(),
  portfolioPerformance: vi.fn(),
  portfolioRisk: vi.fn(),
  portfolioFundamentals: vi.fn(),
  portfolioNews: vi.fn(),
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
    PieChart: passthrough,
    Pie: passthrough,
    RadarChart: passthrough,
    Radar: passthrough,
    PolarGrid: passthrough,
    PolarAngleAxis: passthrough,
    PolarRadiusAxis: passthrough,
    Cell: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

function renderPortfolioWorkspace(route = "/portfolios") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <PortfolioWorkspacePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderPortfolioDetail(route = "/portfolios/1?tab=overview") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/portfolios/:portfolioId" element={<PortfolioDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PortfolioWorkspacePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.portfolioNews.mockResolvedValue({ items: [] });
  });

  it("renders aggregate portfolio state from API data", async () => {
    const user = userEvent.setup();
    apiMock.portfolios.mockResolvedValue([{ portfolio_id: 1, name: "Core Growth", base_ccy: "CAD" }]);
    apiMock.aggregatePortfolio.mockResolvedValue({
      portfolio_id: 0,
      name: "All portfolios",
      base_ccy: "CAD",
      display_currency: "CAD",
      market_value: 125000,
      book_cost: 100000,
      unrealized_gain: 25000,
      position_count: 2,
      source: "duckdb",
      as_of: "2026-06-19T15:00:00Z",
      fx_missing: [],
    });
    apiMock.aggregatePositions.mockResolvedValue([
      {
        asset_id: "NVDA",
        symbol: "NVDA",
        name: "NVIDIA",
        sector: "Technology",
        country: "US",
        industry: "Semiconductors",
        asset_type: "equity",
        allocation_class: "Stock",
        currency: "USD",
        book_cost: 60000,
        market_value: 75000,
        unrealized_gain: 15000,
        total_return_percent: 0.25,
        weight: 0.6,
        stale_price: false,
      },
      {
        asset_id: "RY.TO",
        symbol: "RY",
        name: "Royal Bank",
        sector: "Financials",
        country: "CA",
        industry: "Banks",
        asset_type: "equity",
        allocation_class: "Stock",
        currency: "CAD",
        book_cost: 40000,
        market_value: 50000,
        unrealized_gain: 10000,
        total_return_percent: 0.25,
        weight: 0.4,
        stale_price: true,
      },
    ]);

    renderPortfolioWorkspace();

    expect(await screen.findByRole("heading", { name: "Portfolios" })).toBeInTheDocument();
    expect(await screen.findByText("Asset class allocation")).toBeInTheDocument();
    expect(screen.getByText("Stock")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Cash" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pie" })).toBeInTheDocument();
    expect(screen.getByText("Stale prices")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Stock.*2 holdings/s }));

    expect(screen.getByRole("heading", { name: "Stock" })).toBeInTheDocument();
    expect(screen.getByText("Asset class holdings")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
    expect(screen.getByText("Royal Bank")).toBeInTheDocument();
    expect(screen.getAllByText("25.0% return").length).toBeGreaterThan(0);
  });

  it("renders exposure allocation controls on an individual portfolio overview", async () => {
    const user = userEvent.setup();
    apiMock.portfolio.mockResolvedValue({
      portfolio_id: 1,
      name: "Core Growth",
      base_ccy: "CAD",
      market_value: 125000,
      book_cost: 100000,
      unrealized_gain: 25000,
      position_count: 2,
    });
    apiMock.positions.mockResolvedValue([
      {
        asset_id: "NVDA",
        symbol: "NVDA",
        name: "NVIDIA",
        sector: "Technology",
        country: "US",
        industry: "Semiconductors",
        asset_type: "equity",
        allocation_class: "Stock",
        currency: "USD",
        book_cost: 60000,
        market_value: 75000,
        unrealized_gain: 15000,
        total_return_percent: 0.25,
        weight: 0.6,
        stale_price: false,
      },
      {
        asset_id: "CASH.TO",
        symbol: "CASH.TO",
        name: "Global X High Interest Savings ETF",
        sector: null,
        country: "CA",
        industry: null,
        asset_type: "etf",
        allocation_class: "Money market",
        currency: "CAD",
        book_cost: 49000,
        market_value: 50000,
        unrealized_gain: 1000,
        total_return_percent: 0.0204,
        weight: 0.4,
        stale_price: false,
      },
      {
        asset_id: "VTI",
        symbol: "VTI",
        name: "Vanguard Total Stock Market ETF",
        sector: "Broad market",
        country: "US",
        industry: null,
        asset_type: "etf",
        allocation_class: "ETF",
        currency: "USD",
        book_cost: 90000,
        market_value: 100000,
        unrealized_gain: 10000,
        total_return_percent: 0.1111,
        weight: 0.5,
        stale_price: false,
        country_exposure: { US: 0.55, CA: 0.45 },
      },
    ]);
    apiMock.portfolioPerformance.mockResolvedValue({
      portfolio_id: 1,
      range: "3Y",
      benchmark: "SP500",
      points: [],
      observation_count: 0,
      actual_twr_cagr: null,
      benchmark_cagr: null,
      excess_cagr: null,
      coverage: 0,
      missing_inputs: [],
    });
    apiMock.portfolioRisk.mockResolvedValue({
      portfolio_id: 1,
      risk_free_rate: 0,
      annualized_return: null,
      annualized_volatility: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      beta: null,
      alpha: null,
      correlation: null,
      maximum_drawdown: null,
      downside_deviation: null,
      observation_count: 0,
      effective_number_of_holdings: 2,
      hhi: 0.5,
      weight_balance_score: 0.8,
      asset_class_concentration: {},
      sector_concentration: {},
      geographic_concentration: {},
      currency_concentration: {},
      missing_inputs: [],
    });
    apiMock.portfolioFundamentals.mockResolvedValue({
      portfolio_id: 1,
      base_currency: "CAD",
      horizon_years: 5,
      weighted_expected_cagr: { value: null, coverage: 0 },
      pe_ratio: { value: null, coverage: 0 },
      price_to_free_cash_flow: { value: null, coverage: 0 },
      dividend_yield: { value: null, coverage: 0 },
      margin_of_safety: { value: null, coverage: 0 },
      holdings: [],
      missing_inputs: [],
    });

    renderPortfolioDetail();

    expect(await screen.findByRole("heading", { name: "Core Growth" })).toBeInTheDocument();
    expect(await screen.findByText("Asset class allocation")).toBeInTheDocument();
    expect(screen.getByText("Stock")).toBeInTheDocument();
    expect(screen.getByText("Money market")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Cash" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Money market.*1 holdings/s }));

    expect(screen.getByRole("heading", { name: "Money market" })).toBeInTheDocument();
    expect(screen.getAllByText("Global X High Interest Savings ETF").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: "Country" }));
    await user.click(screen.getByRole("button", { name: /US.*2 holdings/s }));

    expect(screen.getByRole("heading", { name: "US" })).toBeInTheDocument();
    expect(screen.getAllByText("Vanguard Total Stock Market ETF").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Pie" }));

    expect(screen.getByLabelText("Allocation pie chart")).toBeInTheDocument();
  });

  it("starts snapshot-backed overview analytics without waiting for performance", async () => {
    apiMock.portfolio.mockResolvedValue({
      portfolio_id: 1,
      name: "Core Growth",
      base_ccy: "CAD",
      market_value: 75000,
      book_cost: 60000,
      unrealized_gain: 15000,
      position_count: 0,
    });
    apiMock.positions.mockResolvedValue([]);
    apiMock.portfolioPerformance.mockReturnValue(new Promise(() => undefined));
    apiMock.portfolioRisk.mockResolvedValue({
      portfolio_id: 1,
      risk_free_rate: 0,
      observation_count: 0,
      missing_inputs: [],
    });
    apiMock.portfolioFundamentals.mockResolvedValue({
      portfolio_id: 1,
      base_currency: "CAD",
      horizon_years: 5,
      weighted_expected_cagr: { value: null, coverage: 0 },
      pe_ratio: { value: null, coverage: 0 },
      price_to_free_cash_flow: { value: null, coverage: 0 },
      dividend_yield: { value: null, coverage: 0 },
      margin_of_safety: { value: null, coverage: 0 },
      holdings: [],
      missing_inputs: [],
    });

    renderPortfolioDetail();

    expect(await screen.findByRole("heading", { name: "Core Growth" })).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMock.portfolioPerformance).toHaveBeenCalledTimes(1);
      expect(apiMock.portfolioRisk).toHaveBeenCalledTimes(1);
      expect(apiMock.portfolioFundamentals).toHaveBeenCalledTimes(1);
    });
  });

  it("renders holding Kiviat factor diagrams from backend holding signals", async () => {
    apiMock.portfolio.mockResolvedValue({
      portfolio_id: 1,
      name: "Core Growth",
      base_ccy: "CAD",
      market_value: 75000,
      book_cost: 60000,
      unrealized_gain: 15000,
      position_count: 1,
    });
    apiMock.positions.mockResolvedValue([
      {
        asset_id: "NVDA",
        symbol: "NVDA",
        name: "NVIDIA",
        sector: "Technology",
        country: "US",
        industry: "Semiconductors",
        asset_type: "stock",
        allocation_class: "Stock",
        currency: "USD",
        quantity: 10,
        book_cost: 60000,
        latest_price: 750,
        market_value: 75000,
        unrealized_gain: 15000,
        total_return_percent: 0.25,
        weight: 1,
        broker_linked: false,
        broker_account_count: 0,
        stale_price: false,
      },
    ]);
    apiMock.holdingSignals.mockResolvedValue({
      timeframe: "1m",
      methodology: "Kiviat grades use stored factor inputs.",
      items: [{
        asset_id: "NVDA",
        symbol: "NVDA",
        name: "NVIDIA",
        currency: "USD",
        market_value: 75000,
        weight: 1,
        latest_price: 750,
        timeframe: "1m",
        return_value: 0.12,
        signal_score: 42,
        signal_strength: 42,
        grade: "B",
        action: "Buy",
        confidence: 0.8,
        data_points: 70,
        components: [
          { name: "Value", metric: "valuation discount", value: -0.2, contribution: 42, score: 42, grade: "B", available: true, detail: "Stored valuation inputs." },
          { name: "Growth", metric: "revenue/EPS/FCF growth", value: 0.18, contribution: 72, score: 72, grade: "A", available: true, detail: "Stored growth inputs." },
          { name: "Quality", metric: "ROIC and reinvestment", value: 0.22, contribution: 55, score: 55, grade: "B", available: true, detail: "Stored quality inputs." },
          { name: "Profitability", metric: "margins and cash flow", value: 0.3, contribution: 61, score: 61, grade: "B", available: true, detail: "Stored profitability inputs." },
          { name: "Financial strength", metric: "balance sheet", value: 0.1, contribution: 48, score: 48, grade: "B", available: true, detail: "Stored balance sheet inputs." },
          { name: "Momentum", metric: "monthly price trend", value: 0.12, contribution: 72, score: 72, grade: "A", available: true, detail: "Stored price momentum." },
          { name: "Sentiment", metric: "news and retail tone", value: -0.2, contribution: -22, score: -22, grade: "D", available: true, detail: "Stored sentiment inputs." },
          { name: "Ownership", metric: "institutional and buyback support", value: null, contribution: null, score: null, grade: null, available: false, detail: "Needs ownership inputs." },
        ],
      }],
    });
    apiMock.portfolioPerformance.mockResolvedValue({
      portfolio_id: 1,
      range: "1Y",
      benchmark: null,
      points: [],
      observation_count: 0,
      actual_twr_cagr: null,
      benchmark_cagr: null,
      excess_cagr: null,
      coverage: 0,
      missing_inputs: [],
    });
    apiMock.portfolioRisk.mockResolvedValue({
      portfolio_id: 1,
      risk_free_rate: 0,
      annualized_return: null,
      annualized_volatility: null,
      sharpe_ratio: null,
      sortino_ratio: null,
      beta: null,
      alpha: null,
      correlation: null,
      maximum_drawdown: null,
      downside_deviation: null,
      observation_count: 0,
      effective_number_of_holdings: 1,
      hhi: 1,
      weight_balance_score: 1,
      asset_class_concentration: {},
      sector_concentration: {},
      geographic_concentration: {},
      currency_concentration: {},
      missing_inputs: [],
    });
    apiMock.portfolioFundamentals.mockResolvedValue({
      portfolio_id: 1,
      base_currency: "CAD",
      horizon_years: 5,
      weighted_expected_cagr: { value: null, coverage: 0 },
      pe_ratio: { value: null, coverage: 0 },
      price_to_free_cash_flow: { value: null, coverage: 0 },
      dividend_yield: { value: null, coverage: 0 },
      margin_of_safety: { value: null, coverage: 0 },
      holdings: [],
      missing_inputs: [],
    });

    renderPortfolioDetail("/portfolios/1?tab=holdings");

    expect(await screen.findByText("Holding grades")).toBeInTheDocument();
    expect(screen.getByLabelText("NVDA factor Kiviat diagram")).toBeInTheDocument();
    expect(screen.getByText("Strengths")).toBeInTheDocument();
    expect(screen.getByText("Growth: A")).toBeInTheDocument();
    expect(screen.getByText("Weaknesses")).toBeInTheDocument();
    expect(screen.getByText("Sentiment: D")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(screen.getByText("Ownership: Incomplete")).toBeInTheDocument();
    expect(apiMock.holdingSignals).toHaveBeenCalledWith("1m", 1);
  });
});
