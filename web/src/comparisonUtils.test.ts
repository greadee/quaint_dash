import { describe, expect, it } from "vitest";
import {
  assetMetricValue,
  calculateSeriesMetrics,
  defaultComparisonState,
  formatComparisonValue,
  metricRegistry,
  parseComparisonState,
  rankValues,
  serializeComparisonState,
} from "./comparisonUtils";

describe("comparison url state", () => {
  it("sanitizes duplicate symbols and invalid state", () => {
    const { state } = parseComparisonState(new URLSearchParams("symbols=nvda,AMD,nvda,bad%20symbol&period=BAD&mode=nope&currency=EUR&section=missing"));

    expect(state.symbols).toEqual(["NVDA", "AMD", "BADSYMBOL"]);
    expect(state.period).toBe(defaultComparisonState.period);
    expect(state.mode).toBe(defaultComparisonState.mode);
    expect(state.currency).toBe(defaultComparisonState.currency);
  });

  it("serializes only meaningful query parameters", () => {
    expect(serializeComparisonState({
      ...defaultComparisonState,
      symbols: ["NVDA", "AMD"],
      benchmark: "SP500",
      period: "1Y",
      reference: "AMD",
    })).toBe("symbols=NVDA%2CAMD&benchmark=SP500&reference=AMD");
  });
});

describe("comparison calculations and registry", () => {
  it("normalizes return metrics from aligned series", () => {
    const metrics = calculateSeriesMetrics({
      asset_id: "NVDA",
      symbol: "NVDA",
      mode: "total-return",
      currency: "USD",
      start_date: "2026-01-01",
      end_date: "2026-01-04",
      observation_count: 4,
      source: "test",
      warnings: [],
      points: [
        { date: "2026-01-01", value: 100, close: 10, cumulative_return: 0 },
        { date: "2026-01-02", value: 110, close: 11, cumulative_return: 0.1 },
        { date: "2026-01-03", value: 105, close: 10.5, cumulative_return: 0.05 },
        { date: "2026-01-04", value: 120, close: 12, cumulative_return: 0.2 },
      ],
    });

    expect(metrics.period_return).toBeCloseTo(0.2);
    expect(metrics.max_drawdown).toBeCloseTo(-0.04545, 4);
    expect(metrics.volatility).toBeGreaterThan(0);
  });

  it("keeps missing values as N/A and ranks by direction", () => {
    const pe = metricRegistry().find((item) => item.key === "pe_ratio");

    expect(pe?.direction).toBe("lower_is_better");
    expect(formatComparisonValue(null, pe!)).toBe("N/A");
    expect(rankValues([{ symbol: "A", value: 30 }, { symbol: "B", value: 20 }], pe!.direction)).toEqual({ A: 2, B: 1 });
  });

  it("maps provider-backed fundamentals into registered sections", () => {
    const registry = metricRegistry();
    const capitalMetric = registry.find((item) => item.key === "buyback_yield");
    const balanceMetric = registry.find((item) => item.key === "net_debt_to_ebitda");
    const reinvestmentMetric = registry.find((item) => item.key === "reinvestment_rate");
    const asset = {
      asset_id: "NVDA",
      symbol: "NVDA",
      name: "NVIDIA",
      asset_type: "stock",
      exchange_code: "XNAS",
      sector: "Technology",
      industry: "Semiconductors",
      country: "US",
      currency: "USD",
      latest_price: 20,
      market_cap: 2000,
      market_beta: 1.7,
      returns: { return_1d: null, return_5d: null, return_21d: null, return_252d: null },
      valuation: {
        historical_pe_average: null,
        historical_pe_discount: null,
        sector_pe_average: null,
        sector_pe_premium: null,
        industry_pe_average: null,
        industry_pe_premium: null,
      },
      fundamentals: {
        revenue: 1000,
        net_income: 200,
        eps: 2,
        forward_eps: 2.5,
        forward_revenue: 1200,
        pe_ratio: 10,
        forward_pe: 8,
        price_to_sales: 2,
        free_cash_flow: 250,
        free_cash_flow_yield: 0.125,
        gross_margin: 0.6,
        operating_margin: 0.3,
        net_margin: 0.2,
        cash: 150,
        total_debt: 50,
        net_debt: -100,
        net_debt_to_ebitda: -0.25,
        current_ratio: 3,
        debt_to_equity: 0.1,
        shares_outstanding: 95,
        dividend_yield: 0.025,
        buyback_yield: 0.02,
        stock_based_compensation: 25,
        acquisition_intensity: 0.08,
        reinvestment_rate: 0.3,
        roic: 0.5925,
        roic_on_reinvestment: 0.395,
        customer_concentration: 0.35,
        revenue_concentration: 0.45,
        latest_period_end: "2026-01-02",
        estimate_as_of: "2026-01-03T00:00:00Z",
      },
    };

    expect(capitalMetric?.section).toBe("capital-allocation");
    expect(balanceMetric?.section).toBe("balance-sheet");
    expect(reinvestmentMetric?.direction).toBe("target_range");
    expect(assetMetricValue(asset, "buyback_yield")).toBe(0.02);
    expect(assetMetricValue(asset, "net_debt_to_ebitda")).toBe(-0.25);
    expect(assetMetricValue(asset, "roic")).toBe(0.5925);
    expect(assetMetricValue(asset, "reinvestment_rate")).toBe(0.3);
    expect(assetMetricValue(asset, "customer_concentration")).toBe(0.35);
  });
});
