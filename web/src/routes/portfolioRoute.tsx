import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Activity, ArrowUpRight, BarChart3, CircleDollarSign, ShieldCheck, WalletCards } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, Cell, Line, LineChart, Pie, PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type HoldingSignal, type NewsArticle, type OptimizationPreview, type Portfolio, type PortfolioFundamentals, type PortfolioPerformance, type PortfolioRisk, type Position } from "../api";
import { AnalyticsBlock, DataIssueList, ExposureBars } from "./routeAnalytics";
import { formatTimestamp, money, number, percent } from "./routeFormatters";
import { ChartTypeToggle, EmptyRow, ErrorPanel, Loading, Metric, RangeSelector, Signal, TabBar } from "./routeShared";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar, usePageFeature, usePageFeatureControls } from "../pageFeatureStore";

type PortfolioTopTab = "aggregate" | "portfolios" | "fundamentals";
type PortfolioDetailTab = "overview" | "holdings" | "performance" | "risk" | "optimization" | "fundamentals" | "activity";
type GainView = "total" | "unrealized";
type AllocationView = "grid" | "pie";
type ChartType = "line" | "bar";
type ExposureDimension = "asset_class" | "sector" | "country" | "industry" | "asset_type" | "currency";
const portfolioTopTabs: { value: PortfolioTopTab; label: string }[] = [
  { value: "aggregate", label: "Aggregate" },
  { value: "portfolios", label: "Portfolios" },
  { value: "fundamentals", label: "Fundamentals" },
];
const portfolioDetailTabs: { value: PortfolioDetailTab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "holdings", label: "Holdings" },
  { value: "performance", label: "Performance" },
  { value: "risk", label: "Risk" },
  { value: "optimization", label: "Optimization" },
  { value: "fundamentals", label: "Fundamentals" },
  { value: "activity", label: "Activity" },
];
const exposureTabs: { value: ExposureDimension; label: string }[] = [
  { value: "asset_class", label: "Asset class" },
  { value: "sector", label: "Sector" },
  { value: "country", label: "Country" },
  { value: "industry", label: "Industry" },
  { value: "currency", label: "Currency" },
];
const pieColors = ["#245c4f", "#7b6f5c", "#486b8f", "#9a6b54", "#6b7c45", "#8b5f79", "#587072", "#b18b3a"];
const MARKET_REFRESH_REFETCH_MS = 60_000;
export function PortfolioWorkspacePage() {
  const [params, setParams] = useSearchParams();
  const selected = (params.get("tab") as PortfolioTopTab | null) ?? "aggregate";
  const gainView = ((params.get("gain") as GainView | null) ?? "total") === "unrealized" ? "unrealized" : "total";
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios, refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const firstPortfolioId = portfolios.data?.[0]?.portfolio_id;
  const features = usePageFeatureControls("portfolio.workspace");
  const visibleTopTabs = portfolioTopTabs.filter((item) => item.value !== "fundamentals" || features.isEnabled("portfolio.workspace.fundamentals"));
  const resolvedSelected = visibleTopTabs.some((item) => item.value === selected) ? selected : "aggregate";
  const aggregate = useQuery({ queryKey: ["portfolio-aggregate"], queryFn: api.aggregatePortfolio, enabled: resolvedSelected === "aggregate" && Boolean(portfolios.data?.length), refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const positions = useQuery({ queryKey: ["positions", "all"], queryFn: api.aggregatePositions, enabled: resolvedSelected === "aggregate" && Boolean(aggregate.data), refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const fundamentals = useQuery({ queryKey: ["portfolio-fundamentals", firstPortfolioId], queryFn: () => api.portfolioFundamentals(firstPortfolioId!), enabled: resolvedSelected === "fundamentals" && Boolean(firstPortfolioId) && features.isEnabled("portfolio.workspace.fundamentals") });
  const setTab = (tab: PortfolioTopTab) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", tab); return next; });
  const setGainView = (value: GainView) => setParams((current) => { const next = new URLSearchParams(current); next.set("gain", value); return next; });
  if (portfolios.isLoading) return <Loading />;
  if (portfolios.error) return <ErrorPanel error={portfolios.error} />;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Portfolio management</p><h1>Portfolios</h1><p className="page-subtitle">Backend-sourced portfolio totals, holdings, fundamentals, risk, and optimization previews.</p></div>
      <div className="actions"><PageLayoutButton pageId="portfolio.workspace" /><PageFeatureMenu pageId="portfolio.workspace" /></div>
    </div>
    <PageLayoutToolbar pageId="portfolio.workspace" />
    <TabBar tabs={visibleTopTabs} selected={resolvedSelected} onSelect={setTab} label="Portfolio workspace tabs" />
    <GainViewToggle value={gainView} onChange={setGainView} />
    <OptionalFeaturesEmpty pageId="portfolio.workspace" />
    {resolvedSelected === "aggregate" ? <AggregateWorkspacePanel aggregate={aggregate.data} positions={positions.data ?? []} isLoading={aggregate.isLoading || positions.isLoading} gainView={gainView} /> : null}
    {resolvedSelected === "portfolios" ? <PortfolioCardGrid portfolios={portfolios.data ?? []} gainView={gainView} /> : null}
    {resolvedSelected === "fundamentals" ? fundamentals.isLoading ? <Loading /> : fundamentals.data ? <PortfolioFundamentalsView fundamentals={fundamentals.data} /> : <section className="card"><EmptyRow text="No portfolio fundamentals are available yet." /></section> : null}
  </div>;
}

function AggregateWorkspacePanel({ aggregate, positions, isLoading, gainView }: { aggregate?: Portfolio; positions: Position[]; isLoading: boolean; gainView: GainView }) {
  const [exposureDimension, setExposureDimension] = useState<ExposureDimension>("asset_class");
  const [allocationView, setAllocationView] = useState<AllocationView>("grid");
  const showAllocation = usePageFeature("portfolio.workspace", "portfolio.workspace.allocation");
  const showDataQuality = usePageFeature("portfolio.workspace", "portfolio.workspace.dataQuality");
  if (isLoading) return <Loading />;
  if (!aggregate) return <section className="card"><EmptyRow text="No portfolios are available yet." /></section>;
  const gain = portfolioGain(aggregate, gainView);
  return <>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Combined market value" value={money(aggregate.market_value, aggregate.base_ccy)} detail={aggregate.base_ccy} />
      <Metric icon={<ArrowUpRight />} label={gain.label} value={money(gain.amount, aggregate.base_ccy)} detail={percent(gain.returnPercent)} />
      <Metric icon={<Activity />} label="Holdings" value={String(aggregate.position_count)} />
      <Metric icon={<ShieldCheck />} label="Data source" value={aggregate.source ?? "duckdb"} detail={formatTimestamp(aggregate.as_of)} />
    </section>
    <section className="portfolio-layout-grid">
      {showAllocation ? <LayoutWidget pageId="portfolio.workspace" widgetId="portfolio.workspace.allocation"><AllocationPanel positions={positions} currency={aggregate.base_ccy} dimension={exposureDimension} view={allocationView} onDimensionChange={setExposureDimension} onViewChange={setAllocationView} /></LayoutWidget> : null}
      {showDataQuality ? <LayoutWidget pageId="portfolio.workspace" widgetId="portfolio.workspace.dataQuality"><section className="card">
        <div className="card-heading"><div><p className="eyebrow">Data quality</p><h2>Coverage</h2></div></div>
        <div className="signal-grid">
          <Signal label="Display currency" value={aggregate.display_currency ?? aggregate.base_ccy} />
          <Signal label="Missing FX" value={String(aggregate.fx_missing?.length ?? 0)} />
          <Signal label="Stale prices" value={String(positions.filter((item) => item.stale_price).length)} />
          <Signal label="Unavailable values" value={String(positions.filter((item) => item.market_value == null).length)} />
        </div>
      </section></LayoutWidget> : null}
    </section>
  </>;
}

function PortfolioCardGrid({ portfolios, gainView }: { portfolios: Portfolio[]; gainView: GainView }) {
  if (!portfolios.length) return <section className="card"><EmptyRow text="No portfolios yet." /></section>;
  return <section className="portfolio-card-grid">
    {portfolios.map((portfolio) => {
      const gain = portfolioGain(portfolio, gainView);
      return <Link className="portfolio-link-card" to={`/portfolios/${portfolio.portfolio_id}?tab=overview`} key={portfolio.portfolio_id} aria-label={`Open ${portfolio.name} portfolio`}>
        <div><p className="eyebrow">{portfolio.base_ccy}</p><h2>{portfolio.name}</h2></div>
        <strong>{money(portfolio.market_value, portfolio.base_ccy)}</strong>
        <span>{portfolio.position_count} holdings</span>
        <span className={(gain.amount ?? 0) >= 0 ? "positive" : "negative"}>{gain.label}: {money(gain.amount, portfolio.base_ccy)} {percent(gain.returnPercent)}</span>
      </Link>;
    })}
  </section>;
}

function GainViewToggle({ value, onChange }: { value: GainView; onChange: (value: GainView) => void }) {
  return <div className="actions">
    <button className={value === "total" ? "primary" : ""} onClick={() => onChange("total")}>Total gain</button>
    <button className={value === "unrealized" ? "primary" : ""} onClick={() => onChange("unrealized")}>Unrealized gain</button>
  </div>;
}

function portfolioGain(portfolio: Portfolio, gainView: GainView) {
  if (gainView === "unrealized") {
    return {
      label: "Unrealized gain",
      amount: portfolio.unrealized_gain,
      returnPercent: portfolio.unrealized_return_percent,
    };
  }
  return {
    label: "Total gain",
    amount: portfolio.total_gain ?? portfolio.unrealized_gain,
    returnPercent: portfolio.total_return_percent ?? portfolio.unrealized_return_percent,
  };
}

export function PortfolioDetailPage() {
  const { portfolioId = "" } = useParams();
  const id = Number(portfolioId);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as PortfolioDetailTab | null) ?? "overview";
  const range = params.get("range") ?? "1Y";
  const chartType = ((params.get("chart") as ChartType | null) ?? "line") === "bar" ? "bar" : "line";
  const benchmark = params.get("benchmark") ?? "";
  const setParam = useCallback((key: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; }), [setParams]);
  const features = usePageFeatureControls("portfolio.detail");
  const visibleDetailTabs = portfolioDetailTabs.filter((item) => {
    if (item.value === "risk") return features.isEnabled("portfolio.detail.riskTab");
    if (item.value === "optimization") return features.isEnabled("portfolio.detail.optimizationTab");
    if (item.value === "fundamentals") return features.isEnabled("portfolio.detail.fundamentalsTab");
    if (item.value === "activity") return features.isEnabled("portfolio.detail.activityTab");
    return true;
  });
  const resolvedTab = visibleDetailTabs.some((item) => item.value === tab) ? tab : "overview";
  const holdingGradesVisible = features.isEnabled("portfolio.detail.holdingGrades");
  const portfolio = useQuery({ queryKey: ["portfolio", id], queryFn: () => api.portfolio(id), enabled: Number.isFinite(id), refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const portfolioReady = Number.isFinite(id) && Boolean(portfolio.data);
  const positions = useQuery({ queryKey: ["positions", id], queryFn: () => api.positions(id), enabled: portfolioReady && (resolvedTab === "overview" || resolvedTab === "holdings"), refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const performance = useQuery({ queryKey: ["portfolio-performance", id, benchmark, range], queryFn: () => api.portfolioPerformance(id, { benchmark: benchmark || undefined, range }), enabled: portfolioReady && (resolvedTab === "overview" || resolvedTab === "performance") });
  const risk = useQuery({ queryKey: ["portfolio-risk", id, benchmark, range], queryFn: () => api.portfolioRisk(id, { benchmark: benchmark || undefined, lookback: range }), enabled: portfolioReady && (resolvedTab === "risk" || (resolvedTab === "overview" && Boolean(performance.data))) });
  const fundamentals = useQuery({ queryKey: ["portfolio-fundamentals", id, 5], queryFn: () => api.portfolioFundamentals(id, 5), enabled: portfolioReady && (resolvedTab === "fundamentals" || (resolvedTab === "overview" && Boolean(risk.data))) });
  const transactions = useQuery({ queryKey: ["transactions", id, 25, 0], queryFn: () => api.transactions(id, 25, 0), enabled: Number.isFinite(id) && resolvedTab === "activity" && features.isEnabled("portfolio.detail.activityTab") });
  const holdingSignals = useQuery({ queryKey: ["holding-signals", id, "1m"], queryFn: () => api.holdingSignals("1m", id), enabled: portfolioReady && resolvedTab === "holdings" && holdingGradesVisible && Boolean(positions.data) });
  const portfolioNews = useQuery({ queryKey: ["portfolio-news", id], queryFn: () => api.portfolioNews(id, { limit: 5, sort: "relevance" }), enabled: portfolioReady && resolvedTab === "overview" });
  useEffect(() => {
    if (resolvedTab !== tab) setParam("tab", resolvedTab);
  }, [resolvedTab, setParam, tab]);
  if (portfolio.isLoading) return <Loading />;
  if (portfolio.error) return <ErrorPanel error={portfolio.error} />;
  if (!portfolio.data) return <section className="card"><EmptyRow text="Portfolio not found." /></section>;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow"><Link to="/portfolios?tab=portfolios">Portfolios</Link> / {portfolio.data.base_ccy}</p><h1>{portfolio.data.name}</h1><p className="page-subtitle">Actual performance, risk, fundamentals, holdings, and optimizer preview from the Python backend.</p></div>
      <div className="overview-actions"><PageLayoutButton pageId="portfolio.detail" /><PageFeatureMenu pageId="portfolio.detail" /><RangeSelector value={range} onChange={(value) => setParam("range", value)} /><ChartTypeToggle value={chartType} onChange={(value) => setParam("chart", value)} /><input aria-label="Benchmark" value={benchmark} onChange={(event) => setParam("benchmark", event.target.value.toUpperCase())} placeholder="SP500" /></div>
    </div>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Market value" value={money(portfolio.data.market_value, portfolio.data.base_ccy)} />
      <Metric icon={<ArrowUpRight />} label="Historical TWR CAGR" value={percent(performance.data?.actual_twr_cagr)} detail={performance.data?.range} />
      <Metric icon={<Activity />} label="Forward expected CAGR" value={percent(fundamentals.data?.weighted_expected_cagr.value)} detail={`coverage ${percent(fundamentals.data?.weighted_expected_cagr.coverage)}`} />
      <Metric icon={<BarChart3 />} label="Sharpe" value={number(risk.data?.sharpe_ratio)} detail={`rf ${percent(risk.data?.risk_free_rate)}`} />
      <Metric icon={<WalletCards />} label="Holdings" value={String(portfolio.data.position_count)} />
    </section>
    <TabBar tabs={visibleDetailTabs} selected={resolvedTab} onSelect={(value) => setParam("tab", value)} label="Portfolio detail tabs" />
    <PageLayoutToolbar pageId="portfolio.detail" />
    <OptionalFeaturesEmpty pageId="portfolio.detail" />
    {resolvedTab === "overview" ? <PortfolioNewsPanel portfolioId={id} items={portfolioNews.data?.items ?? []} isLoading={portfolioNews.isLoading} /> : null}
    {resolvedTab === "overview" ? <PortfolioOverviewDetail performance={performance.data} risk={risk.data} fundamentals={fundamentals.data} positions={positions.data ?? []} currency={portfolio.data.base_ccy} chartType={chartType} loading={{ performance: performance.isLoading, risk: risk.isLoading, fundamentals: fundamentals.isLoading, positions: positions.isLoading }} /> : null}
    {resolvedTab === "holdings" ? <HoldingsTable positions={positions.data ?? []} signals={holdingSignals.data?.items ?? []} methodology={holdingSignals.data?.methodology} currency={portfolio.data.base_ccy} isLoading={positions.isLoading || (holdingGradesVisible && holdingSignals.isLoading)} portfolioId={id} /> : null}
    {resolvedTab === "performance" ? <PortfolioPerformanceView performance={performance.data} isLoading={performance.isLoading} chartType={chartType} /> : null}
    {resolvedTab === "risk" ? <PortfolioRiskView risk={risk.data} isLoading={risk.isLoading} /> : null}
    {resolvedTab === "optimization" ? <PortfolioOptimizationPanel portfolioId={id} /> : null}
    {resolvedTab === "fundamentals" ? fundamentals.isLoading ? <Loading /> : fundamentals.data ? <PortfolioFundamentalsView fundamentals={fundamentals.data} /> : <section className="card"><EmptyRow text="Portfolio fundamentals are unavailable." /></section> : null}
    {resolvedTab === "activity" ? <section className="card"><div className="card-heading"><div><p className="eyebrow">Activity</p><h2>Transactions</h2></div></div>{transactions.isLoading ? <Loading compact /> : transactions.data?.items.length ? <div className="mini-list">{transactions.data.items.map((item) => <article key={item.transaction_id}><div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div><span>{item.asset_id ?? item.currency ?? "cash"}</span><b>{item.cash_amount != null ? money(item.cash_amount, item.currency ?? portfolio.data.base_ccy) : number(item.quantity, 4)}</b></article>)}</div> : <EmptyRow text="No transactions recorded." />}</section> : null}
  </div>;
}

function PortfolioOverviewDetail({ performance, risk, fundamentals, positions, currency, chartType, loading }: { performance?: PortfolioPerformance; risk?: PortfolioRisk; fundamentals?: PortfolioFundamentals; positions: Position[]; currency: string; chartType: ChartType; loading: { performance: boolean; risk: boolean; fundamentals: boolean; positions: boolean } }) {
  const [exposureDimension, setExposureDimension] = useState<ExposureDimension>("asset_class");
  const [allocationView, setAllocationView] = useState<AllocationView>("grid");
  const showAllocation = usePageFeature("portfolio.detail", "portfolio.detail.overviewAllocation");
  const showRisk = usePageFeature("portfolio.detail", "portfolio.detail.overviewRisk");
  const showFundamentals = usePageFeature("portfolio.detail", "portfolio.detail.overviewFundamentals");
  const showLargestHoldings = usePageFeature("portfolio.detail", "portfolio.detail.overviewLargestHoldings");
  return <section className="portfolio-layout-grid">
    <PortfolioPerformanceView performance={performance} isLoading={loading.performance} chartType={chartType} compact />
    {showAllocation ? <LayoutWidget pageId="portfolio.detail" widgetId="portfolio.detail.overviewAllocation">{loading.positions ? <section className="card"><Loading compact /></section> : <AllocationPanel positions={positions} currency={currency} dimension={exposureDimension} view={allocationView} onDimensionChange={setExposureDimension} onViewChange={setAllocationView} />}</LayoutWidget> : null}
    {showRisk ? <LayoutWidget pageId="portfolio.detail" widgetId="portfolio.detail.overviewRisk"><section className="card"><div className="card-heading"><div><p className="eyebrow">Risk</p><h2>Risk and concentration</h2></div></div>{loading.risk ? <Loading compact /> : <div className="signal-grid"><Signal label="Volatility" value={percent(risk?.annualized_volatility)} /><Signal label="Sortino" value={number(risk?.sortino_ratio)} /><Signal label="Beta" value={number(risk?.beta)} /><Signal label="Max drawdown" value={percent(risk?.maximum_drawdown)} /><Signal label="Effective holdings" value={number(risk?.effective_number_of_holdings, 1)} /><Signal label="HHI" value={number(risk?.hhi, 3)} /></div>}</section></LayoutWidget> : null}
    {showFundamentals ? <LayoutWidget pageId="portfolio.detail" widgetId="portfolio.detail.overviewFundamentals"><section className="card"><div className="card-heading"><div><p className="eyebrow">Fundamentals</p><h2>Coverage-aware rollup</h2></div></div>{loading.fundamentals ? <Loading compact /> : <div className="signal-grid"><Signal label="Expected CAGR" value={percent(fundamentals?.weighted_expected_cagr.value)} /><Signal label="P/E" value={number(fundamentals?.pe_ratio.value)} /><Signal label="P/FCF" value={number(fundamentals?.price_to_free_cash_flow.value)} /><Signal label="Coverage" value={percent(fundamentals?.weighted_expected_cagr.coverage)} /></div>}</section></LayoutWidget> : null}
    {showLargestHoldings ? <LayoutWidget pageId="portfolio.detail" widgetId="portfolio.detail.overviewLargestHoldings"><section className="card"><div className="card-heading"><div><p className="eyebrow">Largest holdings</p><h2>Weight drivers</h2></div></div>{loading.positions ? <Loading compact /> : <div className="mini-list">{positions.slice(0, 6).map((item) => <article key={item.asset_id}><div><strong>{item.symbol}</strong><span>{item.name ?? "Asset"}</span></div><b>{percent(item.weight)}</b></article>)}</div>}</section></LayoutWidget> : null}
  </section>;
}

function PortfolioNewsPanel({ portfolioId, items, isLoading }: { portfolioId: number; items: NewsArticle[]; isLoading: boolean }) {
  if (isLoading) return <section className="card"><Loading compact /></section>;
  return <section className="card portfolio-news-widget">
    <div className="card-heading"><div><p className="eyebrow">Holding-aware feed</p><h2>Portfolio news</h2></div><Link className="button-link" to={`/news?portfolio_id=${portfolioId}&sort=relevance`}>Open terminal</Link></div>
    {items.length ? <div className="mini-list news-mini-list">{items.map((item) => <article key={item.article_id}><div><strong>{item.headline}</strong><span>{item.published_at ? new Date(item.published_at).toLocaleString() : "not dated"}</span></div><span>{item.assets[0]?.symbol ?? "Portfolio"}</span><b>{percent(item.relevance_score)}</b></article>)}</div> : <EmptyRow text="No mapped stories are available for this portfolio yet." />}
  </section>;
}

function HoldingsTable({ positions, signals, methodology, currency, isLoading, portfolioId }: { positions: Position[]; signals: HoldingSignal[]; methodology?: string; currency: string; isLoading: boolean; portfolioId: number }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"weight" | "symbol" | "gain">("weight");
  const signalByAsset = new Map(signals.map((item) => [item.asset_id, item]));
  const showHoldingGrades = usePageFeature("portfolio.detail", "portfolio.detail.holdingGrades");
  const filtered = positions.filter((item) => `${item.symbol} ${item.name ?? ""}`.toLowerCase().includes(query.toLowerCase())).sort((left, right) => sort === "symbol" ? left.symbol.localeCompare(right.symbol) : sort === "gain" ? (right.unrealized_gain ?? -Infinity) - (left.unrealized_gain ?? -Infinity) : (right.weight ?? -Infinity) - (left.weight ?? -Infinity));
  return <section className="card holdings-card"><div className="card-heading"><div><p className="eyebrow">Holdings</p><h2>Positions</h2></div><div className="card-tools"><label>Search<input value={query} onChange={(event) => setQuery(event.target.value)} /></label><label>Sort<select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="weight">Weight</option><option value="symbol">Ticker</option><option value="gain">Gain</option></select></label></div></div>{isLoading ? <Loading compact /> : filtered.length ? <><div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Class</th><th>Quantity</th><th>Price</th><th>Value</th><th>Weight</th><th>Book</th><th>Gain</th><th>Status</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.asset_id}><td><Link className="asset-link" to={`/assets/${item.asset_id}?from=/portfolios/${portfolioId}%3Ftab%3Dholdings`}><strong>{item.symbol}</strong><span>{item.name ?? item.asset_type ?? "Asset"}</span></Link></td><td>{item.allocation_class ?? "Other"}</td><td>{number(item.quantity, 4)}</td><td>{money(item.latest_price, item.currency)}</td><td>{money(item.market_value, currency)}</td><td>{percent(item.weight)}</td><td>{money(item.book_cost, currency)}</td><td className={(item.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money(item.unrealized_gain, currency)}</td><td>{item.stale_price ? item.stale_reason ?? "stale" : item.data_status ?? "available"}</td></tr>)}</tbody></table></div>{showHoldingGrades ? <LayoutWidget pageId="portfolio.detail" widgetId="portfolio.detail.holdingGrades"><HoldingKiviatGrid positions={filtered} signalByAsset={signalByAsset} methodology={methodology} /></LayoutWidget> : null}</> : <EmptyRow text="No holdings match this search." />}</section>;
}

function HoldingKiviatGrid({ positions, signalByAsset, methodology }: { positions: Position[]; signalByAsset: Map<string, HoldingSignal>; methodology?: string }) {
  return <div className="holding-kiviat-section">
    <div className="card-heading kiviat-heading"><div><p className="eyebrow">Kiviat factors</p><h3>Holding grades</h3></div><span>{methodology ?? "Stored factor scores load from the holdings signal endpoint."}</span></div>
    <div className="holding-kiviat-grid">
      {positions.map((position) => <HoldingKiviatCard key={position.asset_id} position={position} signal={signalByAsset.get(position.asset_id)} />)}
    </div>
  </div>;
}

function HoldingKiviatCard({ position, signal }: { position: Position; signal?: HoldingSignal }) {
  const chartData = (signal?.components ?? []).map((component) => ({
    factor: shortFactor(component.name),
    score: component.score == null ? 50 : Math.max(0, Math.min(100, (component.score + 100) / 2)),
    rawScore: component.score,
    grade: component.grade ?? "Incomplete",
    available: component.available,
    detail: component.detail,
  }));
  const strengths = signal?.components.filter((component) => component.available && (component.score ?? 0) >= 25) ?? [];
  const weaknesses = signal?.components.filter((component) => component.available && (component.score ?? 0) <= -10) ?? [];
  const missing = signal?.components.filter((component) => !component.available) ?? [];
  return <article className={`holding-kiviat-card ${actionClass(signal?.action)}`}>
    <div className="holding-kiviat-title">
      <div><strong>{position.symbol}</strong><span>{position.asset_type ?? "Holding"}</span></div>
      <b>{signal?.grade ?? "Incomplete"}</b>
    </div>
    <div className="holding-kiviat-chart" aria-label={`${position.symbol} factor Kiviat diagram`}>
      {chartData.length ? <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={chartData} outerRadius="72%">
          <PolarGrid />
          <PolarAngleAxis dataKey="factor" tick={{ fontSize: 10 }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="score" name="Factor grade" stroke="#245c4f" fill="#245c4f" fillOpacity={0.22} />
          <Tooltip formatter={(value, _name, item) => [`${number((Number(value) - 50) * 2, 1)} score`, `${item.payload.grade}`]} />
        </RadarChart>
      </ResponsiveContainer> : <EmptyRow text="No factor scores are available for this holding yet." />}
    </div>
    <div className="holding-grade-strip">
      <span>{signal?.action ?? "No signal"}</span>
      <span>Confidence {percent(signal?.confidence)}</span>
      <span>1m return {percent(signal?.return_value)}</span>
    </div>
    <FactorSummary title="Strengths" items={strengths} empty="No strong positive factors." />
    <FactorSummary title="Weaknesses" items={weaknesses} empty="No material weak factors." />
    {missing.length ? <FactorSummary title="Missing" items={missing} empty="" /> : null}
  </article>;
}

function FactorSummary({ title, items, empty }: { title: string; items: NonNullable<HoldingSignal["components"]>; empty: string }) {
  return <div className="factor-summary"><strong>{title}</strong>{items.length ? items.slice(0, 3).map((item) => <span key={`${title}-${item.name}`}>{item.name}: {item.grade ?? "Incomplete"}</span>) : <span>{empty}</span>}</div>;
}

function shortFactor(name: string) {
  return name
    .replace("Financial strength", "Fin. strength")
    .replace("Profitability", "Profit")
    .replace("Institutional buying", "Inst. buying");
}

function actionClass(action: string | undefined) {
  const normalized = action?.toLowerCase() ?? "";
  if (normalized.includes("buy")) return "buy";
  if (normalized.includes("sell")) return "sell";
  return "hold";
}

function PortfolioPerformanceView({ performance, isLoading, chartType, compact = false }: { performance?: PortfolioPerformance; isLoading: boolean; chartType: ChartType; compact?: boolean }) {
  if (isLoading) return <Loading />;
  if (!performance) return <section className="card"><EmptyRow text="Performance is unavailable." /></section>;
  const chartPoints = performance.points.filter((point) => point.portfolio_return_index != null);
  return <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Normalized performance</p><h2>Portfolio TWR index</h2></div><span>{performance.observation_count} observations</span></div>{chartPoints.length >= 2 ? <div className="chart" aria-label="Normalized portfolio performance chart"><ResponsiveContainer width="100%" height="100%">{chartType === "bar" ? <BarChart data={chartPoints}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => Number(value).toFixed(1)} /><Bar dataKey="portfolio_return_index" name="Portfolio TWR index" fill="#245c4f" /></BarChart> : <LineChart data={chartPoints}><XAxis dataKey="date" minTickGap={28}/><YAxis domain={["auto", "auto"]}/><Tooltip formatter={(value) => Number(value).toFixed(1)} /><Line type="monotone" dataKey="portfolio_return_index" name="Portfolio TWR index" stroke="#245c4f" dot={false} strokeWidth={2}/></LineChart>}</ResponsiveContainer></div> : <EmptyRow text="Not enough complete valuation points are available for a clean normalized chart in this range." />}<div className="signal-grid"><Signal label="TWR CAGR" value={percent(performance.actual_twr_cagr)} /><Signal label="Benchmark CAGR" value={percent(performance.benchmark_cagr)} /><Signal label="Excess CAGR" value={percent(performance.excess_cagr)} /><Signal label="Coverage" value={percent(performance.coverage)} /></div>{!compact && performance.missing_inputs.length ? <DataIssueList items={performance.missing_inputs} /> : null}</section>;
}

function PortfolioRiskView({ risk, isLoading }: { risk?: PortfolioRisk; isLoading: boolean }) {
  if (isLoading) return <Loading />;
  if (!risk) return <section className="card"><EmptyRow text="Risk metrics are unavailable." /></section>;
  return <section className="card"><div className="card-heading"><div><p className="eyebrow">Risk definitions</p><h2>Annualized daily-return metrics</h2></div><span>risk-free {percent(risk.risk_free_rate)}</span></div><div className="signal-grid deep"><Signal label="Annualized return" value={percent(risk.annualized_return)} /><Signal label="Annualized volatility" value={percent(risk.annualized_volatility)} /><Signal label="Sharpe" value={number(risk.sharpe_ratio)} /><Signal label="Sortino" value={number(risk.sortino_ratio)} /><Signal label="Beta" value={number(risk.beta)} /><Signal label="Alpha" value={percent(risk.alpha)} /><Signal label="Correlation" value={number(risk.correlation)} /><Signal label="Max drawdown" value={percent(risk.maximum_drawdown)} /><Signal label="Downside deviation" value={percent(risk.downside_deviation)} /><Signal label="Observation count" value={String(risk.observation_count)} /><Signal label="Effective holdings" value={number(risk.effective_number_of_holdings, 1)} /><Signal label="Weight balance score" value={number(risk.weight_balance_score, 1)} /></div><div className="analytics-detail-grid"><AnalyticsBlock title="Asset class concentration"><ExposureBars values={risk.asset_class_concentration} /></AnalyticsBlock><AnalyticsBlock title="Sector concentration"><ExposureBars values={risk.sector_concentration} /></AnalyticsBlock><AnalyticsBlock title="Country concentration"><ExposureBars values={risk.geographic_concentration} /></AnalyticsBlock><AnalyticsBlock title="Currency concentration"><ExposureBars values={risk.currency_concentration} /></AnalyticsBlock></div>{risk.missing_inputs.length ? <DataIssueList items={risk.missing_inputs} /> : null}</section>;
}

function PortfolioFundamentalsView({ fundamentals }: { fundamentals: PortfolioFundamentals }) {
  return <section className="card"><div className="card-heading"><div><p className="eyebrow">Fundamentals</p><h2>Weighted rollup with coverage</h2></div><span>{fundamentals.horizon_years}y horizon</span></div><div className="signal-grid"><Signal label="Forward expected CAGR" value={percent(fundamentals.weighted_expected_cagr.value)} /><Signal label="Expected CAGR coverage" value={percent(fundamentals.weighted_expected_cagr.coverage)} /><Signal label="P/E" value={number(fundamentals.pe_ratio.value)} /><Signal label="P/FCF" value={number(fundamentals.price_to_free_cash_flow.value)} /><Signal label="Dividend yield" value={percent(fundamentals.dividend_yield.value)} /><Signal label="Margin of safety" value={percent(fundamentals.margin_of_safety.value)} /></div><div className="table-wrap"><table><thead><tr><th>Holding</th><th>Value</th><th>Weight</th><th>Expected CAGR</th><th>Contribution</th><th>P/E</th><th>P/FCF</th><th>Coverage</th></tr></thead><tbody>{fundamentals.holdings.map((item) => <tr key={item.asset_id}><td><Link to={`/assets/${item.asset_id}`} className="asset-link"><strong>{item.symbol}</strong><span>{item.missing_inputs.join(", ") || "inputs covered"}</span></Link></td><td>{money(item.market_value, fundamentals.base_currency)}</td><td>{percent(item.weight)}</td><td>{percent(item.expected_cagr)}</td><td>{percent(item.expected_cagr_contribution)}</td><td>{number(item.pe_ratio)}</td><td>{number(item.price_to_free_cash_flow)}</td><td>{item.coverage_status}</td></tr>)}</tbody></table></div>{fundamentals.missing_inputs.length ? <DataIssueList items={fundamentals.missing_inputs} /> : null}</section>;
}

function PortfolioOptimizationPanel({ portfolioId }: { portfolioId: number }) {
  const [preview, setPreview] = useState<OptimizationPreview | null>(null);
  const [showOptimized, setShowOptimized] = useState(true);
  const optimize = useMutation({ mutationFn: (objective: OptimizationPreview["objective"]) => api.optimizePortfolio(portfolioId, objective), onSuccess: setPreview });
  const weights = showOptimized ? preview?.optimized_weights : preview?.current_weights;
  const sum = weights ? Object.values(weights).reduce((total, value) => total + value, 0) : null;
  return <section className="card"><div className="card-heading"><div><p className="eyebrow">Preview only</p><h2>Backend optimization</h2></div><span aria-live="polite">{preview?.status ?? "not run"}</span></div><div className="actions"><button className="primary" onClick={() => optimize.mutate("max_expected_cagr")} disabled={optimize.isPending}>Max CAGR</button><button className="primary" onClick={() => optimize.mutate("max_risk_adjusted_return")} disabled={optimize.isPending}>Max Risk-Adjusted</button><label className="toggle-row"><input type="checkbox" checked={showOptimized} onChange={(event) => setShowOptimized(event.target.checked)} />Optimized allocation</label></div>{optimize.error ? <ErrorPanel error={optimize.error} /> : null}{optimize.isPending ? <Loading compact /> : preview ? <><div className="signal-grid"><Signal label="Current expected CAGR" value={percent(preview.before.expected_cagr)} /><Signal label="Optimized expected CAGR" value={percent(preview.after.expected_cagr)} /><Signal label="Current Sharpe" value={number(preview.before.expected_sharpe)} /><Signal label="Optimized Sharpe" value={number(preview.after.expected_sharpe)} /><Signal label="Turnover" value={percent(preview.estimated_turnover)} /><Signal label="Weight sum" value={percent(sum)} /></div><p className="muted-copy">{preview.solver_message}</p><div className="table-wrap"><table><thead><tr><th>Asset</th><th>Current</th><th>Optimized</th><th>Delta</th></tr></thead><tbody>{Object.keys(preview.current_weights).sort().map((assetId) => <tr key={assetId}><td>{assetId}</td><td>{percent(preview.current_weights[assetId])}</td><td>{percent(preview.optimized_weights[assetId])}</td><td>{percent(preview.weight_deltas[assetId])}</td></tr>)}</tbody></table></div>{preview.warnings.length ? <DataIssueList items={preview.warnings} /> : null}</> : <EmptyRow text="Run an optimization objective to preview target weights. This does not persist any trades." />}</section>;
}

const trancheLabels: Record<ExposureDimension, string> = {
  asset_class: "Other",
  sector: "Unclassified sector",
  country: "Unclassified geography",
  industry: "Unclassified industry",
  asset_type: "Unclassified type",
  currency: "Unknown currency",
};
function AllocationPanel({ positions, currency, dimension, view, onDimensionChange, onViewChange }: { positions: Position[]; currency: string; dimension: ExposureDimension; view: AllocationView; onDimensionChange: (dimension: ExposureDimension) => void; onViewChange: (view: AllocationView) => void }) {
  const [selectedGroupLabel, setSelectedGroupLabel] = useState<string | null>(null);
  const exposures = groupPositions(positions, dimension);
  const selectedGroup = exposures.find((group) => group.label === selectedGroupLabel) ?? null;
  const activeLabel = exposureTabs.find((tab) => tab.value === dimension)?.label ?? "Allocation";
  const emptyText = "No exposure metadata is available.";
  const body = exposures.length
    ? view === "pie"
      ? <AllocationPie groups={exposures} currency={currency} selectedGroup={selectedGroupLabel} onSelect={setSelectedGroupLabel} />
      : <AllocationGrid groups={exposures} currency={currency} selectedGroup={selectedGroupLabel} onSelect={setSelectedGroupLabel} />
    : <EmptyRow text={emptyText} />;
  return <section className="card">
    <div className="card-heading">
      <div><p className="eyebrow">Exposure</p><h2>{activeLabel} allocation</h2></div>
      <div className="card-tools allocation-tools">
        <div className="segmented-control" role="tablist" aria-label="Exposure dimension">
          {exposureTabs.map((tab) => <button key={tab.value} role="tab" aria-selected={dimension === tab.value} className={dimension === tab.value ? "primary" : ""} onClick={() => onDimensionChange(tab.value)}>{tab.label}</button>)}
        </div>
        <div className="segmented-control" aria-label="Allocation view">
          <button className={view === "grid" ? "primary" : ""} onClick={() => onViewChange("grid")}>Grid</button>
          <button className={view === "pie" ? "primary" : ""} onClick={() => onViewChange("pie")}>Pie</button>
        </div>
      </div>
    </div>
    {body}
    {selectedGroup ? <AllocationHoldingList group={selectedGroup} currency={currency} dimensionLabel={activeLabel} onClose={() => setSelectedGroupLabel(null)} /> : null}
  </section>;
}
function AllocationGrid({ groups, currency, selectedGroup, onSelect }: { groups: AllocationGroup[]; currency: string; selectedGroup: string | null; onSelect: (label: string) => void }) {
  return <div className="tranche-grid">{groups.map((group) => <button type="button" className={`tranche ${selectedGroup === group.label ? "active" : ""}`} key={group.label} onClick={() => onSelect(group.label)} aria-pressed={selectedGroup === group.label}><div><strong>{group.label}</strong><span>{group.count} holdings</span></div><b>{money(group.marketValue, currency)}</b><div className="bar"><span style={{ width: `${Math.max(group.weight * 100, 2)}%` }} /></div><em>{percent(group.weight)} weight</em><em>{percent(group.returnPercent)} return</em></button>)}</div>;
}
function AllocationPie({ groups, currency, selectedGroup, onSelect }: { groups: AllocationGroup[]; currency: string; selectedGroup: string | null; onSelect: (label: string) => void }) {
  return <div className="allocation-pie-layout">
    <div className="allocation-pie-chart" aria-label="Allocation pie chart">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={groups} dataKey="marketValue" nameKey="label" innerRadius="52%" outerRadius="82%" paddingAngle={2}>
            {groups.map((group, index) => <Cell key={group.label} fill={pieColors[index % pieColors.length]} />)}
          </Pie>
          <Tooltip formatter={(value) => money(Number(value), currency)} />
        </PieChart>
      </ResponsiveContainer>
    </div>
    <div className="allocation-legend">{groups.map((group, index) => <button type="button" key={group.label} className={selectedGroup === group.label ? "active" : ""} onClick={() => onSelect(group.label)} aria-pressed={selectedGroup === group.label}><span style={{ background: pieColors[index % pieColors.length] }} /><strong>{group.label}</strong><b>{percent(group.weight)}</b><em>{percent(group.returnPercent)}</em></button>)}</div>
  </div>;
}
function AllocationHoldingList({ group, currency, dimensionLabel, onClose }: { group: AllocationGroup; currency: string; dimensionLabel: string; onClose: () => void }) {
  return <div className="allocation-holdings">
    <div className="card-heading">
      <div><p className="eyebrow">{dimensionLabel} holdings</p><h3>{group.label}</h3></div>
      <div className="card-tools"><span>{percent(group.returnPercent)} return</span><button type="button" onClick={onClose}>Close</button></div>
    </div>
    <div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Name</th><th>Value</th><th>Weight</th><th>Return</th><th>Gain</th></tr></thead><tbody>{group.positions.map((item) => <tr key={`${item.asset_id}-${item.allocation_market_value}`}><td><strong>{item.symbol}</strong></td><td>{item.name ?? item.asset_type ?? "Asset"}</td><td>{money(item.allocation_market_value, currency)}</td><td>{percent(item.allocation_weight)}</td><td>{percent(item.total_return_percent)}</td><td className={(item.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money((item.unrealized_gain ?? 0) * item.allocation_share, currency)}</td></tr>)}</tbody></table></div>
  </div>;
}
type AllocationGroup = { label: string; marketValue: number; bookCost: number; unrealizedGain: number; count: number; weight: number; returnPercent: number | null; positions: AllocationHolding[] };
type AllocationHolding = Position & { allocation_market_value: number; allocation_weight: number; allocation_share: number };
function groupPositions(positions: Position[], dimension: ExposureDimension): AllocationGroup[] {
  const total = positions.reduce((sum, item) => sum + (item.market_value ?? 0), 0);
  const grouped = new Map<string, { label: string; marketValue: number; bookCost: number; unrealizedGain: number; count: number; positions: AllocationHolding[] }>();
  positions.forEach((item) => {
    exposureSplits(item, dimension).forEach(({ label, share }) => {
      const current = grouped.get(label) ?? { label, marketValue: 0, bookCost: 0, unrealizedGain: 0, count: 0, positions: [] };
      const marketValue = (item.market_value ?? 0) * share;
      const bookCost = (item.book_cost ?? 0) * share;
      const gain = (item.unrealized_gain ?? 0) * share;
      current.marketValue += marketValue;
      current.bookCost += bookCost;
      current.unrealizedGain += gain;
      current.count += 1;
      current.positions.push({ ...item, allocation_market_value: marketValue, allocation_weight: total ? marketValue / total : 0, allocation_share: share });
      grouped.set(label, current);
    });
  });
  return Array.from(grouped.values())
    .map((item) => ({ ...item, weight: total ? item.marketValue / total : 0, returnPercent: item.bookCost ? item.unrealizedGain / item.bookCost : null, positions: item.positions.sort((a, b) => b.allocation_market_value - a.allocation_market_value) }))
    .sort((a, b) => b.marketValue - a.marketValue);
}

function exposureSplits(position: Position, dimension: ExposureDimension): { label: string; share: number }[] {
  const map = dimension === "sector"
    ? position.sector_exposure
    : dimension === "industry"
      ? position.industry_exposure
      : dimension === "country"
        ? position.country_exposure
        : dimension === "currency"
          ? position.currency_exposure
          : undefined;
  if (map && Object.keys(map).length) {
    return Object.entries(map)
      .filter(([, share]) => share > 0)
      .map(([label, share]) => ({ label: label.trim() || trancheLabels[dimension], share }));
  }
  const raw = dimension === "asset_class" ? position.allocation_class : dimension === "asset_type" ? position.asset_type : position[dimension];
  return [{ label: raw?.trim() || trancheLabels[dimension], share: 1 }];
}
