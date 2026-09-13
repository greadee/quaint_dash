import type { ComparisonAsset, ComparisonHistorySeries } from "./api";

export type ComparisonPeriod = "1D" | "1W" | "1M" | "YTD" | "1Y" | "5Y";
export type ComparisonMode = "price-return" | "total-return" | "relative" | "drawdown" | "rolling-return" | "rolling-volatility";
export type ComparisonCurrency = "native" | "USD" | "CAD";
export type ComparisonSection = "performance" | "business-strength" | "valuation" | "growth" | "quality" | "balance-sheet" | "capital-allocation" | "estimates" | "methodology";
export type DifferenceMode = "absolute" | "difference" | "percent-difference" | "rank" | "percentile";
export type MetricDirection = "higher_is_better" | "lower_is_better" | "neutral" | "target_range";
export type ComparisonState = {
  symbols: string[];
  benchmark: string;
  period: ComparisonPeriod;
  mode: ComparisonMode;
  currency: ComparisonCurrency;
  section: ComparisonSection;
  reference: string;
  differenceMode: DifferenceMode;
};

export type MetricDefinition = {
  key: string;
  label: string;
  section: ComparisonSection | "risk";
  description: string;
  unit: "currency" | "percent" | "multiple" | "ratio" | "date";
  precision: number;
  direction: MetricDirection;
  applicableAssetTypes: string[];
  formula: string;
  source: string;
  reportingPeriod: string;
  stalenessDays: number;
  estimated: boolean;
  targetRange?: [number, number];
};

export const defaultComparisonState: ComparisonState = {
  symbols: [],
  benchmark: "",
  period: "1Y",
  mode: "total-return",
  currency: "native",
  section: "performance",
  reference: "",
  differenceMode: "absolute",
};

export const comparisonPeriods: ComparisonPeriod[] = ["1D", "1W", "1M", "1Y", "YTD", "5Y"];
export const comparisonModes: ComparisonMode[] = ["total-return", "price-return", "relative", "drawdown", "rolling-return", "rolling-volatility"];

const validSections: ComparisonSection[] = ["performance", "business-strength", "valuation", "growth", "quality", "balance-sheet", "capital-allocation", "estimates", "methodology"];
const validDifferenceModes: DifferenceMode[] = ["absolute", "difference", "percent-difference", "rank", "percentile"];
const validCurrencies: ComparisonCurrency[] = ["native", "USD", "CAD"];

export function parseComparisonState(params: URLSearchParams): { state: ComparisonState; warnings: string[]; sanitized: boolean } {
  const warnings: string[] = [];
  const rawSymbols = params.get("symbols") ?? [params.get("left"), params.get("right")].filter(Boolean).join(",");
  const symbols = uniqueSymbols(rawSymbols.split(",")).slice(0, 5);
  if (uniqueSymbols(rawSymbols.split(",")).length > 5) warnings.push("Only five assets can be compared at once.");
  const period = asOneOf(params.get("period")?.toUpperCase(), comparisonPeriods, defaultComparisonState.period);
  const mode = asOneOf(params.get("mode"), comparisonModes, defaultComparisonState.mode);
  const currency = asOneOf(params.get("currency"), validCurrencies, defaultComparisonState.currency);
  const section = asOneOf(params.get("section"), validSections, defaultComparisonState.section);
  const differenceMode = asOneOf(params.get("view"), validDifferenceModes, defaultComparisonState.differenceMode);
  const referenceParam = sanitizeSymbol(params.get("reference") ?? "");
  const reference = referenceParam && symbols.includes(referenceParam) ? referenceParam : symbols[0] ?? "";
  const benchmark = sanitizeSymbol(params.get("benchmark") ?? params.get("benchmark_index_id") ?? "");
  const state = { symbols, benchmark, period, mode, currency, section, reference, differenceMode };
  const sanitized = serializeComparisonState(state) !== params.toString();
  return { state, warnings, sanitized };
}

