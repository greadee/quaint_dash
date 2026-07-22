import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type BusinessStrengthScorecard, type ComparisonAsset, type ComparisonHistorySeries } from "../api";
import {
  assetMetricValue,
  calculateSeriesMetrics,
  comparisonModes,
  comparisonPeriods,
  formatComparisonValue,
  metricRegistry,
  parseComparisonState,
  rankValues,
  serializeComparisonState,
  type ComparisonMode,
  type ComparisonPeriod,
  type ComparisonState,
  type DifferenceMode,
  type MetricDefinition,
} from "../comparisonUtils";
import { money, percent } from "./routeFormatters";
import { ChartTypeToggle, EmptyRow, ErrorPanel, HelpDisclosure, MetricLine } from "./routeShared";
import type { HelpItem } from "./routeTypes";
import { BenchmarkPicker, TickerPicker } from "./routePickers";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar, usePageFeature } from "../pageFeatureStore";

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const parsed = useMemo(() => parseComparisonState(params), [params]);
  const state = parsed.state;
  const chartType = params.get("chart") === "bar" ? "bar" : "line";
  const [draft, setDraft] = useState("");
  const [assetWarning, setAssetWarning] = useState("");
  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [businessStrengthSort, setBusinessStrengthSort] = useState("overall_score");
  const [businessStrengthMode, setBusinessStrengthMode] = useState<"template-adjusted" | "common-metric">("template-adjusted");
  const showAssetStrip = usePageFeature("compare", "compare.assetStrip");
  const showChartTable = usePageFeature("compare", "compare.chartTable");
  const showValuation = usePageFeature("compare", "compare.valuation");
  const showGrowth = usePageFeature("compare", "compare.growth");
  const showQuality = usePageFeature("compare", "compare.quality");
  const showBalanceSheet = usePageFeature("compare", "compare.balanceSheet");
  const showCapitalAllocation = usePageFeature("compare", "compare.capitalAllocation");
  const showForwardScenarios = usePageFeature("compare", "compare.forwardScenarios");
  const showMethodology = usePageFeature("compare", "compare.methodology");
  const registry = useMemo(() => metricRegistry(), []);
  const primarySymbol = state.symbols[0] ?? draft.trim().toUpperCase();
  const benchmarkAssociations = useQuery({
    queryKey: ["asset-benchmark-associations", primarySymbol],
    queryFn: () => api.assetBenchmarkAssociations(primarySymbol),
    enabled: Boolean(primarySymbol),
    retry: false,
  });
  const comparison = useQuery({
    queryKey: ["comparison-workspace", state.symbols, state.benchmark, state.period, state.mode, state.currency],
    queryFn: () => api.comparisonWorkspace({
      symbols: [...state.symbols].sort(),
      benchmark: state.benchmark || undefined,
      period: state.period,
      mode: state.mode,
      currency: state.currency,
    }),
    enabled: state.symbols.length > 0,
    placeholderData: (previous) => previous,
  });
  const businessStrength = useQuery({
    queryKey: ["business-strength-compare", state.symbols],
    queryFn: () => api.compareBusinessStrength(state.symbols),
    enabled: state.symbols.length >= 2 && state.section === "business-strength",
    placeholderData: (previous) => previous,
  });
  const updateState = useCallback((next: Partial<ComparisonState>, replace = false) => {
    const merged: ComparisonState = { ...state, ...next };
    if (!merged.reference || !merged.symbols.includes(merged.reference)) merged.reference = merged.symbols[0] ?? "";
    const query = serializeComparisonState(merged);
    setParams(query ? new URLSearchParams(query) : new URLSearchParams(), { replace });
  }, [setParams, state]);
  const updateChartType = (value: "line" | "bar") => setParams((current) => { const next = new URLSearchParams(current); next.set("chart", value); return next; });
  useEffect(() => {
    if (!parsed.sanitized) return;
    const query = serializeComparisonState(state);
    setParams(query ? new URLSearchParams(query) : new URLSearchParams(), { replace: true });
  }, [parsed.sanitized, setParams, state]);
  useEffect(() => {
    if (state.benchmark || !benchmarkAssociations.data?.associations.length) return;
    const core = benchmarkAssociations.data.associations.find((item) => item.role === "core");
    if (core && state.symbols.length) updateState({ benchmark: core.benchmark_index_id }, true);
  }, [benchmarkAssociations.data, state.benchmark, state.symbols, updateState]);
  const addSymbol = (symbol: string) => {
    const nextSymbol = symbol.trim().toUpperCase();
    if (!nextSymbol) return;
    if (state.symbols.includes(nextSymbol)) {
      setAssetWarning(`${nextSymbol} is already selected.`);
      return;
    }
    if (state.symbols.length >= 5) {
      setAssetWarning("Maximum of five assets can be compared.");
      return;
    }
    setAssetWarning("");
    updateState({ symbols: [...state.symbols, nextSymbol], reference: state.reference || nextSymbol });
    setDraft("");
  };
  const removeSymbol = (symbol: string) => {
    const symbols = state.symbols.filter((item) => item !== symbol);
    updateState({ symbols, reference: state.reference === symbol ? symbols[0] ?? "" : state.reference });
  };
  const moveSymbol = (symbol: string, direction: -1 | 1) => {
    const index = state.symbols.indexOf(symbol);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= state.symbols.length) return;
    const symbols = [...state.symbols];
    [symbols[index], symbols[nextIndex]] = [symbols[nextIndex], symbols[index]];
    updateState({ symbols });
  };
  const data = comparison.data;
  const reference = data?.assets.find((asset) => asset.symbol === state.reference) ?? data?.assets[0] ?? null;
  const chartRows = useMemo(() => buildChartRows(data?.historical_series ?? [], hiddenSeries), [data?.historical_series, hiddenSeries]);
  const metricsBySymbol = useMemo(() => Object.fromEntries((data?.historical_series ?? []).map((series) => [series.symbol, calculateSeriesMetrics(series)])), [data?.historical_series]);
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Comparison workspace</p><h1>Compare</h1><p className="page-subtitle">Compare two to five stocks, ETFs, benchmarks, or portfolios with URL-shareable state, aligned history, risk, valuation, and methodology from stored application data.</p></div>
      <div className="actions"><PageLayoutButton pageId="compare" /><PageFeatureMenu pageId="compare" /></div>
    </div>
    <PageLayoutToolbar pageId="compare" />
    <OptionalFeaturesEmpty pageId="compare" />
    <section className="card compare-workspace-toolbar" aria-label="Comparison controls">
      <form onSubmit={(event) => { event.preventDefault(); addSymbol(draft); }}>
        <TickerPicker label="Add asset" value={draft} onChange={setDraft} />
        <button className="primary" disabled={!draft.trim() || state.symbols.length >= 5}><Plus size={17} />Add</button>
      </form>
      <div className="compare-control-row">
        <label>Period<select value={state.period} onChange={(event) => updateState({ period: event.target.value as ComparisonPeriod })}>{comparisonPeriods.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Mode<select value={state.mode} onChange={(event) => updateState({ mode: event.target.value as ComparisonMode })}>{comparisonModes.map((item) => <option key={item} value={item}>{item.replace(/-/g, " ")}</option>)}</select></label>
        <label>Currency<select value={state.currency} onChange={(event) => updateState({ currency: event.target.value as ComparisonState["currency"] })}><option value="native">Native</option><option value="USD">USD display</option><option value="CAD">CAD display</option></select></label>
        <label>Reference<select value={state.reference} onChange={(event) => updateState({ reference: event.target.value })}>{state.symbols.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>View<select value={state.differenceMode} onChange={(event) => updateState({ differenceMode: event.target.value as DifferenceMode })}><option value="absolute">Absolute</option><option value="difference">Difference</option><option value="percent-difference">Percent difference</option><option value="rank">Rank</option><option value="percentile">Percentile</option></select></label>
        <label>Section<select value={state.section} onChange={(event) => updateState({ section: event.target.value as ComparisonState["section"] })}><option value="performance">Performance</option><option value="business-strength">Business Strength</option><option value="valuation">Valuation</option><option value="growth">Growth</option><option value="quality">Quality</option><option value="balance-sheet">Balance sheet</option><option value="capital-allocation">Capital allocation</option><option value="methodology">Methodology</option></select></label>
      </div>
      <BenchmarkPicker value={state.benchmark} onChange={(value) => updateState({ benchmark: value })} associations={benchmarkAssociations.data?.associations} />
      <div className="selected-assets" aria-label="Selected assets">
        {state.symbols.map((symbol, index) => <span key={symbol} className={symbol === state.reference ? "selected" : ""}>
          <b>{symbol}</b>
          <button type="button" aria-label={`Move ${symbol} left`} onClick={() => moveSymbol(symbol, -1)} disabled={index === 0}>{"<"}</button>
          <button type="button" aria-label={`Move ${symbol} right`} onClick={() => moveSymbol(symbol, 1)} disabled={index === state.symbols.length - 1}>{">"}</button>
          <button type="button" aria-label={`Remove ${symbol}`} onClick={() => removeSymbol(symbol)}><X size={13} /></button>
        </span>)}
        {state.symbols.length ? <button type="button" onClick={() => updateState({ symbols: [], reference: "", benchmark: "" })}>Clear all</button> : null}
      </div>
      <div className="compare-alerts" aria-live="polite">
        {[assetWarning, ...parsed.warnings, ...(data?.coverage.warnings ?? [])].filter(Boolean).map((item) => <p key={item}>{item}</p>)}
      </div>
    </section>
    {state.symbols.length < 2 ? <section className="card compare-empty"><EmptyRow text="Add at least two comparable assets to show aligned performance, metric differences, and reference modes. The URL updates as you build the comparison." /></section> : null}
    {state.section === "business-strength" ? <BusinessStrengthComparison data={businessStrength.data?.assets ?? []} commonMetricCodes={businessStrength.data?.common_metric_codes ?? []} loading={businessStrength.isLoading} error={businessStrength.error} warning={businessStrength.data?.warning ?? null} sortKey={businessStrengthSort} onSort={setBusinessStrengthSort} mode={businessStrengthMode} onMode={setBusinessStrengthMode} /> : comparison.error ? <ErrorPanel error={comparison.error} /> : comparison.isLoading ? <CompareSkeleton /> : data ? <>
      {showAssetStrip ? <LayoutWidget pageId="compare" widgetId="compare.assetStrip"><section className="compare-asset-strip">
        {data.assets.map((asset) => <CompareAssetSummary key={asset.asset_id} asset={asset} freshness={data.freshness[asset.symbol]} reference={asset.symbol === reference?.symbol} />)}
      </section></LayoutWidget> : null}
      <section className="card compare-chart-card">
        <div className="card-heading">
          <div><p className="eyebrow">Historical prices</p><h2>Actual price comparison</h2></div>
          <div className="card-tools"><span>{data.coverage.common_start_date ? `Common start ${new Date(data.coverage.common_start_date).toLocaleDateString()}` : "No common history"}</span><ChartTypeToggle value={chartType} onChange={updateChartType} /><HelpDisclosure title="Performance methodology" items={performanceMethodologyHelp} /></div>
        </div>
        {chartRows.length ? <div className="compare-chart" aria-label="Actual price comparison chart">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "bar" ? <BarChart data={chartRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={32} />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip formatter={(value, name) => [typeof value === "number" ? money(value, data.coverage.currency === "native" ? undefined : data.coverage.currency) : value, name]} />
              <Legend />
              {data.historical_series.filter((series) => !hiddenSeries.includes(series.symbol)).map((series, index) => <Bar key={series.symbol} dataKey={series.symbol} fill={chartColors[index % chartColors.length]} />)}
            </BarChart> : <LineChart data={chartRows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" minTickGap={32} />
              <YAxis domain={["auto", "auto"]} />
              <Tooltip formatter={(value, name) => [typeof value === "number" ? money(value, data.coverage.currency === "native" ? undefined : data.coverage.currency) : value, name]} />
              <Legend />
              {data.historical_series.filter((series) => !hiddenSeries.includes(series.symbol)).map((series, index) => <Line key={series.symbol} type="linear" dataKey={series.symbol} stroke={chartColors[index % chartColors.length]} strokeDasharray={index % 2 ? "5 4" : undefined} dot={false} strokeWidth={2} />)}
            </LineChart>}
          </ResponsiveContainer>
        </div> : <EmptyRow text="No aligned stored price history is available for the selected assets and period." />}
        <div className="compare-series-toggles">
          {data.historical_series.map((series) => <button key={series.symbol} className={hiddenSeries.includes(series.symbol) ? "" : "selected"} onClick={() => setHiddenSeries((current) => current.includes(series.symbol) ? current.filter((item) => item !== series.symbol) : [...current, series.symbol])}>{series.symbol}</button>)}
        </div>
        {showChartTable ? <LayoutWidget pageId="compare" widgetId="compare.chartTable"><ComparisonChartTable series={data.historical_series} /></LayoutWidget> : null}
      </section>
      <ComparisonMetricSection title="Key performance and risk metrics" section="performance" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} />
      {showValuation ? <LayoutWidget pageId="compare" widgetId="compare.valuation"><ComparisonMetricSection title="Valuation" section="valuation" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} /></LayoutWidget> : null}
      {showGrowth ? <LayoutWidget pageId="compare" widgetId="compare.growth"><ComparisonMetricSection title="Growth" section="growth" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} /></LayoutWidget> : null}
      {showQuality ? <LayoutWidget pageId="compare" widgetId="compare.quality"><ComparisonMetricSection title="Quality and profitability" section="quality" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} /></LayoutWidget> : null}
      {showBalanceSheet ? <LayoutWidget pageId="compare" widgetId="compare.balanceSheet"><ComparisonMetricSection title="Balance sheet and risk" section="balance-sheet" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} /></LayoutWidget> : null}
      {showCapitalAllocation ? <LayoutWidget pageId="compare" widgetId="compare.capitalAllocation"><ComparisonMetricSection title="Capital allocation" section="capital-allocation" assets={data.assets} registry={registry} seriesMetrics={metricsBySymbol} reference={reference} mode={state.differenceMode} /></LayoutWidget> : null}
      {showForwardScenarios ? <LayoutWidget pageId="compare" widgetId="compare.forwardScenarios"><ComparisonForwardScenarios assets={data.assets} seriesMetrics={metricsBySymbol} /></LayoutWidget> : null}
      {showMethodology ? <LayoutWidget pageId="compare" widgetId="compare.methodology"><ComparisonMethodology data={data} registry={registry} /></LayoutWidget> : null}
    </> : null}
  </div>;
}

