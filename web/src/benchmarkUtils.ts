import type { BenchmarkIndexSummary, BenchmarkPricePoint } from "./api";

export type BenchmarkPeriod = "1D" | "1W" | "1M" | "YTD" | "1Y" | "5Y";
export type BenchmarkCategoryFilter = "all" | "core_geo" | "sector" | "industry" | "theme";
export type BenchmarkSortKey =
  | "name"
  | "category"
  | "return_1d"
  | "return_21d"
  | "return_252d"
  | "volatility_252d_ann"
  | "latest_close"
  | "freshness";
export type SortDirection = "asc" | "desc";

export const benchmarkPeriods: { value: BenchmarkPeriod; label: string; days?: number }[] = [
  { value: "1D", label: "1D", days: 1 },
  { value: "1W", label: "1W", days: 8 },
  { value: "1M", label: "1M", days: 35 },
  { value: "1Y", label: "1Y", days: 370 },
  { value: "YTD", label: "YTD" },
  { value: "5Y", label: "5Y", days: 365 * 5 + 12 },
];

export const benchmarkCategories: { value: BenchmarkCategoryFilter; label: string }[] = [
  { value: "all", label: "Overview" },
  { value: "core_geo", label: "Global Markets" },
  { value: "sector", label: "Sectors" },
  { value: "industry", label: "Industries" },
  { value: "theme", label: "Themes" },
];

const categoryLabels: Record<string, string> = {
  core_geo: "Core market",
  sector: "Sector",
  industry: "Industry",
  theme: "Theme",
};

export function benchmarkCategoryLabel(value: string | null | undefined): string {
  if (!value) return "Unclassified";
  return categoryLabels[value] ?? value.replace(/_/g, " ");
}

export function formatMissing(value: string | null | undefined): string {
  return value?.trim() || "-";
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

export function formatLevel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 2 }).format(value);
}

export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-CA", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function isProxyBenchmark(item: BenchmarkIndexSummary): boolean {
  return item.composition_quality === "proxy" || item.notes?.toLowerCase().includes("proxy") === true;
}

export function proxyLabel(item: BenchmarkIndexSummary): string {
  return isProxyBenchmark(item) ? "ETF proxy" : "Direct index";
}

export type FreshnessStatus = "fresh" | "stale" | "partial" | "unavailable" | "error" | "proxy";

export function benchmarkFreshness(item: BenchmarkIndexSummary, now = new Date()): FreshnessStatus {
  if (item.last_error) return "error";
  if (isProxyBenchmark(item)) return "proxy";
  if (!item.latest_close || !item.latest_metric_date) return "unavailable";
  if (!item.latest_composition_date) return "partial";
  const ageDays = (now.getTime() - new Date(item.latest_metric_date).getTime()) / 86400000;
  return ageDays > 14 ? "stale" : "fresh";
}

export function freshnessLabel(status: FreshnessStatus): string {
  const labels: Record<FreshnessStatus, string> = {
    fresh: "Fresh",
    stale: "Stale",
    partial: "Partial",
    unavailable: "Unavailable",
    error: "Error",
    proxy: "Proxy",
  };
  return labels[status];
}

export function periodStartDate(period: BenchmarkPeriod, now = new Date()): string | undefined {
  const start = new Date(now);
  if (period === "YTD") {
    start.setMonth(0, 1);
  } else {
    const days = benchmarkPeriods.find((item) => item.value === period)?.days;
    if (!days) return undefined;
    start.setDate(start.getDate() - days);
  }
  return start.toISOString().slice(0, 10);
}

export type NormalizedPoint = {
  date: string;
  [seriesKey: string]: number | string | null;
};

export type NormalizedSeries = {
  id: string;
  name: string;
  sourceSymbol: string | null;
  isProxy: boolean;
  periodReturn: number | null;
  points: { date: string; close: number; normalized: number }[];
};

export function normalizeSeries(
  benchmark: BenchmarkIndexSummary,
  prices: BenchmarkPricePoint[],
): NormalizedSeries {
  const usable = prices.filter((point) => Number.isFinite(point.adj_close ?? point.close) && (point.adj_close ?? point.close) > 0);
  const first = usable[0]?.adj_close ?? usable[0]?.close ?? null;
  const last = usable.at(-1)?.adj_close ?? usable.at(-1)?.close ?? null;
  const points = first
    ? usable.map((point) => {
      const close = point.adj_close ?? point.close;
      return { date: point.date, close, normalized: (close / first) * 100 };
    })
    : [];
  return {
    id: benchmark.index_id,
    name: benchmark.index_name,
    sourceSymbol: usable.at(-1)?.source_symbol ?? null,
    isProxy: usable.some((point) => point.is_proxy) || isProxyBenchmark(benchmark),
    periodReturn: first && last ? (last / first) - 1 : null,
    points,
  };
}

export function mergeNormalizedSeries(series: NormalizedSeries[]): NormalizedPoint[] {
  const byDate = new Map<string, NormalizedPoint>();
  series.forEach((item) => {
    item.points.forEach((point) => {
      const current = byDate.get(point.date) ?? { date: point.date };
      current[item.id] = Number(point.close.toFixed(4));
      current[`${item.id}Close`] = point.close;
      byDate.set(point.date, current);
    });
  });
  return Array.from(byDate.values()).sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

export function baselineDelta(series: NormalizedSeries, baseline: NormalizedSeries | undefined): number | null {
  if (!baseline || series.periodReturn == null || baseline.periodReturn == null) return null;
  return series.periodReturn - baseline.periodReturn;
}

function sortValue(item: BenchmarkIndexSummary, key: BenchmarkSortKey): number | string | null {
  if (key === "name") return item.index_name.toLowerCase();
  if (key === "category") return item.index_category;
  if (key === "freshness") return benchmarkFreshness(item);
  return item[key];
}

export function sortBenchmarks(
  items: BenchmarkIndexSummary[],
  key: BenchmarkSortKey,
  direction: SortDirection,
): BenchmarkIndexSummary[] {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...items].sort((left, right) => {
    const leftValue = sortValue(left, key);
    const rightValue = sortValue(right, key);
    if (leftValue == null && rightValue == null) return left.index_id.localeCompare(right.index_id);
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * multiplier || left.index_id.localeCompare(right.index_id);
    }
    return String(leftValue).localeCompare(String(rightValue)) * multiplier || left.index_id.localeCompare(right.index_id);
  });
}

export function parseSelected(value: string | null, fallback: string[] = []): string[] {
  const parsed = (value ?? "")
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  return Array.from(new Set(parsed.length ? parsed : fallback)).slice(0, 5);
}