export function serializeComparisonState(state: ComparisonState): string {
  const params = new URLSearchParams();
  if (state.symbols.length) params.set("symbols", state.symbols.join(","));
  if (state.benchmark) params.set("benchmark", state.benchmark);
  if (state.period !== defaultComparisonState.period) params.set("period", state.period);
  if (state.mode !== defaultComparisonState.mode) params.set("mode", state.mode);
  if (state.currency !== defaultComparisonState.currency) params.set("currency", state.currency);
  if (state.section !== defaultComparisonState.section) params.set("section", state.section);
  if (state.reference && state.reference !== state.symbols[0]) params.set("reference", state.reference);
  if (state.differenceMode !== defaultComparisonState.differenceMode) params.set("view", state.differenceMode);
  return params.toString();
}

export function uniqueSymbols(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const symbol = sanitizeSymbol(value);
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    result.push(symbol);
  });
  return result;
}

export function sanitizeSymbol(value: string): string {
  return value.trim().toUpperCase().replace(/[^A-Z0-9._-]/g, "").slice(0, 32);
}

export function metricRegistry(): MetricDefinition[] {
  return [
    metric("period_return", "Period return", "performance", "Total change over the selected aligned period.", "percent", 1, "higher_is_better", "last normalized value / 100 - 1", "local adjusted-price series", "selected period"),
    metric("cagr", "CAGR", "performance", "Annualized compounded return from the aligned series.", "percent", 1, "higher_is_better", "(ending / beginning) ^ (252 / observations) - 1", "local calculation", "selected period"),
    metric("volatility", "Annualized volatility", "risk", "Annualized standard deviation of daily returns.", "percent", 1, "lower_is_better", "stdev(daily returns) * sqrt(252)", "local calculation", "selected period"),
    metric("sharpe", "Sharpe ratio", "risk", "Excess return per unit of total volatility. Risk-free rate is 0% in this local view.", "ratio", 2, "higher_is_better", "annualized return / annualized volatility", "local calculation", "selected period"),
    metric("sortino", "Sortino ratio", "risk", "Return divided by downside deviation.", "ratio", 2, "higher_is_better", "annualized return / annualized downside deviation", "local calculation", "selected period"),
    metric("max_drawdown", "Maximum drawdown", "risk", "Worst peak-to-trough loss in the aligned adjusted-price series.", "percent", 1, "lower_is_better", "min(value / running peak - 1)", "local calculation", "selected comparison period"),
    metric("latest_price", "Latest price", "valuation", "Latest stored close or adjusted close.", "currency", 2, "neutral", "provider close", "asset_quote_daily", "latest daily bar"),
    metric("market_cap", "Market cap", "valuation", "Stored asset market capitalization.", "currency", 0, "neutral", "provider supplied", "asset metadata", "latest asset row"),
    metric("pe_ratio", "Trailing P/E", "valuation", "Latest price divided by latest positive reported EPS.", "multiple", 1, "lower_is_better", "latest price / EPS", "local calculation from stored statements", "latest income statement"),
    metric("forward_pe", "Forward P/E", "valuation", "Latest price divided by stored forward EPS estimate.", "multiple", 1, "lower_is_better", "latest price / estimated EPS", "local calculation from earnings estimates", "next earnings estimate"),
    metric("price_to_sales", "Price/sales", "valuation", "Market cap divided by latest reported revenue.", "multiple", 1, "lower_is_better", "market cap / revenue", "local calculation from stored statements", "latest income statement"),
    metric("free_cash_flow_yield", "FCF yield", "valuation", "Latest reported free cash flow divided by market capitalization.", "percent", 1, "higher_is_better", "free cash flow / market cap", "local calculation from stored cash-flow statement", "latest cash-flow statement"),
    metric("revenue", "Revenue", "growth", "Latest reported revenue from stored income statement JSON.", "currency", 0, "higher_is_better", "provider statement value", "financial_statement", "latest income statement"),
    metric("forward_revenue", "Forward revenue", "growth", "Stored analyst revenue estimate from earnings calendar data.", "currency", 0, "higher_is_better", "provider estimate", "earnings_calendar_event", "next reported estimate"),
    metric("forward_eps", "Forward EPS", "growth", "Stored analyst EPS estimate from earnings calendar data.", "ratio", 2, "higher_is_better", "provider estimate", "earnings_calendar_event", "next reported estimate"),
    metric("net_income", "Net income", "quality", "Latest reported net income from stored income statement JSON.", "currency", 0, "higher_is_better", "provider statement value", "financial_statement", "latest income statement"),
    metric("gross_margin", "Gross margin", "quality", "Gross profit divided by revenue where both are stored.", "percent", 1, "higher_is_better", "gross profit / revenue", "local calculation from stored statements", "latest income statement"),
    metric("operating_margin", "Operating margin", "quality", "Operating income divided by revenue where both are stored.", "percent", 1, "higher_is_better", "operating income / revenue", "local calculation from stored statements", "latest income statement"),
    metric("net_margin", "Net margin", "quality", "Net income divided by revenue where both are stored.", "percent", 1, "higher_is_better", "net income / revenue", "local calculation from stored statements", "latest income statement"),
    metric("free_cash_flow", "Free cash flow", "quality", "Latest stored free cash flow or operating cash flow plus capex.", "currency", 0, "higher_is_better", "free cash flow; fallback operating cash flow + capex", "financial_statement cashflow", "latest cash-flow statement"),
    metric("roic", "ROIC", "quality", "Tax-adjusted operating income divided by invested capital when stored balance sheet inputs exist.", "percent", 1, "higher_is_better", "NOPAT / (debt + equity - cash)", "local calculation from stored statements", "latest fiscal period"),
    metric("roic_on_reinvestment", "ROIC on reinvestment", "quality", "Incremental NOPAT divided by incremental invested capital across the two latest stored periods.", "percent", 1, "higher_is_better", "change in NOPAT / change in invested capital", "local calculation from stored statements", "two latest fiscal periods"),
    metric("beta", "Beta", "risk", "Stored provider beta from asset metadata.", "ratio", 2, "lower_is_better", "provider supplied", "asset metadata", "latest asset row"),
    metric("cash", "Cash", "balance-sheet", "Latest stored cash and equivalents.", "currency", 0, "neutral", "provider statement value", "financial_statement balance", "latest balance sheet"),
    metric("total_debt", "Total debt", "balance-sheet", "Latest stored total debt, or short-term plus long-term debt when total debt is absent.", "currency", 0, "lower_is_better", "provider value or short debt + long debt", "financial_statement balance", "latest balance sheet"),
    metric("net_debt", "Net debt", "balance-sheet", "Total debt less cash where both are stored.", "currency", 0, "lower_is_better", "total debt - cash", "local calculation from balance sheet", "latest balance sheet"),
    metric("net_debt_to_ebitda", "Net debt/EBITDA", "balance-sheet", "Net debt divided by stored EBITDA.", "multiple", 1, "lower_is_better", "(total debt - cash) / EBITDA", "local calculation from stored statements", "latest fiscal period"),
    metric("current_ratio", "Current ratio", "balance-sheet", "Current assets divided by current liabilities.", "ratio", 2, "higher_is_better", "current assets / current liabilities", "local calculation from balance sheet", "latest balance sheet"),
    metric("debt_to_equity", "Debt/equity", "balance-sheet", "Total debt divided by stockholders' equity.", "ratio", 2, "lower_is_better", "total debt / equity", "local calculation from balance sheet", "latest balance sheet"),
    metric("customer_concentration", "Customer concentration", "balance-sheet", "Largest customer revenue share when the provider stores it in statement JSON.", "percent", 1, "lower_is_better", "provider-supplied concentration ratio", "financial_statement JSON", "latest income statement"),
    metric("revenue_concentration", "Revenue concentration", "balance-sheet", "Largest segment revenue share when the provider stores it in statement JSON.", "percent", 1, "lower_is_better", "provider-supplied concentration ratio", "financial_statement JSON", "latest income statement"),
    metric("shares_outstanding", "Shares", "capital-allocation", "Latest diluted weighted average shares or asset metadata shares outstanding.", "ratio", 0, "neutral", "provider statement value", "financial_statement or asset metadata", "latest fiscal period"),
    metric("dividend_yield", "Dividend yield", "capital-allocation", "Trailing dividends per share from stored events divided by latest price.", "percent", 1, "higher_is_better", "last 370 days dividends / latest price", "local calculation from dividend_event", "trailing 370 days"),
    metric("buyback_yield", "Buyback yield", "capital-allocation", "Repurchased stock cash flow divided by market cap where available.", "percent", 1, "higher_is_better", "absolute buybacks / market cap", "local calculation from cash-flow statement", "latest cash-flow statement"),
    metric("stock_based_compensation", "Stock-based comp", "capital-allocation", "Latest stored stock-based compensation expense.", "currency", 0, "lower_is_better", "provider statement value", "financial_statement cashflow", "latest cash-flow statement"),
    metric("acquisition_intensity", "Acquisition intensity", "capital-allocation", "Acquisition cash flow divided by revenue when stored cash-flow data exists.", "percent", 1, "neutral", "absolute acquisitions / revenue", "local calculation from stored statements", "latest fiscal period"),
    metric("reinvestment_rate", "Reinvestment rate", "capital-allocation", "Capex, acquisitions, and R&D divided by revenue when stored inputs exist.", "percent", 1, "target_range", "(capex + acquisitions + R&D) / revenue", "local calculation from stored statements", "latest fiscal period"),
  ];
}