function BusinessStrengthComparison({
  data,
  commonMetricCodes,
  loading,
  error,
  warning,
  sortKey,
  onSort,
  mode,
  onMode,
}: {
  data: BusinessStrengthScorecard[];
  commonMetricCodes: string[];
  loading: boolean;
  error: unknown;
  warning: string | null;
  sortKey: string;
  onSort: (value: string) => void;
  mode: "template-adjusted" | "common-metric";
  onMode: (value: "template-adjusted" | "common-metric") => void;
}) {
  if (error) return <ErrorPanel error={error as Error} />;
  if (loading) return <CompareSkeleton />;
  if (!data.length) return <section className="card compare-empty"><EmptyRow text="Add at least two supported operating-company assets to compare deterministic Business Strength scorecards." /></section>;
  const categories = [...new Set(data.flatMap((asset) => asset.category_scores.map((item) => item.category_code)))];
  const sorted = [...data].sort((left, right) => scoreForSort(right, sortKey) - scoreForSort(left, sortKey));
  return <section className="card compare-section business-strength-compare">
    <div className="card-heading">
      <div><p className="eyebrow">Business Strength</p><h2>Side-by-side scorecard</h2></div>
      <div className="card-tools">
        <label>Sort<select value={sortKey} onChange={(event) => onSort(event.target.value)}><option value="overall_score">Overall</option><option value="confidence_score">Confidence</option><option value="easy_hold_score">Easy-hold</option>{categories.map((code) => <option key={code} value={code}>{labelForCategory(data[0], code)}</option>)}</select></label>
        <label>Mode<select value={mode} onChange={(event) => onMode(event.target.value as "template-adjusted" | "common-metric")}><option value="template-adjusted">Template-adjusted</option><option value="common-metric">Common metrics</option></select></label>
      </div>
    </div>
    {warning ? <p className="compare-warning">{warning}</p> : null}
    <div className="comparison-matrix wide" role="region" aria-label="Business Strength comparison table">
      <table>
        <thead><tr><th scope="col">Score</th>{sorted.map((asset) => <th scope="col" key={asset.symbol}>{asset.symbol}<span>{asset.template_name}</span></th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">Overall</th>{sorted.map((asset) => <td key={`${asset.symbol}-overall`}><strong>{scoreText(asset.overall_score)}</strong><span>{asset.classification}</span></td>)}</tr>
          <tr><th scope="row">Easy-hold</th>{sorted.map((asset) => <td key={`${asset.symbol}-easy`}>{scoreText(asset.easy_hold_score)}<span>{asset.easy_hold_label}</span></td>)}</tr>
          <tr><th scope="row">Confidence</th>{sorted.map((asset) => <td key={`${asset.symbol}-confidence`}>{asset.confidence_score.toFixed(0)}%</td>)}</tr>
          <tr><th scope="row">Completeness</th>{sorted.map((asset) => <td key={`${asset.symbol}-complete`}>{asset.completeness_score.toFixed(0)}%</td>)}</tr>
          {categories.map((code) => <tr key={code}><th scope="row"><details><summary>{labelForCategory(data[0], code)}</summary><p>Category scores are normalized by each asset's sector template.</p></details></th>{sorted.map((asset) => {
            const category = asset.category_scores.find((item) => item.category_code === code);
            return <td key={`${asset.symbol}-${code}`} className={bestWorstClass(sorted, code, asset)}><strong>{scoreText(category?.adjusted_score)}</strong><span>{category ? `${category.confidence_score.toFixed(0)}% confidence` : "not comparable"}</span></td>;
          })}</tr>)}
        </tbody>
      </table>
    </div>
    {mode === "common-metric" ? <CommonMetricComparison assets={sorted} commonMetricCodes={commonMetricCodes} /> : <TemplateAdjustedDetails assets={sorted} />}
  </section>;
}

