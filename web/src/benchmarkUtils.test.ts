import { describe, expect, it } from "vitest";
import type { BenchmarkIndexSummary, BenchmarkPricePoint } from "./api";
import {
  baselineDelta,
  benchmarkCategoryLabel,
  benchmarkFreshness,
  formatCompact,
  formatDate,
  formatDateTime,
  formatLevel,
  formatMissing,
  formatPercent,
  freshnessLabel,
  isProxyBenchmark,
  mergeNormalizedSeries,
  normalizeSeries,
  parseSelected,
  periodStartDate,
  proxyLabel,
  sortBenchmarks,
} from "./benchmarkUtils";

const benchmark = (overrides: Partial<BenchmarkIndexSummary> = {}): BenchmarkIndexSummary => ({
  index_id: "SP500",
  index_name: "S&P 500",
  index_family: "S&P",
  index_category: "core_geo",
  region: "North America",
  country_code: "US",
  currency: "USD",
  is_core: true,
  is_active: true,
  notes: "Large cap US",
  latest_metric_date: "2026-06-18",
  latest_close: 5200,
  return_1d: 0.01,
  return_21d: 0.04,
  return_252d: 0.15,
  volatility_252d_ann: 0.18,
  latest_composition_date: "2026-06-18",
  constituent_count: 500,
  composition_quality: "exact",
  daily_price_last_success_at: "2026-06-18T21:00:00",
  composition_last_success_at: "2026-06-18T21:30:00",
  last_error: null,
  ...overrides,
});

const price = (date: string, close: number, overrides: Partial<BenchmarkPricePoint> = {}): BenchmarkPricePoint => ({
  date,
  open: close,
  high: close,
  low: close,
  close,
  adj_close: close,
  volume: null,
  source: "test",
  source_symbol: "SPY",
  is_proxy: false,
  ...overrides,
});

describe("benchmark formatting", () => {
  it("formats missing, percent, level, compact numbers, and dates without fabricating values", () => {
    expect(formatMissing(null)).toBe("-");
    expect(formatMissing(" USD ")).toBe("USD");
    expect(formatPercent(null)).toBe("-");
    expect(formatPercent(0.1534)).toBe("+15.34%");
    expect(formatPercent(-0.008)).toBe("-0.80%");
    expect(formatLevel(null)).toBe("-");
    expect(formatLevel(1234.567)).toBe("1,234.57");
    expect(formatCompact(null)).toBe("-");
    expect(formatCompact(1234567)).toContain("1.23");
    expect(formatDate(null)).toBe("-");
    expect(formatDate("not-a-date")).toBe("not-a-date");
    expect(formatDateTime(null)).toBe("-");
  });

  it("labels categories, freshness, and proxy status", () => {
    expect(benchmarkCategoryLabel("core_geo")).toBe("Core market");
    expect(benchmarkCategoryLabel("custom_type")).toBe("custom type");
    expect(freshnessLabel("partial")).toBe("Partial");

    const proxy = benchmark({ composition_quality: "proxy" });
    expect(isProxyBenchmark(proxy)).toBe(true);
    expect(proxyLabel(proxy)).toBe("ETF proxy");
    expect(proxyLabel(benchmark())).toBe("Direct index");
  });
});

describe("benchmark freshness", () => {
  const now = new Date("2026-06-19T12:00:00");

  it("classifies error, proxy, unavailable, partial, stale, and fresh states", () => {
    expect(benchmarkFreshness(benchmark({ last_error: "provider failed" }), now)).toBe("error");
    expect(benchmarkFreshness(benchmark({ composition_quality: "proxy" }), now)).toBe("proxy");
    expect(benchmarkFreshness(benchmark({ latest_close: null }), now)).toBe("unavailable");
    expect(benchmarkFreshness(benchmark({ latest_composition_date: null }), now)).toBe("partial");
    expect(benchmarkFreshness(benchmark({ latest_metric_date: "2026-05-01" }), now)).toBe("stale");
    expect(benchmarkFreshness(benchmark({ latest_metric_date: "2026-06-18" }), now)).toBe("fresh");
  });
});

describe("benchmark URL and period helpers", () => {
  it("parses selected ids and removes duplicates", () => {
    expect(parseSelected("sp500, nasdaq100, SP500")).toEqual(["SP500", "NASDAQ100"]);
    expect(parseSelected(null, ["SP500", "TSX"])).toEqual(["SP500", "TSX"]);
    expect(parseSelected("a,b,c,d,e,f")).toHaveLength(5);
  });

  it("builds period start dates", () => {
    const now = new Date("2026-06-19T12:00:00");
    expect(periodStartDate("MAX", now)).toBeUndefined();
    expect(periodStartDate("YTD", now)).toBe("2026-01-01");
    expect(periodStartDate("5D", now)).toBe("2026-06-11");
  });
});

describe("benchmark sorting and normalization", () => {
  it("sorts deterministically and keeps missing values last", () => {
    const rows = [
      benchmark({ index_id: "B", index_name: "Beta", return_252d: null }),
      benchmark({ index_id: "A", index_name: "Alpha", return_252d: 0.2 }),
      benchmark({ index_id: "C", index_name: "Charlie", return_252d: 0.1 }),
    ];
    expect(sortBenchmarks(rows, "return_252d", "desc").map((item) => item.index_id)).toEqual(["A", "C", "B"]);
    expect(sortBenchmarks(rows, "name", "asc").map((item) => item.index_id)).toEqual(["A", "B", "C"]);
  });

  it("normalizes price series and computes baseline deltas", () => {
    const base = normalizeSeries(benchmark(), [price("2026-01-01", 100), price("2026-01-02", 110)]);
    const other = normalizeSeries(benchmark({ index_id: "TECH", index_name: "Tech" }), [
      price("2026-01-01", 50, { is_proxy: true }),
      price("2026-01-02", 60, { is_proxy: true }),
    ]);

    expect(base.points.map((point) => point.normalized)).toEqual([100, 110.00000000000001]);
    expect(base.periodReturn).toBeCloseTo(0.1);
    expect(other.isProxy).toBe(true);
    expect(baselineDelta(other, base)).toBeCloseTo(0.1);
    expect(mergeNormalizedSeries([base, other])).toEqual([
      { date: "2026-01-01", SP500: 100, SP500Close: 100, TECH: 100, TECHClose: 50 },
      { date: "2026-01-02", SP500: 110, SP500Close: 110, TECH: 120, TECHClose: 60 },
    ]);
  });

  it("returns an empty normalized series when history is unavailable", () => {
    const empty = normalizeSeries(benchmark(), []);
    expect(empty.points).toEqual([]);
    expect(empty.periodReturn).toBeNull();
    expect(baselineDelta(empty, undefined)).toBeNull();
  });
});
