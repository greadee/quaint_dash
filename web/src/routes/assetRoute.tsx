import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { AssetAnalyticsPanel } from "./routeAnalytics";
import { money } from "./routeFormatters";
import { ChartTypeToggle, EmptyRow, ErrorPanel, Loading, RangeSelector, TabBar } from "./routeShared";
import type { AppNotification } from "./routeTypes";

type AssetDetailTab = "chart" | "news" | "fundamentals";
type ChartType = "line" | "bar";
const assetDetailTabs: { value: AssetDetailTab; label: string }[] = [
  { value: "chart", label: "Chart" },
  { value: "news", label: "News" },
  { value: "fundamentals", label: "Fundamentals" },
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
  const activity = useQuery({ queryKey: ["asset-activity", assetId, 10, 0], queryFn: () => api.assetActivity(assetId, 10, 0), enabled: tab === "news" });
  const setTab = (value: AssetDetailTab) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", value); return next; });
  const setParam = (key: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; });
  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorPanel error={asset.error} />;
  return <div className="page"><div className="page-title"><div><p className="eyebrow">{asset.data?.sector ?? "Asset"}</p><h1>{asset.data?.symbol} <small>{asset.data?.name}</small></h1></div><div className="actions"><Link className="button-link" to={params.get("from") ?? "/portfolios"}>Back</Link><Link className="button-link" to={`/compare?symbols=${asset.data?.asset_id ?? assetId}`}><BarChart3 size={17}/>Compare</Link><strong className="asset-price">{money(asset.data?.latest_price, asset.data?.currency)}</strong></div></div><TabBar tabs={assetDetailTabs} selected={tab} onSelect={setTab} label="Asset detail tabs" />{tab === "chart" ? <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Actual share price</p><h2>{asset.data?.symbol ?? assetId} price</h2></div><div className="chart-controls"><RangeSelector value={range} onChange={(value) => setParam("range", value)} /><ChartTypeToggle value={chartType} onChange={(value) => setParam("chart", value)} /></div></div>{prices.isLoading ? <Loading compact /> : prices.data && prices.data.length >= 2 ? <div className="chart" aria-label="Actual share price chart"><ResponsiveContainer width="100%" height="100%">{chartType === "bar" ? <BarChart data={prices.data}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => money(Number(value), asset.data?.currency)} /><Bar dataKey="close" name="Share price" fill="#245c4f" /></BarChart> : <LineChart data={prices.data}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => money(Number(value), asset.data?.currency)} /><Line type="monotone" dataKey="close" name="Share price" stroke="#245c4f" dot={false} strokeWidth={2}/></LineChart>}</ResponsiveContainer></div> : <EmptyRow text="Not enough stored daily price points are available for a clean chart in this range." />}</section> : null}{tab === "news" ? <section className="card"><div className="card-heading"><div><p className="eyebrow">Asset-specific events</p><h2>News and activity</h2></div></div>{activity.isLoading ? <Loading compact /> : activity.data?.items.length ? <div className="mini-list">{activity.data.items.map((item) => <article key={item.provider_transaction_id ?? item.transaction_id ?? item.timestamp}><div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div><span>{item.source}</span><b>{item.portfolio_name ?? item.provider_account_id ?? "local"}</b></article>)}</div> : <EmptyRow text="No asset-specific news feed is available yet; showing stored activity when present." />}</section> : null}{tab === "fundamentals" ? <AssetAnalyticsPanel payload={analytics.data} isLoading={analytics.isLoading} benchmark="" onBenchmarkChange={() => undefined} /> : null}</div>;
}