function TemplateAdjustedDetails({ assets }: { assets: BusinessStrengthScorecard[] }) {
  return <div className="business-strength-compare-details">{assets.map((asset) => <details key={asset.symbol}><summary>{asset.symbol} metric drivers</summary><div className="model-table"><table><thead><tr><th>Category</th><th>Metric</th><th>Score</th><th>Status</th><th>Explanation</th></tr></thead><tbody>{asset.category_scores.flatMap((category) => category.metrics.map((metric) => <tr key={`${category.category_code}-${metric.metric_code}`}><td>{category.label}</td><td>{metric.label}</td><td>{scoreText(metric.metric_score)}</td><td>{metric.value_status.replace(/_/g, " ")}</td><td>{metric.explanation}</td></tr>))}</tbody></table></div></details>)}</div>;
}

function CommonMetricComparison({ assets, commonMetricCodes }: { assets: BusinessStrengthScorecard[]; commonMetricCodes: string[] }) {
  const common = commonMetricCodes.length ? commonMetricCodes : assets.length ? [...assets.map((asset) => new Set(asset.category_scores.flatMap((category) => category.metrics.map((metric) => metric.metric_code)))).reduce((left, right) => new Set([...left].filter((item) => right.has(item))))] : [];
  if (!common.length) return <EmptyRow text="No common metric definitions are shared by every selected Business Strength template." />;
  return <div className="model-table"><table><thead><tr><th>Common metric</th>{assets.map((asset) => <th key={asset.symbol}>{asset.symbol}</th>)}</tr></thead><tbody>{common.map((code) => <tr key={code}><th scope="row">{metricLabel(assets[0], code)}</th>{assets.map((asset) => {
    const metric = asset.category_scores.flatMap((category) => category.metrics).find((item) => item.metric_code === code);
    return <td key={`${asset.symbol}-${code}`}>{scoreText(metric?.metric_score)}<span>{metric?.value_status.replace(/_/g, " ")}</span></td>;
  })}</tr>)}</tbody></table></div>;
}