function metric(
  key: string,
  label: string,
  section: MetricDefinition["section"],
  description: string,
  unit: MetricDefinition["unit"],
  precision: number,
  direction: MetricDirection,
  formula: string,
  source: string,
  reportingPeriod: string,
): MetricDefinition {
  return {
    key,
    label,
    section,
    description,
    unit,
    precision,
    direction,
    applicableAssetTypes: ["stock", "equity", "etf", "benchmark", "portfolio"],
    formula,
    source,
    reportingPeriod,
    stalenessDays: 45,
    estimated: false,
  };
}

export type SeriesMetrics = {
  period_return: number | null;
  cagr: number | null;
  volatility: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  observation_count: number;
};

export function calculateSeriesMetrics(series?: ComparisonHistorySeries): SeriesMetrics {
  const values = series?.points.map((point) => point.close).filter((value): value is number => value != null && Number.isFinite(value)) ?? [];
  if (values.length < 2) return emptySeriesMetrics(values.length);
  const returns = values.slice(1).map((value, index) => values[index] ? value / values[index] - 1 : null).filter((value): value is number => value != null && Number.isFinite(value));
  if (!returns.length) return emptySeriesMetrics(values.length);
  const periodReturn = values.at(-1)! / values[0] - 1;
  const years = returns.length / 252;
  const cagr = years > 0 ? Math.pow(values.at(-1)! / values[0], 1 / years) - 1 : null;
  const volatility = standardDeviation(returns) * Math.sqrt(252);
  const downside = returns.filter((value) => value < 0);
  const downsideDeviation = downside.length ? Math.sqrt(downside.reduce((sum, value) => sum + value * value, 0) / downside.length) * Math.sqrt(252) : null;
  return {
    period_return: periodReturn,
    cagr,
    volatility,
    sharpe: volatility ? (cagr ?? 0) / volatility : null,
    sortino: downsideDeviation ? (cagr ?? 0) / downsideDeviation : null,
    max_drawdown: maxDrawdown(values),
    observation_count: values.length,
  };
}

