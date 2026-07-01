import { useQuery } from "@tanstack/react-query";
import { BarChart3, RefreshCw } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type BusinessStrengthScorecard, type BusinessStrengthMetric } from "../api";
import { AssetAnalyticsPanel } from "./routeAnalytics";
import { money, percent } from "./routeFormatters";
import { ChartTypeToggle, EmptyRow, ErrorPanel, Loading, RangeSelector, TabBar } from "./routeShared";
import type { AppNotification } from "./routeTypes";

type AssetDetailTab = "chart" | "news" | "fundamentals" | "business-strength";
type ChartType = "line" | "bar";
const assetDetailTabs: { value: AssetDetailTab; label: string }[] = [
  { value: "chart", label: "Chart" },
  { value: "news", label: "News" },
  { value: "fundamentals", label: "Fundamentals" },
  { value: "business-strength", label: "Business Strength" },
];

export function AssetDetailPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  void notify;
  const { assetId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as AssetDetailTab | null) ?? "chart";
  const range = params.get("range") ?? "1Y";
  const chartType = ((params.get("chart") as ChartType | null) ?? "line") === "bar" ? "bar" : "line";
  const asset = useQuery({ queryKey: ["asset", assetId], queryFn: () => api.asset(assetId) });
  const prices = useQuery({ queryKey: ["prices", assetId, range], queryFn: () => api.prices(assetId, { range }), enabled: tab === "chart" });
  const analytics = useQuery({ queryKey: ["asset-analytics", assetId, ""], queryFn: () => api.assetAnalytics(assetId), enabled: tab === "fundamentals" });
  const businessStrength = useQuery({ queryKey: ["asset-business-strength", assetId], queryFn: () => api.assetBusinessStrength(assetId), enabled: tab === "business-strength" });
  const activity = useQuery({ queryKey: ["asset-activity", assetId, 10, 0], queryFn: () => api.assetActivity(assetId, 10, 0), enabled: tab === "news" });
  const setTab = (value: AssetDetailTab) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", value); return next; });
  const setParam = (key: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; });
  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorPanel error={asset.error} />;
  return <div className="page"><div className="page-title"><div><p className="eyebrow">{asset.data?.sector ?? "Asset"}</p><h1>{asset.data?.symbol} <small>{asset.data?.name}</small></h1></div><div className="actions"><Link className="button-link" to={params.get("from") ?? "/portfolios"}>Back</Link><Link className="button-link" to={`/compare?symbols=${asset.data?.asset_id ?? assetId}`}><BarChart3 size={17}/>Compare</Link><strong className="asset-price">{money(asset.data?.latest_price, asset.data?.currency)}</strong></div></div><TabBar tabs={assetDetailTabs} selected={tab} onSelect={setTab} label="Asset detail tabs" />{tab === "chart" ? <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Actual share price</p><h2>{asset.data?.symbol ?? assetId} price</h2></div><div className="chart-controls"><RangeSelector value={range} onChange={(value) => setParam("range", value)} /><ChartTypeToggle value={chartType} onChange={(value) => setParam("chart", value)} /></div></div>{prices.isLoading ? <Loading compact /> : prices.data && prices.data.length >= 2 ? <div className="chart" aria-label="Actual share price chart"><ResponsiveContainer width="100%" height="100%">{chartType === "bar" ? <BarChart data={prices.data}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => money(Number(value), asset.data?.currency)} /><Bar dataKey="close" name="Share price" fill="#245c4f" /></BarChart> : <LineChart data={prices.data}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => money(Number(value), asset.data?.currency)} /><Line type="monotone" dataKey="close" name="Share price" stroke="#245c4f" dot={false} strokeWidth={2}/></LineChart>}</ResponsiveContainer></div> : <EmptyRow text="Not enough stored daily price points are available for a clean chart in this range." />}</section> : null}{tab === "news" ? <section className="card"><div className="card-heading"><div><p className="eyebrow">Asset-specific events</p><h2>News and activity</h2></div></div>{activity.isLoading ? <Loading compact /> : activity.data?.items.length ? <div className="mini-list">{activity.data.items.map((item) => <article key={item.provider_transaction_id ?? item.transaction_id ?? item.timestamp}><div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div><span>{item.source}</span><b>{item.portfolio_name ?? item.provider_account_id ?? "local"}</b></article>)}</div> : <EmptyRow text="No asset-specific news feed is available yet; showing stored activity when present." />}</section> : null}{tab === "fundamentals" ? <AssetAnalyticsPanel payload={analytics.data} isLoading={analytics.isLoading} benchmark="" onBenchmarkChange={() => undefined} /> : null}{tab === "business-strength" ? <BusinessStrengthPanel data={businessStrength.data} isLoading={businessStrength.isLoading} error={businessStrength.error} onRefresh={() => businessStrength.refetch()} /> : null}</div>;
}