function scoreForSort(asset: BusinessStrengthScorecard, key: string) {
  if (key === "overall_score") return asset.overall_score ?? -1;
  if (key === "confidence_score") return asset.confidence_score;
  if (key === "easy_hold_score") return asset.easy_hold_score ?? -1;
  return asset.category_scores.find((item) => item.category_code === key)?.adjusted_score ?? -1;
}

function labelForCategory(asset: BusinessStrengthScorecard, code: string) {
  return asset.category_scores.find((item) => item.category_code === code)?.label ?? code.replace(/_/g, " ");
}

function metricLabel(asset: BusinessStrengthScorecard, code: string) {
  return asset.category_scores.flatMap((category) => category.metrics).find((metric) => metric.metric_code === code)?.label ?? code.replace(/_/g, " ");
}

function bestWorstClass(assets: BusinessStrengthScorecard[], code: string, asset: BusinessStrengthScorecard) {
  const values = assets.map((item) => item.category_scores.find((category) => category.category_code === code)?.adjusted_score ?? null).filter((value): value is number => value != null);
  const value = asset.category_scores.find((category) => category.category_code === code)?.adjusted_score;
  if (value == null || values.length < 2) return "";
  if (value === Math.max(...values)) return "best-cell";
  if (value === Math.min(...values)) return "worst-cell";
  return "";
}