export function assetMetricValue(asset: ComparisonAsset, key: string): number | null {
  if (key === "latest_price") return asset.latest_price;
  if (key === "market_cap") return asset.market_cap;
  if (key === "pe_ratio") return asset.fundamentals.pe_ratio;
  if (key === "forward_pe") return asset.fundamentals.forward_pe;
  if (key === "price_to_sales") return asset.fundamentals.price_to_sales;
  if (key === "free_cash_flow_yield") return asset.fundamentals.free_cash_flow_yield;
  if (key === "revenue") return asset.fundamentals.revenue;
  if (key === "forward_revenue") return asset.fundamentals.forward_revenue;
  if (key === "forward_eps") return asset.fundamentals.forward_eps;
  if (key === "net_income") return asset.fundamentals.net_income;
  if (key === "gross_margin") return asset.fundamentals.gross_margin;
  if (key === "operating_margin") return asset.fundamentals.operating_margin;
  if (key === "net_margin") return asset.fundamentals.net_margin;
  if (key === "free_cash_flow") return asset.fundamentals.free_cash_flow;
  if (key === "roic") return asset.fundamentals.roic;
  if (key === "roic_on_reinvestment") return asset.fundamentals.roic_on_reinvestment;
  if (key === "beta") return asset.market_beta;
  if (key === "cash") return asset.fundamentals.cash;
  if (key === "total_debt") return asset.fundamentals.total_debt;
  if (key === "net_debt") return asset.fundamentals.net_debt;
  if (key === "net_debt_to_ebitda") return asset.fundamentals.net_debt_to_ebitda;
  if (key === "current_ratio") return asset.fundamentals.current_ratio;
  if (key === "debt_to_equity") return asset.fundamentals.debt_to_equity;
  if (key === "customer_concentration") return asset.fundamentals.customer_concentration;
  if (key === "revenue_concentration") return asset.fundamentals.revenue_concentration;
  if (key === "shares_outstanding") return asset.fundamentals.shares_outstanding;
  if (key === "dividend_yield") return asset.fundamentals.dividend_yield;
  if (key === "buyback_yield") return asset.fundamentals.buyback_yield;
  if (key === "stock_based_compensation") return asset.fundamentals.stock_based_compensation;
  if (key === "acquisition_intensity") return asset.fundamentals.acquisition_intensity;
  if (key === "reinvestment_rate") return asset.fundamentals.reinvestment_rate;
  return null;
}