function BusinessStrengthPanel({ data, isLoading, error, onRefresh }: { data?: BusinessStrengthScorecard; isLoading: boolean; error: unknown; onRefresh: () => void }) {
  if (isLoading) return <Loading />;
  if (error) return <ErrorPanel error={error as Error} />;
  if (!data) return <EmptyRow text="No deterministic Business Strength scorecard is available yet." />;
  return <div className="business-strength-view">
    <section className="card business-strength-hero">
      <div>
        <p className="eyebrow">Deterministic business quality</p>
        <h2>{scoreText(data.overall_score)} <small>{data.classification}</small></h2>
        <p>Template: {data.template_name} v{data.template_version}. Methodology: {data.methodology_version}.</p>
      </div>
      <dl>
        <div><dt>Easy-hold</dt><dd>{scoreText(data.easy_hold_score)} <span>{data.easy_hold_label}</span></dd></div>
        <div><dt>Confidence</dt><dd>{data.confidence_score.toFixed(0)}%</dd></div>
        <div><dt>Completeness</dt><dd>{data.completeness_score.toFixed(0)}%</dd></div>
        <div><dt>Data as of</dt><dd>{data.source_data_as_of ? new Date(data.source_data_as_of).toLocaleDateString() : "unknown"}</dd></div>
      </dl>
      <button type="button" onClick={onRefresh}><RefreshCw size={15} />Refresh</button>
    </section>
    <section className="business-strength-lists">
      <article className="card"><div className="card-heading"><div><p className="eyebrow">Drivers</p><h2>Top strengths</h2></div></div>{data.strengths.length ? <ul>{data.strengths.map((item) => <li key={item}>{item}</li>)}</ul> : <EmptyRow text="No positive drivers are available." />}</article>
      <article className="card"><div className="card-heading"><div><p className="eyebrow">Drivers</p><h2>Key weaknesses</h2></div></div>{data.weaknesses.length ? <ul>{data.weaknesses.map((item) => <li key={item}>{item}</li>)}</ul> : <EmptyRow text="No negative drivers are available." />}</article>
      <article className="card"><div className="card-heading"><div><p className="eyebrow">Data quality</p><h2>Missing and stale inputs</h2></div></div><p>{data.missing_critical_metrics.length ? data.missing_critical_metrics.join(", ") : "No missing critical metrics in the active template."}</p>{data.stale_metrics.length ? <p>Stale: {data.stale_metrics.join(", ")}</p> : null}</article>
    </section>
    <section className="business-strength-category-grid">
      {data.category_scores.map((category) => <article className="card business-strength-category" key={category.category_code}>
        <div className="card-heading"><div><p className="eyebrow">{percent(category.category_weight)}</p><h2>{category.label}</h2></div><strong>{scoreText(category.adjusted_score)}</strong></div>
        <p>{category.explanation}</p>
        <div className="business-strength-bars"><span style={{ width: `${Math.max(0, Math.min(100, category.adjusted_score ?? 0))}%` }} /></div>
        <dl><div><dt>Confidence</dt><dd>{category.confidence_score.toFixed(0)}%</dd></div><div><dt>Completeness</dt><dd>{category.completeness_score.toFixed(0)}%</dd></div></dl>
        <details><summary>Metric audit</summary><BusinessStrengthMetricTable metrics={category.metrics} /></details>
      </article>)}
    </section>
    <details className="card business-strength-audit">
      <summary>Full calculation audit</summary>
      <dl>
        <div><dt>Run</dt><dd>{data.analysis_run_id ?? "not persisted"}</dd></div>
        <div><dt>Template</dt><dd>{data.template_code}</dd></div>
        <div><dt>Sector</dt><dd>{data.sector ?? "unknown"}</dd></div>
        <div><dt>Industry</dt><dd>{data.industry ?? "unknown"}</dd></div>
        <div><dt>Peer group</dt><dd>{data.peer_group.join(", ") || "none"}</dd></div>
        <div><dt>Future agent layer</dt><dd>{data.future_research_enabled ? "enabled" : "disabled"}</dd></div>
      </dl>
    </details>
  </div>;
}

function BusinessStrengthMetricTable({ metrics }: { metrics: BusinessStrengthMetric[] }) {
  return <div className="model-table"><table><thead><tr><th>Metric</th><th>Value</th><th>Score</th><th>Contribution</th><th>Status</th><th>Source</th><th>Explanation</th></tr></thead><tbody>{metrics.map((metric) => <tr key={metric.metric_code}><th scope="row">{metric.label}</th><td>{formatMetric(metric)}</td><td>{scoreText(metric.metric_score)}</td><td>{metric.contribution == null ? "not used" : metric.contribution.toFixed(2)}</td><td>{metric.value_status.replace(/_/g, " ")}</td><td>{metric.source_timestamp ? `${metric.source} ${new Date(metric.source_timestamp).toLocaleDateString()}` : metric.source}</td><td>{metric.explanation}</td></tr>)}</tbody></table></div>;
}

function scoreText(value: number | null | undefined) {
  return value == null ? "insufficient data" : value.toFixed(0);
}

function formatMetric(metric: BusinessStrengthMetric) {
  if (metric.raw_value == null) return metric.value_status.replace(/_/g, " ");
  if (metric.unit === "percent") return percent(metric.raw_value);
  if (metric.unit === "multiple") return `${metric.raw_value.toFixed(1)}x`;
  return metric.raw_value.toFixed(2);
}