function scoreText(value: number | null | undefined) {
  return value == null ? "insufficient" : value.toFixed(0);
}

const chartColors = ["#58d2c3", "#2f6bff", "#8f5cff", "#f2b544", "#ff8f5b"];
const performanceMethodologyHelp: HelpItem[] = [
  { term: "Aligned start", detail: "Every visible series starts at the latest common valid date, so returns are compared over the same stored window." },
  { term: "Total return", detail: "Uses adjusted close when available. If adjusted close is missing, the API falls back to stored close and labels the source." },
  { term: "Risk-free rate", detail: "Frontend risk metrics use a 0% risk-free assumption until an app-wide rate source is configured." },
  { term: "Missing data", detail: "Unsupported or missing values remain N/A and are never converted to zero." },
];

function CompareAssetSummary({ asset, freshness, reference }: { asset: ComparisonAsset; freshness?: { latest_price_date: string | null; latest_fiscal_period: string | null; provider: string; stale: boolean; stale_reason: string | null }; reference: boolean }) {
  return <article className={`card compare-asset-summary ${reference ? "reference" : ""}`}>
    <div className="asset-avatar" aria-hidden="true">{asset.symbol.slice(0, 2)}</div>
    <div>
      <p className="eyebrow">{reference ? "Reference asset" : "Asset"}</p>
      <h2>{asset.symbol}</h2>
      <span>{[asset.name ?? asset.asset_id, asset.exchange_code, asset.asset_type].filter(Boolean).join(" - ")}</span>
    </div>
    <dl>
      <div><dt>Price</dt><dd>{money(asset.latest_price, asset.currency)}</dd></div>
      <div><dt>Currency</dt><dd>{asset.currency}</dd></div>
      <div><dt>Sector</dt><dd>{asset.sector ?? "N/A"}</dd></div>
      <div><dt>Price date</dt><dd>{freshness?.latest_price_date ? new Date(freshness.latest_price_date).toLocaleDateString() : "N/A"}</dd></div>
    </dl>
    {freshness?.stale ? <p className="compare-warning">{freshness.stale_reason}</p> : null}
  </article>;
}