export function rankValues(values: Array<{ symbol: string; value: number | null }>, direction: MetricDirection): Record<string, number | null> {
  const present = values.filter((item): item is { symbol: string; value: number } => item.value != null && Number.isFinite(item.value));
  const sorted = [...present].sort((left, right) => {
    if (direction === "lower_is_better") return left.value - right.value;
    return right.value - left.value;
  });
  return Object.fromEntries(values.map((item) => [item.symbol, item.value == null ? null : sorted.findIndex((candidate) => candidate.symbol === item.symbol) + 1]));
}

export function formatComparisonValue(value: number | null | undefined, definition: MetricDefinition, currency = "USD"): string {
  if (value == null || !Number.isFinite(value)) return "N/A";
  if (definition.unit === "percent") return `${(value * 100).toFixed(definition.precision)}%`;
  if (definition.unit === "multiple") return `${value.toFixed(definition.precision)}x`;
  if (definition.unit === "currency") {
    return new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency,
      notation: Math.abs(value) >= 1_000_000 ? "compact" : "standard",
      maximumFractionDigits: definition.precision,
    }).format(value);
  }
  return value.toFixed(definition.precision);
}

function emptySeriesMetrics(observationCount: number): SeriesMetrics {
  return { period_return: null, cagr: null, volatility: null, sharpe: null, sortino: null, max_drawdown: null, observation_count: observationCount };
}

function standardDeviation(values: number[]): number {
  if (values.length < 2) return 0;
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  return Math.sqrt(values.reduce((sum, value) => sum + (value - average) ** 2, 0) / (values.length - 1));
}

function maxDrawdown(values: number[]): number | null {
  if (!values.length) return null;
  let peak = values[0];
  let drawdown = 0;
  values.forEach((value) => {
    peak = Math.max(peak, value);
    if (peak > 0) drawdown = Math.min(drawdown, value / peak - 1);
  });
  return drawdown;
}

function asOneOf<T extends string>(value: string | null | undefined, valid: readonly T[], fallback: T): T {
  return valid.includes(value as T) ? value as T : fallback;
}