function CompareSkeleton() {
  return <section className="card compare-skeleton" aria-label="Loading comparison">
    <div className="skeleton-row" />
    <div className="skeleton-row" />
    <div className="skeleton-row" />
  </section>;
}

function buildChartRows(series: ComparisonHistorySeries[], hidden: string[]) {
  const byDate = new Map<string, Record<string, string | number>>();
  series.filter((item) => !hidden.includes(item.symbol)).forEach((item) => {
    item.points.forEach((point) => {
      const row = byDate.get(point.date) ?? { date: point.date };
      if (point.close != null) row[item.symbol] = point.close;
      byDate.set(point.date, row);
    });
  });
  return Array.from(byDate.values()).sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

function ComparisonChartTable({ series }: { series: ComparisonHistorySeries[] }) {
  return <details className="compare-chart-table">
    <summary>Accessible chart data</summary>
    <div className="model-table">
      <table>
        <caption>Latest actual price and cumulative return by asset</caption>
        <thead><tr><th scope="col">Asset</th><th scope="col">Start</th><th scope="col">End</th><th scope="col">Observations</th><th scope="col">Latest value</th><th scope="col">Return</th></tr></thead>
        <tbody>{series.map((item) => {
          const latest = item.points.at(-1);
          return <tr key={item.symbol}><th scope="row">{item.symbol}</th><td>{item.start_date ?? "N/A"}</td><td>{item.end_date ?? "N/A"}</td><td>{item.observation_count}</td><td>{latest?.close == null ? "N/A" : latest.close.toFixed(2)}</td><td>{percent(latest?.cumulative_return)}</td></tr>;
        })}</tbody>
      </table>
    </div>
  </details>;
}

function ComparisonMetricSection({
  title,
  section,
  assets,
  registry,
  seriesMetrics,
  reference,
  mode,
}: {
  title: string;
  section: MetricDefinition["section"];
  assets: ComparisonAsset[];
  registry: MetricDefinition[];
  seriesMetrics: Record<string, ReturnType<typeof calculateSeriesMetrics>>;
  reference: ComparisonAsset | null;
  mode: DifferenceMode;
}) {
  const definitions = registry.filter((item) => item.section === section || (section === "performance" && item.section === "risk"));
  if (!definitions.length) return <section className="card compare-section"><div className="card-heading"><div><p className="eyebrow">{section}</p><h2>{title}</h2></div><span>not available</span></div><EmptyRow text="No real application data source is wired for this metric group yet." /></section>;
  return <section className="card compare-section">
    <div className="card-heading"><div><p className="eyebrow">{section}</p><h2>{title}</h2></div><span>{mode.replace(/-/g, " ")}</span></div>
    <div className="comparison-matrix wide" role="region" aria-label={`${title} comparison table`}>
      <table>
        <thead><tr><th scope="col">Metric</th>{assets.map((asset) => <th scope="col" key={asset.symbol}>{asset.symbol}</th>)}</tr></thead>
        <tbody>{definitions.map((definition) => {
          const values = assets.map((asset) => ({ symbol: asset.symbol, value: comparisonValue(asset, definition, seriesMetrics) }));
          const ranks = rankValues(values, definition.direction);
          return <tr key={definition.key}>
            <th scope="row"><MetricDefinitionDisclosure definition={definition} /></th>
            {assets.map((asset) => <td key={`${definition.key}-${asset.symbol}`}>{displayMetricCell(asset, definition, values.find((item) => item.symbol === asset.symbol)?.value ?? null, reference, mode, ranks)}</td>)}
          </tr>;
        })}</tbody>
      </table>
    </div>
  </section>;
}

function MetricDefinitionDisclosure({ definition }: { definition: MetricDefinition }) {
  return <details className="metric-definition"><summary>{definition.label}</summary><p>{definition.description}</p><p>Formula: {definition.formula}</p><p>Source: {definition.source}; period: {definition.reportingPeriod}; direction: {definition.direction.replace(/_/g, " ")}.</p></details>;
}

function comparisonValue(asset: ComparisonAsset, definition: MetricDefinition, seriesMetrics: Record<string, ReturnType<typeof calculateSeriesMetrics>>) {
  const series = seriesMetrics[asset.symbol];
  if (definition.key in (series ?? {})) return series?.[definition.key as keyof typeof series] as number | null;
  return assetMetricValue(asset, definition.key);
}

function displayMetricCell(asset: ComparisonAsset, definition: MetricDefinition, value: number | null, reference: ComparisonAsset | null, mode: DifferenceMode, ranks: Record<string, number | null>) {
  if (mode === "rank") return ranks[asset.symbol] == null ? "N/A" : `#${ranks[asset.symbol]}`;
  const formatted = formatComparisonValue(value, definition, asset.currency);
  if (!reference || reference.symbol === asset.symbol || mode === "absolute") return formatted;
  const refValue = assetMetricValue(reference, definition.key);
  if (value == null || refValue == null) return "N/A";
  if (mode === "difference") return formatComparisonValue(value - refValue, definition, asset.currency);
  if (mode === "percent-difference") return refValue === 0 ? "N/A" : percent((value - refValue) / Math.abs(refValue));
  return formatted;
}

function ComparisonForwardScenarios({ assets, seriesMetrics }: { assets: ComparisonAsset[]; seriesMetrics: Record<string, ReturnType<typeof calculateSeriesMetrics>> }) {
  return <section className="card compare-section">
    <div className="card-heading"><div><p className="eyebrow">Estimates and forward scenarios</p><h2>Bear, base, and bull expected returns</h2></div><span>editable defaults</span></div>
    <div className="scenario-grid">
      {assets.map((asset) => {
        const base = seriesMetrics[asset.symbol]?.cagr;
        return <article key={asset.symbol}>
          <strong>{asset.symbol}</strong>
          <MetricLine label="Bear CAGR" value={percent(base == null ? null : base - 0.08)} />
          <MetricLine label="Base CAGR" value={percent(base)} />
          <MetricLine label="Bull CAGR" value={percent(base == null ? null : base + 0.08)} />
          <p>Defaults derive from local historical CAGR with +/- 8 percentage points. No analyst estimate is shown unless stored estimate data exists.</p>
        </article>;
      })}
    </div>
  </section>;
}

function ComparisonMethodology({ data, registry }: { data: { coverage: { calculation_version: string; mode: string; currency: string; warnings: string[] }; fx_policy: { source: string | null; rate_count: number; missing_pairs: string[] }; insights: string[]; benchmark: { index_id: string; name: string } | null }; registry: MetricDefinition[] }) {
  return <section className="card compare-section" id="methodology">
    <div className="card-heading"><div><p className="eyebrow">Data sources, methodology, and freshness</p><h2>Calculation notes</h2></div><span>{data.coverage.calculation_version}</span></div>
    <div className="methodology-grid">
      <p>Prices come from `asset_quote_daily`; adjusted close is preferred for total-return mode. Fundamentals come from latest stored company-level `financial_statement` JSON, using the resolved underlying asset for CDRs and wrappers. Benchmark context uses stored benchmark daily metrics.</p>
      <p>Currency policy: {data.coverage.currency === "native" ? "values remain in each asset's native currency." : `historical FX conversion uses stored ${data.fx_policy.source ?? "FX"} rates for ${data.fx_policy.rate_count} matched observation(s); missing pairs: ${data.fx_policy.missing_pairs.join(", ") || "none"}.`}</p>
      <p>Mode: {data.coverage.mode.replace(/-/g, " ")}. Missing, unsupported, stale, or insufficient values render as N/A and are not treated as zero.</p>
      {data.benchmark ? <p>Benchmark: {data.benchmark.index_id} - {data.benchmark.name}.</p> : <p>No benchmark selected.</p>}
      {data.insights.map((item) => <p key={item}>{item}</p>)}
    </div>
    <details className="metric-definition"><summary>Metric registry</summary><dl>{registry.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.description} Source: {item.source}.</dd></div>)}</dl></details>
  </section>;
}
