import { Component, useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bell,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleDollarSign,
  Database,
  ExternalLink,
  Info,
  KeyRound,
  LayoutDashboard,
  Menu,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  WalletCards,
  X,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useLocation, useParams, useSearchParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BenchmarkDetailPage, BenchmarksWorkspacePage } from "./benchmarks";
import {
  api,
  type AssetActivity,
  type AssetHolding,
  type AssetSearchResult,
  type BenchmarkAssociation,
  type BenchmarkDefaultResponse,
  type ComparisonAsset,
  type SectorComparisonContext,
  type IngestionReadiness,
  type IngestionBackgroundStatus,
  type OptimizationPreview,
  type Portfolio,
  type PortfolioFundamentals,
  type PortfolioPerformance,
  type PortfolioRisk,
  type Position,
  type SignalDetailResponse,
  type SignalRow,
  type StockRankingReadiness,
} from "./api";

const percent = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
const number = (value: number | null | undefined, digits = 2) =>
  value == null ? "Unavailable" : value.toFixed(digits);
const signedNumber = (value: number | null | undefined, digits = 1) =>
  value == null ? "Unavailable" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
const cleanCurrency = (value: string | null | undefined, fallback = "CAD") => {
  if (!value) return fallback;
  const direct = value.trim().toUpperCase();
  if (/^[A-Z]{3}$/.test(direct)) return direct;
  const match = direct.match(/['"]?CODE['"]?\s*:\s*['"]?([A-Z]{3})['"]?/);
  return match?.[1] ?? fallback;
};
const formatMoney = (value: number | null | undefined, currency = "CAD") =>
  value == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-CA", {
      style: "currency",
      currency: cleanCurrency(currency),
      maximumFractionDigits: 0,
    }).format(value);
const money = formatMoney;
type ThemeMode = "light" | "dark";
type MoverDefault = "8" | "all";
type StockRankingFactor = "aggregate" | "share_price_momentum" | "news_sentiment" | "retail_sentiment" | "earnings_momentum" | "institutional_buying";
type StockRankingUniverse = "tracked" | "all";
type AppNotification = { id: number; tone: "success" | "error"; message: string };
type HelpItem = { term: string; detail: string };
type AppSettings = {
  theme: ThemeMode;
  moverDefault: MoverDefault;
  density: "comfortable" | "compact";
  featureColor: boolean;
};
const defaultAppSettings: AppSettings = {
  theme: "light",
  moverDefault: "8",
  density: "comfortable",
  featureColor: true,
};
const stockRankingFactors: { value: StockRankingFactor; label: string }[] = [
  { value: "aggregate", label: "Aggregate" },
  { value: "share_price_momentum", label: "Price" },
  { value: "news_sentiment", label: "News" },
  { value: "retail_sentiment", label: "Retail" },
  { value: "earnings_momentum", label: "Earnings" },
  { value: "institutional_buying", label: "Institutions" },
];
const compareHelp: HelpItem[] = [
  { term: "P/E and price/sales", detail: "Simple valuation ratios. Lower can mean cheaper, but only if the business quality and growth are comparable." },
  { term: "Vs history/sector/industry", detail: "Shows whether the company looks expensive or cheap versus its own past and similar companies." },
  { term: "Returns", detail: "Short and long period price movement. Good for context, but one period should not decide the investment case." },
  { term: "Spread", detail: "The gap between the left and right ticker. It helps show which company is stronger on a given metric." },
];
const portfolioAnalyticsHelp: HelpItem[] = [
  { term: "Modified Dietz", detail: "A portfolio return estimate that adjusts for deposits and withdrawals, so cash movement does not distort performance as much." },
  { term: "Sharpe and Sortino", detail: "Risk-adjusted return scores. Higher is generally better; Sortino focuses more on harmful downside moves." },
  { term: "Max drawdown", detail: "The largest peak-to-trough loss in the period. It is a plain stress measure: how deep the worst slump was." },
  { term: "Monte Carlo", detail: "A probability simulation that creates many possible paths using expected return and volatility. Treat it as a range of outcomes, not a prediction." },
  { term: "Margin of safety", detail: "How far estimated fair value sits above the current price. Bigger positive margins imply more valuation cushion." },
];
const assetAnalyticsHelp: HelpItem[] = [
  { term: "Beta", detail: "How sensitive the stock is to the benchmark. A beta above 1 usually moves more than the market; below 1 usually moves less." },
  { term: "DCF", detail: "Discounted cash flow. It estimates fair value from future cash the company may produce, discounted back to today." },
  { term: "DDM", detail: "Dividend discount model. It estimates fair value from future dividends, so it matters most for dividend-paying companies." },
  { term: "Forecast band", detail: "A range of simulated outcomes. The 10th percentile is a rough bear case, the 90th percentile a rough bull case." },
  { term: "Quality", detail: "Profitability and balance-sheet clues, such as margins, return on equity, and debt/equity." },
];
const dataReadinessHelp: HelpItem[] = [
  { term: "Ready", detail: "The model has enough inputs to produce that section's analytics." },
  { term: "Missing inputs", detail: "Data the model wanted but could not find, such as price history, fundamentals, cash flow, or dividend data." },
  { term: "Weak", detail: "Some useful data exists, but the output may be thinner or less reliable than a fully populated model." },
];
const ingestionHelp: HelpItem[] = [
  { term: "Routine ingestion", detail: "Scheduled data refresh work that keeps prices, fundamentals, benchmarks, and analytics inputs current." },
  { term: "Projection readiness", detail: "A checklist showing whether held assets have enough data for projections and valuation models." },
  { term: "Manual controls", detail: "Explicit refresh actions for backfills, retries, and provider-sensitive jobs. These can change local data." },
];
const loadAppSettings = (): AppSettings => {
  try {
    const raw = window.localStorage.getItem("quaint_dash_app_settings");
    if (!raw) return defaultAppSettings;
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return { ...defaultAppSettings, ...parsed };
  } catch {
    return defaultAppSettings;
  }
};
const friendlyBrokerError = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  const lower = message.toLowerCase();
  if (lower.includes("personal keys") && lower.includes("one user")) {
    return "This SnapTrade app already has a test user. Open Advanced and save the existing SnapTrade user ID and secret, then open the portal.";
  }
  if (lower.includes("no snaptrade user found")) {
    return "Create a profile first, or use Advanced if you already have SnapTrade user credentials.";
  }
  if (lower.includes("payment required")) {
    return "SnapTrade rejected the request for this app. Check the SnapTrade app status and keys, then try again.";
  }
  return message;
};
const actionErrorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [settings, setSettings] = useState<AppSettings>(loadAppSettings);
  const [notification, setNotification] = useState<AppNotification | null>(null);
  const location = useLocation();
  const notify = (message: string, tone: AppNotification["tone"] = "success") => {
    setNotification({ id: Date.now(), tone, message });
  };
  const updateSettings = (next: Partial<AppSettings>) => {
    setSettings((current) => {
      const updated = { ...current, ...next };
      window.localStorage.setItem("quaint_dash_app_settings", JSON.stringify(updated));
      return updated;
    });
  };
  useEffect(() => {
    document.documentElement.dataset.theme = settings.theme;
  }, [settings.theme]);
  return (
    <div className={`app-shell ${settings.density === "compact" ? "density-compact" : ""} ${settings.featureColor ? "" : "feature-muted"}`}>
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand"><ChartNoAxesCombined size={21} /><span>Quaint Dash</span></div>
        <button className="mobile-close" onClick={() => setMenuOpen(false)}><X /></button>
        <nav>
          <NavLink to="/" end><LayoutDashboard />Overview</NavLink>
          <NavLink to="/portfolios"><WalletCards />Portfolios</NavLink>
          <NavLink to="/signals"><Activity />Signals</NavLink>
          <NavLink to="/compare"><BarChart3 />Compare</NavLink>
          <NavLink to="/benchmarks"><Search />Benchmarks</NavLink>
          <NavLink to="/brokers"><Building2 />Brokers</NavLink>
          <NavLink to="/operations"><Database />Operations</NavLink>
          <NavLink to="/settings"><Settings />Settings</NavLink>
        </nav>
        <div className="sidebar-note"><span className="status-dot" />Local API connected</div>
      </aside>
      <main>
        <header>
          <button className="mobile-menu" onClick={() => setMenuOpen(true)}><Menu /></button>
          <div><p className="eyebrow">Personal finance workspace</p><strong>Investment dashboard</strong></div>
          <div className="avatar">CP</div>
        </header>
        <RouteErrorBoundary key={location.pathname}>
          <Routes>
            <Route path="/" element={<OverviewPage moverDefault={settings.moverDefault} />} />
            <Route path="/portfolios" element={<PortfolioWorkspacePage />} />
            <Route path="/portfolios/:portfolioId" element={<PortfolioDetailPage />} />
            <Route path="/signals" element={<StockRankingsPage notify={notify} />} />
            <Route path="/signals/:signalId" element={<SignalDetailPage notify={notify} />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/benchmarks" element={<BenchmarksWorkspacePage notify={notify} />} />
            <Route path="/benchmarks/:benchmarkId" element={<BenchmarkDetailPage notify={notify} />} />
            <Route path="/assets/:assetId" element={<AssetDetailPage notify={notify} />} />
            <Route path="/asset/:assetId" element={<AssetDetailPage notify={notify} />} />
            <Route path="/brokers" element={<BrokersPage notify={notify} />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/settings" element={<SettingsPage settings={settings} onChange={updateSettings} />} />
          </Routes>
        </RouteErrorBoundary>
        <ActionNotification notification={notification} onClose={() => setNotification(null)} />
      </main>
    </div>
  );
}

function ActionNotification({ notification, onClose }: { notification: AppNotification | null; onClose: () => void }) {
  useEffect(() => {
    if (!notification) return undefined;
    const timer = window.setTimeout(onClose, 3600);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  if (!notification) return null;
  return (
    <div className={`action-toast ${notification.tone}`} role="status" aria-live="polite">
      {notification.tone === "success" ? <CheckCircle2 size={18} /> : <X size={18} />}
      <span>{notification.message}</span>
      <button aria-label="Dismiss notification" onClick={onClose}><X size={14} /></button>
    </div>
  );
}

function HelpDisclosure({ title, items, note }: { title: string; items: HelpItem[]; note?: string }) {
  return (
    <details className="info-popover">
      <summary aria-label={`Explain ${title}`}>
        <Info size={15} />
      </summary>
      <div className="info-panel">
        <strong>{title}</strong>
        <dl>
          {items.map((item) => (
            <div key={item.term}>
              <dt>{item.term}</dt>
              <dd>{item.detail}</dd>
            </div>
          ))}
        </dl>
        {note ? <p>{note}</p> : null}
      </div>
    </details>
  );
}

class RouteErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <div className="page"><ErrorPanel error={this.state.error} /></div>;
    }
    return this.props.children;
  }
}

function OverviewPage({ moverDefault }: { moverDefault: MoverDefault }) {
  const [showAllMovers, setShowAllMovers] = useState(moverDefault === "all");
  const updates = useQuery({ queryKey: ["overview-updates"], queryFn: api.overviewUpdates });
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const brokers = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const jobs = useQuery({ queryKey: ["jobs", "failed", ""], queryFn: () => api.ingestionJobs("failed") });
  const portfolioCount = portfolios.data?.length ?? 0;
  const mappedAccounts = brokers.data?.filter((account) => account.portfolio_id != null).length ?? 0;
  const failedJobs = jobs.data?.length ?? 0;
  const openAccounts = brokers.data?.length ?? 0;
  const topMover = updates.data?.price_movers[0];
  const movers = updates.data?.price_movers ?? [];
  const visibleMovers = showAllMovers ? movers : movers.slice(0, 8);

  useEffect(() => {
    setShowAllMovers(moverDefault === "all");
  }, [moverDefault]);

  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Today at a glance</p><h1>Overview</h1><p className="page-subtitle">A compact status screen for account coverage, tracked value, recent movement, and anything that needs attention.</p></div>
      <div className="actions"><Link className="button-link" to="/signals"><Activity size={17}/>Review signals</Link><Link className="button-link primary" to="/portfolios"><WalletCards size={17}/>Open portfolios</Link></div>
    </div>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Total market value" value={money(updates.data?.total_market_value)} />
      <Metric icon={<Activity />} label="Active holdings" value={String(updates.data?.position_count ?? 0)} />
      <Metric icon={<WalletCards />} label="Portfolios" value={String(portfolioCount)} />
      <Metric icon={<Building2 />} label="Broker accounts" value={`${mappedAccounts}/${openAccounts}`} detail="mapped" positive={Boolean(mappedAccounts)} />
      <Metric icon={<Database />} label="Attention items" value={String(failedJobs)} detail={failedJobs ? "failed jobs" : "data healthy"} positive={!failedJobs} />
    </section>
    <section className="overview-focus-grid">
      <section className="card overview-primary">
        <div className="card-heading">
          <div><p className="eyebrow">Largest move</p><h2>{topMover?.symbol ?? "Waiting for prices"}</h2></div>
          <span>{topMover ? percent(topMover.change_percent) : "no data"}</span>
        </div>
        <div className="overview-hero-value">
          <strong>{topMover ? money(topMover.change) : "No movement yet"}</strong>
          <p>{topMover ? `${topMover.name ?? topMover.asset_id} represents ${percent(topMover.weight)} of tracked holdings.` : "Once held assets have at least two prices, this panel shows the most important daily movement."}</p>
          {topMover ? <Link className="portal-link" to={`/asset/${topMover.asset_id}`}>Open asset detail</Link> : <Link className="portal-link" to="/operations">Refresh market data</Link>}
        </div>
      </section>
      <section className="card overview-primary">
        <div className="card-heading"><div><p className="eyebrow">Next action</p><h2>{failedJobs ? "Fix failed data jobs" : mappedAccounts ? "Review portfolio exposure" : "Connect a broker account"}</h2></div><span>{failedJobs ? `${failedJobs} failed` : `${mappedAccounts} mapped`}</span></div>
        <div className="overview-hero-value">
          <strong>{failedJobs ? "Data attention" : mappedAccounts ? "Portfolio review" : "Broker setup"}</strong>
          <p>{failedJobs ? "Operations has the failed job list and retry controls." : mappedAccounts ? "Portfolios contains holdings, exposure, analytics, and account mapping views." : "Broker setup stays in the broker workspace so account connection steps are not mixed into overview."}</p>
          <Link className="portal-link" to={failedJobs ? "/operations" : mappedAccounts ? "/portfolios" : "/brokers"}>{failedJobs ? "Open operations" : mappedAccounts ? "Open portfolio workspace" : "Start broker setup"}</Link>
        </div>
      </section>
    </section>
    <section className="update-grid">
      <section className="card">
        <div className="card-heading">
          <div><p className="eyebrow">Price movers</p><h2>Holdings moving most</h2></div>
          <div className="card-tools">
            <span>{updates.data?.mover_count ?? 0} tracked</span>
            {movers.length > 8 ? <button onClick={() => setShowAllMovers((value) => !value)}>{showAllMovers ? "Show 8" : "See all"}</button> : null}
          </div>
        </div>
        {updates.isLoading ? <Loading compact /> : movers.length ? <div className="mover-list">{visibleMovers.map((item) => <Link to={`/asset/${item.asset_id}`} className="mover-row" key={item.asset_id}><div className="mover-asset"><strong>{item.symbol}</strong><span>{item.name ?? "Held asset"}</span></div><b className={(item.change_percent ?? 0) >= 0 ? "positive" : "negative"}>{percent(item.change_percent)}</b><span>{money(item.market_value)}</span></Link>)}</div> : <EmptyRow text="No price movers yet. Add price history for held assets to light this up." />}
      </section>
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Market notes</p><h2>News affecting holdings</h2></div><span>{updates.data?.news_count ?? 0} items</span></div>
        {updates.isLoading ? <Loading compact /> : updates.data?.news.length ? <div className="news-list">{updates.data.news.map((item, index) => <a href={item.url ?? undefined} target="_blank" rel="noreferrer" className="news-row" key={`${item.title}-${index}`}><div><strong>{item.title}</strong><span>{[item.symbol, item.provider, item.published_at ? new Date(item.published_at).toLocaleDateString() : null].filter(Boolean).join(" - ")}</span></div></a>)}</div> : <EmptyRow text="No local news found yet. Run sentiment/news ingestion to populate this panel." />}
      </section>
    </section>
  </div>;
}

function StockRankingsPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [expandedId, setExpandedId] = useState<string | null>(params.get("signal"));
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const filters = signalFiltersFromParams(params);
  const signals = useQuery({
    queryKey: ["signals", filters],
    queryFn: () => api.signals(filters),
    placeholderData: (previous) => previous,
  });
  const detail = useQuery({
    queryKey: ["signal-detail", expandedId],
    queryFn: () => api.signalDetail(expandedId ?? ""),
    enabled: Boolean(expandedId),
  });
  const markReviewed = useMutation({
    mutationFn: (signalId: string) => api.updateSignalUserState(signalId, { reviewed: true }),
    onSuccess: () => {
      notify("Signal marked reviewed.");
      client.invalidateQueries({ queryKey: ["signals"] });
      if (expandedId) client.invalidateQueries({ queryKey: ["signal-detail", expandedId] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const addWatchlist = useMutation({
    mutationFn: (assetId: string) => api.addWatchlistAsset(assetId),
    onSuccess: (result) => {
      notify(`${result.symbol} added to watchlist.`);
      client.invalidateQueries({ queryKey: ["signals"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const createAlert = useMutation({
    mutationFn: (signalId: string) => api.createSignalAlert(signalId, { condition: "status_active", channel: "in_app" }),
    onSuccess: () => {
      notify("Alert rule created.");
      if (expandedId) client.invalidateQueries({ queryKey: ["signal-detail", expandedId] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  };
  const applyMetric = (metric: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(metric).forEach(([key, value]) => next.set(key, value));
    next.delete("offset");
    setParams(next);
  };
  const openSignal = (signalId: string) => {
    setExpandedId(signalId);
    const next = new URLSearchParams(params);
    next.set("signal", signalId);
    setParams(next);
  };
  const closeSignal = () => {
    setExpandedId(null);
    const next = new URLSearchParams(params);
    next.delete("signal");
    setParams(next);
  };
  useEffect(() => {
    document.title = "Signals - Quaint Dash";
  }, []);
  return <div className="page">
    <div className="page-title signals-title">
      <div>
        <p className="eyebrow">Decision support</p>
        <h1>Signals</h1>
        <p className="page-subtitle">Meaningful changes in stored market, sentiment, earnings, and portfolio data. Each signal separates strength, confidence, and portfolio priority so evidence is visible before action.</p>
        <div className="signals-meta" aria-live="polite">
          <span>Market status: local close-based data</span>
          <span>Computed: {formatDateTime(signals.data?.last_successful_computation_at)}</span>
          <span>Data as of: {formatDateTime(signals.data?.data_as_of)}</span>
          <span>Model: {signals.data?.model_version ?? "loading"}</span>
        </div>
      </div>
      <div className="actions">
        <button onClick={() => signals.refetch()} disabled={signals.isFetching}><RefreshCw size={17} />Refresh</button>
        <button onClick={() => notify("Saved views use URL filters in this local build.")}><Save size={17}/>Saved view</button>
        <a className="button-link" href="#signal-methodology"><Info size={17}/>Methodology</a>
      </div>
    </div>
    <section className="signal-summary-strip" aria-label="Signal summary">
      {signals.isLoading ? Array.from({ length: 6 }).map((_item, index) => <div className="signal-summary-tile skeleton" key={index} />) : signals.data?.metrics.map((metric) => (
        <button key={metric.key} className="signal-summary-tile" onClick={() => applyMetric(metric.filter_params)}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </button>
      ))}
    </section>
    {signals.data?.partial_provider_failures.length ? <div className="signal-degraded" role="status">Partial provider coverage: {signals.data.partial_provider_failures.join(", ")}. Valid cached signals remain visible.</div> : null}
    {signals.isError ? <ErrorPanel error={signals.error} /> : null}
    <section className="signal-priority-grid">
      <SignalPrioritySection title="Needs attention" items={signals.data?.needs_attention ?? []} empty="No high-priority risks currently meet the filters." onOpen={openSignal} />
      <SignalPrioritySection title="Top opportunities" items={signals.data?.top_opportunities ?? []} empty="No high-confidence opportunities currently meet the filters." onOpen={openSignal} />
    </section>
    <section className="card signal-explorer">
      <div className="signal-explorer-toolbar">
        <div>
          <p className="eyebrow">Signal explorer</p>
          <h2>{signals.isLoading ? "Loading signals" : `${signals.data?.total ?? 0} matching signals`}</h2>
        </div>
        <button className="mobile-filter-button" onClick={() => setMobileFiltersOpen(true)}><SlidersHorizontal size={17}/>Filters</button>
      </div>
      <SignalFilterPanel filters={filters} updateFilter={updateFilter} mobileOpen={mobileFiltersOpen} onClose={() => setMobileFiltersOpen(false)} />
      <ActiveSignalFilters filters={filters} onClear={(key) => updateFilter(key, "")} onClearAll={() => setParams(new URLSearchParams())} />
      {signals.isLoading ? <SignalTableSkeleton /> : signals.data?.items.length ? (
        <>
          <div className="signal-table-wrap">
            <table className="signal-table">
              <caption className="sr-only">Signals sorted by {filters.sort ?? "portfolio priority"}</caption>
              <thead>
                <tr>
                  {[
                    ["Asset", "ticker"],
                    ["Signal", "priority"],
                    ["Direction", "direction"],
                    ["Strength", "strength"],
                    ["Confidence", "confidence"],
                    ["Trigger", "triggered"],
                    ["Portfolio impact", "portfolio_weight"],
                    ["Age", "triggered"],
                    ["Trend", "score_change"],
                    ["Actions", ""],
                  ].map(([label, sortKey]) => (
                    <th key={label} scope="col">
                      {sortKey ? <button className="sort-header" onClick={() => updateFilter("sort", sortKey)} aria-label={`Sort by ${label}`}>{label}{filters.sort === sortKey ? " desc" : ""}</button> : label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {signals.data.items.map((item) => (
                  <SignalTableRow
                    key={item.signal_id}
                    item={item}
                    expanded={expandedId === item.signal_id}
                    detail={expandedId === item.signal_id ? detail.data : undefined}
                    onOpen={() => openSignal(item.signal_id)}
                    onClose={closeSignal}
                    onReview={() => markReviewed.mutate(item.signal_id)}
                    onAlert={() => createAlert.mutate(item.signal_id)}
                    onWatchlist={() => addWatchlist.mutate(item.asset_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div className="signal-mobile-list">
            {signals.data.items.map((item) => <SignalMobileCard key={item.signal_id} item={item} onOpen={() => openSignal(item.signal_id)} />)}
          </div>
        </>
      ) : <EmptyRow text={Object.keys(filters).length ? "No signals match the selected filters. Clear filters or broaden the confidence and priority thresholds." : "No active signals. Stored ranking inputs are not available for the tracked universe yet."} />}
      {signals.isFetching && !signals.isLoading ? <p className="signal-refreshing" role="status">Refreshing signals while keeping current results visible.</p> : null}
      <p id="signal-methodology" className="signal-methodology">{signals.data?.methodology ?? "Signal methodology loads with the server-side signal response."}</p>
    </section>
  </div>;
}

function signalFiltersFromParams(params: URLSearchParams) {
  const keys = ["q", "portfolio_id", "owned", "category", "direction", "status", "min_strength", "min_confidence", "min_priority", "sector", "industry", "freshness", "completeness", "triggered_after", "triggered_before", "sort", "limit", "offset"];
  return Object.fromEntries(keys.map((key) => [key, params.get(key) ?? undefined]).filter((entry) => entry[1])) as Record<string, string>;
}

function SignalPrioritySection({ title, items, empty, onOpen }: { title: string; items: SignalRow[]; empty: string; onOpen: (id: string) => void }) {
  return <section className="card signal-priority-section">
    <div className="card-heading"><div><p className="eyebrow">Priority</p><h2>{title}</h2></div><span>{items.length}</span></div>
    {items.length ? <div className="signal-priority-list">{items.map((item) => (
      <button key={item.signal_id} onClick={() => onOpen(item.signal_id)} className="signal-priority-item">
        <div><strong>{item.ticker}</strong><span>{item.company_name ?? item.exchange ?? "Tracked asset"}</span></div>
        <p>{item.summary}</p>
        <b>{percent(item.confidence)} confidence</b>
        <span>{percent(item.current_portfolio_weight)} exposure</span>
        <span>{timeAgo(item.first_detected_at)}</span>
      </button>
    ))}</div> : <EmptyRow text={empty} />}
  </section>;
}

function SignalFilterPanel({ filters, updateFilter, mobileOpen, onClose }: { filters: Record<string, string>; updateFilter: (key: string, value: string) => void; mobileOpen: boolean; onClose: () => void }) {
  return <div className={mobileOpen ? "signal-filter-panel open" : "signal-filter-panel"}>
    <div className="signal-filter-heading"><strong>Filters</strong><button onClick={onClose} aria-label="Close filters"><X size={16}/></button></div>
    <label>Search<input value={filters.q ?? ""} onChange={(event) => updateFilter("q", event.target.value)} placeholder="Ticker, company, signal" /></label>
    <label>Portfolio ID<input value={filters.portfolio_id ?? ""} onChange={(event) => updateFilter("portfolio_id", event.target.value)} inputMode="numeric" /></label>
    <label>Owned<select value={filters.owned ?? ""} onChange={(event) => updateFilter("owned", event.target.value)}><option value="">Any</option><option value="owned">Owned</option><option value="unowned">Watchlist/unowned</option></select></label>
    <label>Category<select value={filters.category ?? ""} onChange={(event) => updateFilter("category", event.target.value)}><option value="">Any</option>{["momentum","sentiment","news_event_activity","earnings_revisions","analyst_broker_activity","market_regime","portfolio_concentration","risk","valuation","quality","growth","correlation"].map((item) => <option key={item} value={item}>{labelize(item)}</option>)}</select></label>
    <label>Direction<select value={filters.direction ?? ""} onChange={(event) => updateFilter("direction", event.target.value)}><option value="">Any</option><option value="positive">Positive</option><option value="negative">Negative</option><option value="neutral">Neutral</option></select></label>
    <label>Status<select value={filters.status ?? ""} onChange={(event) => updateFilter("status", event.target.value)}><option value="">Any</option>{["candidate","confirmed","active","weakening","resolved","invalidated","expired","unavailable"].map((item) => <option key={item} value={item}>{labelize(item)}</option>)}</select></label>
    <label>Min strength<select value={filters.min_strength ?? ""} onChange={(event) => updateFilter("min_strength", event.target.value)}><option value="">Any</option><option value="0.35">35%+</option><option value="0.65">65%+</option></select></label>
    <label>Min confidence<select value={filters.min_confidence ?? ""} onChange={(event) => updateFilter("min_confidence", event.target.value)}><option value="">Any</option><option value="0.5">50%+</option><option value="0.7">70%+</option></select></label>
    <label>Min priority<select value={filters.min_priority ?? ""} onChange={(event) => updateFilter("min_priority", event.target.value)}><option value="">Any</option><option value="0.5">50%+</option><option value="0.65">65%+</option></select></label>
    <label>Sector<input value={filters.sector ?? ""} onChange={(event) => updateFilter("sector", event.target.value)} /></label>
    <label>Industry<input value={filters.industry ?? ""} onChange={(event) => updateFilter("industry", event.target.value)} /></label>
    <label>Freshness<select value={filters.freshness ?? ""} onChange={(event) => updateFilter("freshness", event.target.value)}><option value="">Any</option><option value="fresh">Fresh</option><option value="stale">Stale</option></select></label>
    <label>Completeness<select value={filters.completeness ?? ""} onChange={(event) => updateFilter("completeness", event.target.value)}><option value="">Any</option><option value="complete">Complete</option><option value="incomplete">Incomplete</option></select></label>
    <label>Sort<select value={filters.sort ?? "priority"} onChange={(event) => updateFilter("sort", event.target.value)}><option value="priority">Portfolio priority</option><option value="triggered">Most recently triggered</option><option value="strength">Strength</option><option value="confidence">Confidence</option><option value="portfolio_weight">Portfolio weight</option><option value="score_change">Recent score change</option><option value="efficacy">Historical efficacy</option><option value="ticker">Ticker</option><option value="market_cap">Market cap</option></select></label>
  </div>;
}

function ActiveSignalFilters({ filters, onClear, onClearAll }: { filters: Record<string, string>; onClear: (key: string) => void; onClearAll: () => void }) {
  const entries = Object.entries(filters).filter(([key]) => key !== "limit" && key !== "offset" && key !== "signal");
  if (!entries.length) return null;
  return <div className="active-filter-chips" aria-label="Active filters">
    {entries.map(([key, value]) => <button key={key} onClick={() => onClear(key)}>{labelize(key)}: {value}<X size={13}/></button>)}
    <button onClick={onClearAll}>Clear all</button>
  </div>;
}

function SignalTableRow({ item, expanded, detail, onOpen, onClose, onReview, onAlert, onWatchlist }: { item: SignalRow; expanded: boolean; detail?: SignalDetailResponse; onOpen: () => void; onClose: () => void; onReview: () => void; onAlert: () => void; onWatchlist: () => void }) {
  return <>
    <tr className={expanded ? "selected-row" : ""}>
      <td><Link className="asset-link" to={`/asset/${item.asset_id}`}><strong>{item.ticker}</strong><span>{item.company_name ?? item.exchange ?? "Tracked asset"}</span></Link></td>
      <td><button className="link-button signal-name-button" onClick={onOpen}>{item.signal_name}</button><span className="cell-summary">{item.summary}</span></td>
      <td><SignalTone value={item.direction} /></td>
      <td className="numeric">{percent(item.strength)}</td>
      <td className="numeric">{percent(item.confidence)}</td>
      <td>{signedNumber(item.raw_observed_value, 1)} vs {item.trigger_threshold ?? "watch"}</td>
      <td>{item.affected_portfolios.length ? `${item.affected_portfolios.length} portfolio(s), ${percent(item.current_portfolio_weight)}` : "No current holding"}</td>
      <td>{timeAgo(item.first_detected_at)}</td>
      <td>{labelize(item.status)}</td>
      <td><div className="signal-actions"><Link to={`/signals/${encodeURIComponent(item.signal_id)}`}>Details</Link><button onClick={onOpen}>{expanded ? "Hide" : "Evidence"}</button></div></td>
    </tr>
    {expanded ? <tr className="signal-expanded-row"><td colSpan={10}><SignalEvidencePanel item={detail ?? item} onClose={onClose} onReview={onReview} onAlert={onAlert} onWatchlist={onWatchlist} /></td></tr> : null}
  </>;
}

function SignalEvidencePanel({ item, onClose, onReview, onAlert, onWatchlist }: { item: SignalRow | SignalDetailResponse; onClose: () => void; onReview: () => void; onAlert: () => void; onWatchlist: () => void }) {
  return <div className="signal-evidence-panel">
    <div className="signal-evidence-heading">
      <div><strong>{item.ticker}: {item.signal_name}</strong><p>{item.summary}</p></div>
      <button onClick={onClose} aria-label="Close signal evidence"><X size={16}/></button>
    </div>
    <div className="signal-evidence-grid">
      <EvidenceList title="Supporting evidence" items={item.supporting_evidence} />
      <EvidenceList title="Contradicting evidence" items={item.contradicting_evidence} />
      <div className="signal-impact-box"><strong>Portfolio impact</strong>{item.affected_portfolios.length ? item.affected_portfolios.map((impact) => <p key={impact.portfolio_id}>{impact.portfolio_name}: {percent(impact.weight)} weight, {money(impact.market_value, impact.currency)}. {impact.concentration_note}</p>) : <p>No current portfolio holding. Watchlist and compare actions are still available.</p>}</div>
      <div className="signal-impact-box"><strong>Data and methodology</strong><p>Raw value {signedNumber(item.raw_observed_value, 1)}; normalized {number(item.normalized_value, 2)}; threshold {item.trigger_threshold ?? "watch"}. Data as of {formatDateTime(item.data_as_of)} from {item.source}.</p><p>{item.historical_efficacy.warning ?? item.historical_efficacy.label} Sample size: {item.historical_efficacy.sample_size}.</p></div>
    </div>
    <div className="signal-detail-actions">
      <Link to={`/asset/${item.asset_id}`}>Open ticker</Link>
      <Link to={`/compare?left=${item.ticker}`}>Compare asset</Link>
      <Link to="/benchmarks">Benchmarks</Link>
      <button onClick={onWatchlist}><Plus size={14}/>Watchlist</button>
      <button onClick={onReview}><CheckCircle2 size={14}/>Mark reviewed</button>
      <button onClick={onAlert}><Bell size={14}/>Create alert</button>
    </div>
  </div>;
}

function EvidenceList({ title, items }: { title: string; items: { label: string; metric: string; value: number | null; score: number | null; detail: string; source: string }[] }) {
  return <div className="signal-evidence-list"><strong>{title}</strong>{items.length ? items.map((item) => <p key={`${item.label}-${item.metric}`}><b>{item.label}</b><span>{item.metric}: {item.value == null ? "Unavailable" : number(item.value, 2)}; score {item.score == null ? "missing" : signedNumber(item.score, 1)}. {item.detail}</span></p>) : <p>No evidence in this direction.</p>}</div>;
}

function SignalMobileCard({ item, onOpen }: { item: SignalRow; onOpen: () => void }) {
  return <article className="signal-mobile-card">
    <div><strong>{item.ticker}</strong><SignalTone value={item.direction} /></div>
    <h3>{item.signal_name}</h3>
    <p>{item.summary}</p>
    <dl><div><dt>Confidence</dt><dd>{percent(item.confidence)}</dd></div><div><dt>Priority</dt><dd>{percent(item.portfolio_priority)}</dd></div><div><dt>Age</dt><dd>{timeAgo(item.first_detected_at)}</dd></div></dl>
    <button onClick={onOpen}>Inspect evidence</button>
  </article>;
}

function SignalTone({ value }: { value: string }) {
  return <span className={`signal-tone ${value}`}>{labelize(value)}</span>;
}

function SignalTableSkeleton() {
  return <div className="signal-table-skeleton">{Array.from({ length: 6 }).map((_item, index) => <div key={index} className="skeleton-row" />)}</div>;
}

function SignalDetailPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const { signalId = "" } = useParams();
  const decoded = decodeURIComponent(signalId);
  const detail = useQuery({ queryKey: ["signal-detail-page", decoded], queryFn: () => api.signalDetail(decoded), enabled: Boolean(decoded) });
  const createAlert = useMutation({
    mutationFn: () => api.createSignalAlert(decoded, { condition: "status_active", channel: "in_app" }),
    onSuccess: () => notify("Alert rule created."),
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  useEffect(() => {
    document.title = detail.data ? `${detail.data.ticker} signal - Quaint Dash` : "Signal detail - Quaint Dash";
  }, [detail.data]);
  if (detail.isLoading) return <div className="page"><Loading /></div>;
  if (detail.isError) return <div className="page"><ErrorPanel error={detail.error} /></div>;
  if (!detail.data) return <div className="page"><EmptyRow text="Signal not found." /></div>;
  const item = detail.data;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Signal detail</p><h1>{item.ticker} <small>{item.signal_name}</small></h1><p className="page-subtitle">{item.summary}</p></div>
      <div className="actions"><Link className="button-link" to={`/signals?signal=${encodeURIComponent(item.signal_id)}`}>Back to explorer</Link><button className="primary" onClick={() => createAlert.mutate()}><Bell size={17}/>Create alert</button></div>
    </div>
    <section className="card signal-detail-card">
      <SignalEvidencePanel item={item} onClose={() => undefined} onReview={() => notify("Use the explorer row to mark reviewed.")} onAlert={() => createAlert.mutate()} onWatchlist={() => notify("Open the explorer to add watchlist state.")} />
      <div className="signal-detail-grid">
        <div><strong>Lifecycle</strong>{item.lifecycle.map((event) => <p key={`${event.status}-${event.label}`}><b>{event.label}</b><span>{formatDateTime(event.timestamp)} - {event.detail}</span></p>)}</div>
        <div><strong>Strength history</strong>{item.strength_history.map((point) => <p key={point.date}><b>{point.date}</b><span>{percent(point.strength)} strength, {percent(point.confidence)} confidence, raw {signedNumber(point.raw_value, 1)}</span></p>)}</div>
        <div><strong>Related news</strong>{item.related_news.length ? item.related_news.map((news) => <a key={`${news.title}-${news.published_at}`} href={news.url ?? undefined}>{news.title}<span>{formatDateTime(news.published_at)}</span></a>) : <p>No related local news.</p>}</div>
      </div>
    </section>
  </div>;
}
void SignalDetailPage;

function labelize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const dateValue = new Date(value);
  return Number.isNaN(dateValue.getTime()) ? value : dateValue.toLocaleString();
}

function timeAgo(value: string | null | undefined) {
  if (!value) return "No timestamp";
  const dateValue = new Date(value);
  if (Number.isNaN(dateValue.getTime())) return value;
  const days = Math.max(0, Math.round((Date.now() - dateValue.getTime()) / 86400000));
  if (days === 0) return "today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

type PortfolioTopTab = "aggregate" | "portfolios" | "fundamentals";
type PortfolioDetailTab = "overview" | "holdings" | "performance" | "risk" | "optimization" | "fundamentals" | "activity";
type AssetDetailTab = "chart" | "news" | "fundamentals";
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
const assetDetailTabs: { value: AssetDetailTab; label: string }[] = [
  { value: "chart", label: "Chart" },
  { value: "news", label: "News" },
  { value: "fundamentals", label: "Fundamentals" },
];

function PortfolioWorkspacePage() {
  const [params, setParams] = useSearchParams();
  const selected = (params.get("tab") as PortfolioTopTab | null) ?? "aggregate";
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const aggregate = useQuery({ queryKey: ["portfolio-aggregate"], queryFn: api.aggregatePortfolio, enabled: Boolean(portfolios.data?.length) });
  const positions = useQuery({ queryKey: ["positions", "all"], queryFn: api.aggregatePositions, enabled: selected === "aggregate" });
  const firstPortfolioId = portfolios.data?.[0]?.portfolio_id;
  const fundamentals = useQuery({ queryKey: ["portfolio-fundamentals", firstPortfolioId], queryFn: () => api.portfolioFundamentals(firstPortfolioId!), enabled: selected === "fundamentals" && Boolean(firstPortfolioId) });
  const setTab = (tab: PortfolioTopTab) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", tab); return next; });
  if (portfolios.isLoading) return <Loading />;
  if (portfolios.error) return <ErrorPanel error={portfolios.error} />;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Portfolio management</p><h1>Portfolios</h1><p className="page-subtitle">Backend-sourced portfolio totals, holdings, fundamentals, risk, and optimization previews.</p></div>
    </div>
    <TabBar tabs={portfolioTopTabs} selected={selected} onSelect={setTab} label="Portfolio workspace tabs" />
    {selected === "aggregate" ? <AggregateWorkspacePanel aggregate={aggregate.data} positions={positions.data ?? []} isLoading={aggregate.isLoading || positions.isLoading} /> : null}
    {selected === "portfolios" ? <PortfolioCardGrid portfolios={portfolios.data ?? []} /> : null}
    {selected === "fundamentals" ? fundamentals.isLoading ? <Loading /> : fundamentals.data ? <PortfolioFundamentalsView fundamentals={fundamentals.data} /> : <section className="card"><EmptyRow text="No portfolio fundamentals are available yet." /></section> : null}
  </div>;
}

function AggregateWorkspacePanel({ aggregate, positions, isLoading }: { aggregate?: Portfolio; positions: Position[]; isLoading: boolean }) {
  if (isLoading) return <Loading />;
  if (!aggregate) return <section className="card"><EmptyRow text="No portfolios are available yet." /></section>;
  const exposures = groupPositions(positions, "sector");
  return <>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Combined market value" value={money(aggregate.market_value, aggregate.base_ccy)} detail={aggregate.base_ccy} />
      <Metric icon={<ArrowUpRight />} label="Unrealized gain" value={money(aggregate.unrealized_gain, aggregate.base_ccy)} />
      <Metric icon={<Activity />} label="Holdings" value={String(aggregate.position_count)} />
      <Metric icon={<ShieldCheck />} label="Data source" value={aggregate.source ?? "duckdb"} detail={formatTimestamp(aggregate.as_of)} />
    </section>
    <section className="portfolio-layout-grid">
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Exposure</p><h2>Sector allocation</h2></div><span>{positions.length} holdings</span></div>
        {exposures.length ? <div className="tranche-grid">{exposures.map((group) => <article className="tranche" key={group.label}><div><strong>{group.label}</strong><span>{group.count} holdings</span></div><b>{money(group.marketValue, aggregate.base_ccy)}</b><div className="bar"><span style={{ width: `${Math.max(group.weight * 100, 2)}%` }} /></div><em>{percent(group.weight)}</em></article>)}</div> : <EmptyRow text="No exposure metadata is available." />}
      </section>
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Data quality</p><h2>Coverage</h2></div></div>
        <div className="signal-grid">
          <Signal label="Display currency" value={aggregate.display_currency ?? aggregate.base_ccy} />
          <Signal label="Missing FX" value={String(aggregate.fx_missing?.length ?? 0)} />
          <Signal label="Stale prices" value={String(positions.filter((item) => item.stale_price).length)} />
          <Signal label="Unavailable values" value={String(positions.filter((item) => item.market_value == null).length)} />
        </div>
      </section>
    </section>
  </>;
}

function PortfolioCardGrid({ portfolios }: { portfolios: Portfolio[] }) {
  if (!portfolios.length) return <section className="card"><EmptyRow text="No portfolios yet." /></section>;
  return <section className="portfolio-card-grid">
    {portfolios.map((portfolio) => {
      const gainRate = portfolio.book_cost ? (portfolio.unrealized_gain ?? 0) / portfolio.book_cost : null;
      return <Link className="portfolio-link-card" to={`/portfolios/${portfolio.portfolio_id}?tab=overview`} key={portfolio.portfolio_id} aria-label={`Open ${portfolio.name} portfolio`}>
        <div><p className="eyebrow">{portfolio.base_ccy}</p><h2>{portfolio.name}</h2></div>
        <strong>{money(portfolio.market_value, portfolio.base_ccy)}</strong>
        <span>{portfolio.position_count} holdings</span>
        <span className={(portfolio.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money(portfolio.unrealized_gain, portfolio.base_ccy)} {percent(gainRate)}</span>
      </Link>;
    })}
  </section>;
}

function PortfolioDetailPage() {
  const { portfolioId = "" } = useParams();
  const id = Number(portfolioId);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as PortfolioDetailTab | null) ?? "overview";
  const range = params.get("range") ?? "3Y";
  const benchmark = params.get("benchmark") ?? "";
  const setParam = (key: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; });
  const portfolio = useQuery({ queryKey: ["portfolio", id], queryFn: () => api.portfolio(id), enabled: Number.isFinite(id) });
  const positions = useQuery({ queryKey: ["positions", id], queryFn: () => api.positions(id), enabled: Number.isFinite(id) });
  const performance = useQuery({ queryKey: ["portfolio-performance", id, benchmark, range], queryFn: () => api.portfolioPerformance(id, { benchmark: benchmark || undefined, range }), enabled: Number.isFinite(id) });
  const risk = useQuery({ queryKey: ["portfolio-risk", id, benchmark, range], queryFn: () => api.portfolioRisk(id, { benchmark: benchmark || undefined, lookback: range }), enabled: Number.isFinite(id) });
  const fundamentals = useQuery({ queryKey: ["portfolio-fundamentals", id, 5], queryFn: () => api.portfolioFundamentals(id, 5), enabled: Number.isFinite(id) });
  const transactions = useQuery({ queryKey: ["transactions", id, 25, 0], queryFn: () => api.transactions(id, 25, 0), enabled: Number.isFinite(id) && tab === "activity" });
  if (portfolio.isLoading) return <Loading />;
  if (portfolio.error) return <ErrorPanel error={portfolio.error} />;
  if (!portfolio.data) return <section className="card"><EmptyRow text="Portfolio not found." /></section>;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow"><Link to="/portfolios?tab=portfolios">Portfolios</Link> / {portfolio.data.base_ccy}</p><h1>{portfolio.data.name}</h1><p className="page-subtitle">Actual performance, risk, fundamentals, holdings, and optimizer preview from the Python backend.</p></div>
      <div className="overview-actions"><RangeSelector value={range} onChange={(value) => setParam("range", value)} /><input aria-label="Benchmark" value={benchmark} onChange={(event) => setParam("benchmark", event.target.value.toUpperCase())} placeholder="SP500" /></div>
    </div>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Market value" value={money(portfolio.data.market_value, portfolio.data.base_ccy)} />
      <Metric icon={<ArrowUpRight />} label="Historical TWR CAGR" value={percent(performance.data?.actual_twr_cagr)} detail={performance.data?.range} />
      <Metric icon={<Activity />} label="Forward expected CAGR" value={percent(fundamentals.data?.weighted_expected_cagr.value)} detail={`coverage ${percent(fundamentals.data?.weighted_expected_cagr.coverage)}`} />
      <Metric icon={<BarChart3 />} label="Sharpe" value={number(risk.data?.sharpe_ratio)} detail={`rf ${percent(risk.data?.risk_free_rate)}`} />
      <Metric icon={<WalletCards />} label="Holdings" value={String(portfolio.data.position_count)} />
    </section>
    <TabBar tabs={portfolioDetailTabs} selected={tab} onSelect={(value) => setParam("tab", value)} label="Portfolio detail tabs" />
    {tab === "overview" ? <PortfolioOverviewDetail performance={performance.data} risk={risk.data} fundamentals={fundamentals.data} positions={positions.data ?? []} isLoading={performance.isLoading || risk.isLoading || fundamentals.isLoading || positions.isLoading} /> : null}
    {tab === "holdings" ? <HoldingsTable positions={positions.data ?? []} currency={portfolio.data.base_ccy} isLoading={positions.isLoading} portfolioId={id} /> : null}
    {tab === "performance" ? <PortfolioPerformanceView performance={performance.data} isLoading={performance.isLoading} /> : null}
    {tab === "risk" ? <PortfolioRiskView risk={risk.data} isLoading={risk.isLoading} /> : null}
    {tab === "optimization" ? <PortfolioOptimizationPanel portfolioId={id} /> : null}
    {tab === "fundamentals" ? fundamentals.isLoading ? <Loading /> : fundamentals.data ? <PortfolioFundamentalsView fundamentals={fundamentals.data} /> : <section className="card"><EmptyRow text="Portfolio fundamentals are unavailable." /></section> : null}
    {tab === "activity" ? <section className="card"><div className="card-heading"><div><p className="eyebrow">Activity</p><h2>Transactions</h2></div></div>{transactions.isLoading ? <Loading compact /> : transactions.data?.items.length ? <div className="mini-list">{transactions.data.items.map((item) => <article key={item.transaction_id}><div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div><span>{item.asset_id ?? item.currency ?? "cash"}</span><b>{item.cash_amount != null ? money(item.cash_amount, item.currency ?? portfolio.data.base_ccy) : number(item.quantity, 4)}</b></article>)}</div> : <EmptyRow text="No transactions recorded." />}</section> : null}
  </div>;
}

function PortfolioOverviewDetail({ performance, risk, fundamentals, positions, isLoading }: { performance?: PortfolioPerformance; risk?: PortfolioRisk; fundamentals?: PortfolioFundamentals; positions: Position[]; isLoading: boolean }) {
  if (isLoading) return <Loading />;
  return <section className="portfolio-layout-grid">
    <PortfolioPerformanceView performance={performance} isLoading={false} compact />
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Risk</p><h2>Risk and concentration</h2></div></div><div className="signal-grid"><Signal label="Volatility" value={percent(risk?.annualized_volatility)} /><Signal label="Sortino" value={number(risk?.sortino_ratio)} /><Signal label="Beta" value={number(risk?.beta)} /><Signal label="Max drawdown" value={percent(risk?.maximum_drawdown)} /><Signal label="Effective holdings" value={number(risk?.effective_number_of_holdings, 1)} /><Signal label="HHI" value={number(risk?.hhi, 3)} /></div></section>
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Fundamentals</p><h2>Coverage-aware rollup</h2></div></div><div className="signal-grid"><Signal label="Expected CAGR" value={percent(fundamentals?.weighted_expected_cagr.value)} /><Signal label="P/E" value={number(fundamentals?.pe_ratio.value)} /><Signal label="P/FCF" value={number(fundamentals?.price_to_free_cash_flow.value)} /><Signal label="Coverage" value={percent(fundamentals?.weighted_expected_cagr.coverage)} /></div></section>
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Largest holdings</p><h2>Weight drivers</h2></div></div><div className="mini-list">{positions.slice(0, 6).map((item) => <article key={item.asset_id}><div><strong>{item.symbol}</strong><span>{item.name ?? "Asset"}</span></div><b>{percent(item.weight)}</b></article>)}</div></section>
  </section>;
}

function HoldingsTable({ positions, currency, isLoading, portfolioId }: { positions: Position[]; currency: string; isLoading: boolean; portfolioId: number }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"weight" | "symbol" | "gain">("weight");
  const filtered = positions.filter((item) => `${item.symbol} ${item.name ?? ""}`.toLowerCase().includes(query.toLowerCase())).sort((left, right) => sort === "symbol" ? left.symbol.localeCompare(right.symbol) : sort === "gain" ? (right.unrealized_gain ?? -Infinity) - (left.unrealized_gain ?? -Infinity) : (right.weight ?? -Infinity) - (left.weight ?? -Infinity));
  return <section className="card holdings-card"><div className="card-heading"><div><p className="eyebrow">Holdings</p><h2>Positions</h2></div><div className="card-tools"><label>Search<input value={query} onChange={(event) => setQuery(event.target.value)} /></label><label>Sort<select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="weight">Weight</option><option value="symbol">Ticker</option><option value="gain">Gain</option></select></label></div></div>{isLoading ? <Loading compact /> : filtered.length ? <div className="table-wrap"><table><thead><tr><th>Ticker</th><th>Quantity</th><th>Price</th><th>Value</th><th>Weight</th><th>Book</th><th>Gain</th><th>Status</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.asset_id}><td><Link className="asset-link" to={`/assets/${item.asset_id}?from=/portfolios/${portfolioId}%3Ftab%3Dholdings`}><strong>{item.symbol}</strong><span>{item.name ?? item.asset_type ?? "Asset"}</span></Link></td><td>{number(item.quantity, 4)}</td><td>{money(item.latest_price, item.currency)}</td><td>{money(item.market_value, currency)}</td><td>{percent(item.weight)}</td><td>{money(item.book_cost, currency)}</td><td className={(item.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money(item.unrealized_gain, currency)}</td><td>{item.stale_price ? item.stale_reason ?? "stale" : item.data_status ?? "available"}</td></tr>)}</tbody></table></div> : <EmptyRow text="No holdings match this search." />}</section>;
}

function PortfolioPerformanceView({ performance, isLoading, compact = false }: { performance?: PortfolioPerformance; isLoading: boolean; compact?: boolean }) {
  if (isLoading) return <Loading />;
  if (!performance) return <section className="card"><EmptyRow text="Performance is unavailable." /></section>;
  return <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Actual performance</p><h2>Portfolio vs {performance.benchmark ?? "benchmark"}</h2></div><span>{performance.observation_count} observations</span></div><div className="chart" aria-label="Portfolio and benchmark total return chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={performance.points}><XAxis dataKey="date" hide/><YAxis hide domain={["dataMin", "dataMax"]}/><Tooltip/><Area type="monotone" dataKey="portfolio_return_index" name="Portfolio" stroke="#245c4f" fill="#245c4f22" strokeWidth={2}/><Area type="monotone" dataKey="benchmark_return_index" name="Benchmark" stroke="#7b6f5c" fill="#7b6f5c18" strokeWidth={2}/></AreaChart></ResponsiveContainer></div><div className="signal-grid"><Signal label="TWR CAGR" value={percent(performance.actual_twr_cagr)} /><Signal label="Benchmark CAGR" value={percent(performance.benchmark_cagr)} /><Signal label="Excess CAGR" value={percent(performance.excess_cagr)} /><Signal label="Coverage" value={percent(performance.coverage)} /></div>{!compact && performance.missing_inputs.length ? <DataIssueList items={performance.missing_inputs} /> : null}</section>;
}

function PortfolioRiskView({ risk, isLoading }: { risk?: PortfolioRisk; isLoading: boolean }) {
  if (isLoading) return <Loading />;
  if (!risk) return <section className="card"><EmptyRow text="Risk metrics are unavailable." /></section>;
  return <section className="card"><div className="card-heading"><div><p className="eyebrow">Risk definitions</p><h2>Annualized daily-return metrics</h2></div><span>risk-free {percent(risk.risk_free_rate)}</span></div><div className="signal-grid deep"><Signal label="Annualized return" value={percent(risk.annualized_return)} /><Signal label="Annualized volatility" value={percent(risk.annualized_volatility)} /><Signal label="Sharpe" value={number(risk.sharpe_ratio)} /><Signal label="Sortino" value={number(risk.sortino_ratio)} /><Signal label="Beta" value={number(risk.beta)} /><Signal label="Alpha" value={percent(risk.alpha)} /><Signal label="Correlation" value={number(risk.correlation)} /><Signal label="Max drawdown" value={percent(risk.maximum_drawdown)} /><Signal label="Downside deviation" value={percent(risk.downside_deviation)} /><Signal label="Observation count" value={String(risk.observation_count)} /><Signal label="Effective holdings" value={number(risk.effective_number_of_holdings, 1)} /><Signal label="Weight balance score" value={number(risk.weight_balance_score, 1)} /></div><div className="analytics-detail-grid"><AnalyticsBlock title="Sector concentration"><ExposureBars values={risk.sector_concentration} /></AnalyticsBlock><AnalyticsBlock title="Country concentration"><ExposureBars values={risk.geographic_concentration} /></AnalyticsBlock><AnalyticsBlock title="Currency concentration"><ExposureBars values={risk.currency_concentration} /></AnalyticsBlock></div>{risk.missing_inputs.length ? <DataIssueList items={risk.missing_inputs} /> : null}</section>;
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

function AssetDetailPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  void notify;
  const { assetId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as AssetDetailTab | null) ?? "chart";
  const asset = useQuery({ queryKey: ["asset", assetId], queryFn: () => api.asset(assetId) });
  const prices = useQuery({ queryKey: ["prices", assetId, 365], queryFn: () => api.prices(assetId, 365), enabled: tab === "chart" });
  const analytics = useQuery({ queryKey: ["asset-analytics", assetId, ""], queryFn: () => api.assetAnalytics(assetId), enabled: tab === "fundamentals" });
  const activity = useQuery({ queryKey: ["asset-activity", assetId, 10, 0], queryFn: () => api.assetActivity(assetId, 10, 0), enabled: tab === "news" });
  const setTab = (value: AssetDetailTab) => setParams((current) => { const next = new URLSearchParams(current); next.set("tab", value); return next; });
  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorPanel error={asset.error} />;
  return <div className="page"><div className="page-title"><div><p className="eyebrow">{asset.data?.sector ?? "Asset"}</p><h1>{asset.data?.symbol} <small>{asset.data?.name}</small></h1></div><div className="actions"><Link className="button-link" to={params.get("from") ?? "/portfolios"}>Back</Link><Link className="button-link" to={`/compare?left=${asset.data?.asset_id ?? assetId}`}><BarChart3 size={17}/>Compare</Link><strong className="asset-price">{money(asset.data?.latest_price, asset.data?.currency)}</strong></div></div><TabBar tabs={assetDetailTabs} selected={tab} onSelect={setTab} label="Asset detail tabs" />{tab === "chart" ? <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Stored prices</p><h2>Chart</h2></div></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={prices.data}><XAxis dataKey="date" hide/><YAxis hide domain={["dataMin", "dataMax"]}/><Tooltip/><Area type="monotone" dataKey="close" stroke="#245c4f" fill="#245c4f22" strokeWidth={2}/></AreaChart></ResponsiveContainer></div></section> : null}{tab === "news" ? <section className="card"><div className="card-heading"><div><p className="eyebrow">Asset-specific events</p><h2>News and activity</h2></div></div>{activity.isLoading ? <Loading compact /> : activity.data?.items.length ? <div className="mini-list">{activity.data.items.map((item) => <article key={item.provider_transaction_id ?? item.transaction_id ?? item.timestamp}><div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div><span>{item.source}</span><b>{item.portfolio_name ?? item.provider_account_id ?? "local"}</b></article>)}</div> : <EmptyRow text="No asset-specific news feed is available yet; showing stored activity when present." />}</section> : null}{tab === "fundamentals" ? <AssetAnalyticsPanel payload={analytics.data} isLoading={analytics.isLoading} benchmark="" onBenchmarkChange={() => undefined} /> : null}</div>;
}

function TabBar<T extends string>({ tabs, selected, onSelect, label }: { tabs: { value: T; label: string }[]; selected: T; onSelect: (value: T) => void; label: string }) {
  return <div className="tab-bar" role="tablist" aria-label={label}>{tabs.map((tab) => <button key={tab.value} role="tab" aria-selected={selected === tab.value} className={selected === tab.value ? "active" : ""} onClick={() => onSelect(tab.value)}>{tab.label}</button>)}</div>;
}

function RangeSelector({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <div className="segmented-control" aria-label="Performance range">{["1Y", "3Y", "5Y", "10Y", "MAX"].map((item) => <button key={item} className={value.toUpperCase() === item ? "active" : ""} onClick={() => onChange(item)}>{item}</button>)}</div>;
}

function DataIssueList({ items }: { items: string[] }) {
  return <div className="data-issues" role="status">{items.slice(0, 8).map((item) => <p key={item}>{item}</p>)}</div>;
}

function PortfoliosPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const [selectedId, setSelectedId] = useState<number | "all" | null>(() => portfolioSelectionFromParam(params.get("portfolio") ?? window.localStorage.getItem("quaint_dash_portfolio_tab")));
  const [groupBy, setGroupBy] = useState<TrancheDimension>("sector");
  const [newName, setNewName] = useState("");
  const [newBaseCcy, setNewBaseCcy] = useState("CAD");
  const [renameName, setRenameName] = useState("");
  const [transactionLimit, setTransactionLimit] = useState("8");
  const [transactionOffset, setTransactionOffset] = useState(0);
  const isAggregate = selectedId === "all";
  const aggregate = useQuery({
    queryKey: ["portfolio-aggregate"],
    queryFn: api.aggregatePortfolio,
    enabled: isAggregate && Boolean(portfolios.data?.length),
  });
  const selectedPortfolio = portfolios.data?.find((item) => item.portfolio_id === selectedId) ?? portfolios.data?.[0];
  const selected = isAggregate ? aggregate.data : selectedPortfolio;
  const selectedTransactionKey = isAggregate ? "all" : selected?.portfolio_id;
  const selectedRenameName = !isAggregate && selected ? selected.name : "";
  const selectPortfolio = (value: number | "all") => {
    setSelectedId(value);
    window.localStorage.setItem("quaint_dash_portfolio_tab", String(value));
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("portfolio", String(value));
      return next;
    }, { replace: true });
  };
  const positions = useQuery({
    queryKey: ["positions", isAggregate ? "all" : selected?.portfolio_id],
    queryFn: () => isAggregate ? api.aggregatePositions() : api.positions(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const transactions = useQuery({
    queryKey: [
      "transactions",
      selectedTransactionKey,
      transactionLimit,
      transactionOffset,
    ],
    queryFn: () => {
      const limit = boundedInt(transactionLimit, 8, 1, 200);
      return isAggregate
        ? api.aggregateTransactions(limit, transactionOffset)
        : api.transactions(selected!.portfolio_id, limit, transactionOffset);
    },
    enabled: Boolean(selected),
  });
  const analytics = useQuery({
    queryKey: ["portfolio-analytics", selected?.portfolio_id],
    queryFn: () => api.portfolioAnalytics(selected!.portfolio_id),
    enabled: Boolean(selected) && !isAggregate,
  });
  const create = useMutation({
    mutationFn: ({ name, baseCcy }: { name: string; baseCcy: string }) => api.createPortfolio(name, baseCcy),
    onSuccess: (item) => {
      setNewName("");
      client.setQueryData<Portfolio[]>(["portfolios"], (current = []) => [...current.filter((portfolio) => portfolio.portfolio_id !== item.portfolio_id), item]);
      selectPortfolio(item.portfolio_id);
      notify(`${item.name} created.`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const renamePortfolio = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => api.updatePortfolio(id, name),
    onSuccess: (item) => {
      setRenameName(item.name);
      client.setQueryData<Portfolio[]>(["portfolios"], (current = []) =>
        current.map((portfolio) => portfolio.portfolio_id === item.portfolio_id ? item : portfolio)
      );
      notify(`Renamed portfolio to ${item.name}.`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const deletePortfolio = useMutation({
    mutationFn: ({ id }: { id: number; name: string }) => api.deletePortfolio(id),
    onSuccess: (_result, deleted) => {
      client.setQueryData<Portfolio[]>(["portfolios"], (current = []) =>
        current.filter((portfolio) => portfolio.portfolio_id !== deleted.id)
      );
      setSelectedId(null);
      window.localStorage.removeItem("quaint_dash_portfolio_tab");
      setParams((current) => {
        const next = new URLSearchParams(current);
        next.delete("portfolio");
        return next;
      }, { replace: true });
      notify(`${deleted.name} deleted.`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  useEffect(() => {
    setRenameName(selectedRenameName);
  }, [selectedRenameName]);
  useEffect(() => {
    setTransactionOffset(0);
  }, [selectedTransactionKey, transactionLimit]);

  if (portfolios.isLoading) return <Loading />;
  if (portfolios.error) return <ErrorPanel error={portfolios.error} />;
  if (!selected) {
    return (
      <section className="empty-state">
        <WalletCards size={42} />
        <h1>Create your first portfolio</h1>
        <p>Start with a named portfolio, then import transactions through the CLI or a linked broker.</p>
        <form onSubmit={(event) => { event.preventDefault(); create.mutate({ name: newName.trim(), baseCcy: newBaseCcy }); }}>
          <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Long-term investments" />
          <select value={newBaseCcy} onChange={(event) => setNewBaseCcy(event.target.value)} aria-label="Base currency"><option value="CAD">CAD</option><option value="USD">USD</option></select>
          <button className="primary" disabled={!newName.trim()}><Plus size={17} />Create portfolio</button>
        </form>
      </section>
    );
  }
  if (!selected) return <Loading />;

  const gain = selected.unrealized_gain ?? 0;
  const gainRate = selected.book_cost ? gain / selected.book_cost : null;
  const projectionDetail = selected.projected_value_low != null && selected.projected_value_high != null
    ? `${money(selected.projected_value_low, selected.base_ccy)} - ${money(selected.projected_value_high, selected.base_ccy)}`
    : selected.projected_horizon_years
      ? `${selected.projected_horizon_years}y projection`
      : undefined;
  const tranches = groupPositions(positions.data ?? [], groupBy);
  return (
    <div className="page">
      <div className="page-title">
        <div><p className="eyebrow">Portfolio workspace</p><h1>{selected.name}</h1><p className="page-subtitle">Organize one portfolio or all holdings into intuitive tranches by sector, geography, industry, asset type, or currency.</p></div>
        <div className="overview-actions">
          <select value={isAggregate ? "all" : selected.portfolio_id} onChange={(event) => selectPortfolio(event.target.value === "all" ? "all" : Number(event.target.value))}>
            <option value="all">All portfolios</option>
            {portfolios.data?.map((item) => <option key={item.portfolio_id} value={item.portfolio_id}>{item.name}</option>)}
          </select>
          <form className="rename-form" onSubmit={(event) => {
            event.preventDefault();
            if (newName.trim()) {
              create.mutate({ name: newName.trim(), baseCcy: newBaseCcy });
            }
          }}>
            <Plus size={15} />
            <input value={newName} onChange={(event) => setNewName(event.target.value)} aria-label="New portfolio name" placeholder="New portfolio" />
            <select value={newBaseCcy} onChange={(event) => setNewBaseCcy(event.target.value)} aria-label="New portfolio base currency"><option value="CAD">CAD</option><option value="USD">USD</option></select>
            <button className="primary" disabled={!newName.trim() || create.isPending}>Add</button>
          </form>
          {!isAggregate ? (
            <form className="rename-form" onSubmit={(event) => {
              event.preventDefault();
              if (renameName.trim() && renameName.trim() !== selected.name) {
                renamePortfolio.mutate({ id: selected.portfolio_id, name: renameName.trim() });
              }
            }}>
              <Pencil size={15} />
              <input value={renameName} onChange={(event) => setRenameName(event.target.value)} aria-label="Portfolio name" />
              <button className="primary" disabled={!renameName.trim() || renameName.trim() === selected.name || renamePortfolio.isPending}><Save size={15}/>Save</button>
            </form>
          ) : null}
          {!isAggregate ? <button className="danger" disabled={deletePortfolio.isPending} onClick={() => window.confirm(`Delete ${selected.name} from the overview? This removes its local transactions, mappings, and positions.`) && deletePortfolio.mutate({ id: selected.portfolio_id, name: selected.name })}><Trash2 size={16}/>Delete</button> : null}
        </div>
      </div>
      <section className="metric-grid">
        <Metric icon={<CircleDollarSign />} label="Market value" value={money(selected.market_value, selected.base_ccy)} />
        <Metric icon={<ArrowUpRight />} label="Unrealized gain" value={money(gain, selected.base_ccy)} detail={percent(gainRate)} positive={gain >= 0} />
        <Metric icon={<BarChart3 />} label="Projected value" value={money(selected.projected_value, selected.base_ccy)} detail={projectionDetail} />
        <Metric icon={<WalletCards />} label="Book cost" value={money(selected.book_cost, selected.base_ccy)} />
        <Metric icon={<Activity />} label="Active holdings" value={String(selected.position_count)} />
      </section>
      <section className="insight-grid">
        {isAggregate ? <AggregatePanel /> : (
          <AnalyticsPanel
            payload={analytics.data}
            isLoading={analytics.isLoading}
          />
        )}
        <section className="card">
          <div className="card-heading">
            <div><p className="eyebrow">Recent ledger activity</p><h2>Transactions</h2></div>
            <div className="card-tools">
              <label>Rows<select value={transactionLimit} onChange={(event) => setTransactionLimit(event.target.value)}><option value="8">8</option><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label>
              <span>{transactions.data?.total ?? 0} total</span>
            </div>
          </div>
          {transactions.isLoading ? <Loading compact /> : transactions.data?.items.length ? (
            <>
              <div className="mini-list">
                {transactions.data.items.map((item) => (
                  <article key={item.transaction_id}>
                    <div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}{item.fee_amount ? ` - Fee ${money(item.fee_amount, item.currency ?? selected.base_ccy)}` : ""}</span></div>
                    <span>{item.asset_id ?? item.currency ?? "cash"}</span>
                    <b>{item.cash_amount != null ? money(item.cash_amount, item.currency ?? selected.base_ccy) : number(item.quantity, 4)}</b>
                  </article>
                ))}
              </div>
              <Pager
                total={transactions.data.total}
                limit={transactions.data.limit}
                offset={transactions.data.offset}
                onChange={setTransactionOffset}
              />
            </>
          ) : <EmptyRow text="No transactions recorded yet." />}
        </section>
      </section>
      <section className="card tranche-card">
        <div className="card-heading">
          <div><p className="eyebrow">Tranches</p><h2>Organize holdings by exposure</h2></div>
          <label className="tranche-selector">Group by<select value={groupBy} onChange={(event) => setGroupBy(event.target.value as TrancheDimension)}><option value="sector">Sector</option><option value="country">Geography</option><option value="industry">Industry</option><option value="asset_type">Asset type</option><option value="currency">Currency</option></select></label>
        </div>
        {positions.isLoading ? <Loading compact /> : tranches.length ? <div className="tranche-grid">{tranches.map((group) => <article className="tranche" key={group.label}><div><strong>{group.label}</strong><span>{group.count} holding{group.count === 1 ? "" : "s"}</span></div><b>{money(group.marketValue, selected.base_ccy)}</b><div className="bar"><span style={{ width: `${Math.max(group.weight * 100, 2)}%` }} /></div><em>{percent(group.weight)} of selected scope</em></article>)}</div> : <EmptyRow text="No tranche data yet. Add holdings with sector, industry, country, or currency metadata." />}
      </section>
      <section className="card holdings-card">
        <div className="card-heading">
          <div><p className="eyebrow">Composition</p><h2>Holdings</h2></div>
          <span>{positions.data?.length ?? 0} positions</span>
        </div>
        {positions.isLoading ? <Loading compact /> : positions.data?.length ? (
          <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Value</th><th>Weight</th><th>Book cost</th><th>Gain</th></tr></thead>
          <tbody>{positions.data.map((item) => <tr key={item.asset_id}>
            <td><Link className="asset-link" to={`/asset/${item.asset_id}`}><strong>{item.symbol}</strong><span>{item.name ?? item.asset_type ?? "Asset"}</span></Link></td>
            <td>{money(item.market_value, selected.base_ccy)}</td><td>{percent(item.weight)}</td>
            <td>{money(item.book_cost, selected.base_ccy)}</td>
            <td className={(item.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money(item.unrealized_gain, selected.base_ccy)} <span>{percent(item.total_return_percent)}</span></td>
          </tr>)}</tbody></table></div>
        ) : <EmptyRow text="No active positions yet." />}
      </section>
    </div>
  );
}
void PortfoliosPage;

function ComparePage() {
  const [params] = useSearchParams();
  const initialLeft = params.get("left")?.toUpperCase() ?? "NVDA";
  const [left, setLeft] = useState(initialLeft);
  const [right, setRight] = useState(params.get("right")?.toUpperCase() ?? "");
  const [benchmark, setBenchmark] = useState(params.get("benchmark")?.toUpperCase() ?? "");
  const [benchmarkTouched, setBenchmarkTouched] = useState(false);
  const [submitted, setSubmitted] = useState({
    left: initialLeft,
    right: params.get("right")?.toUpperCase() ?? "",
    benchmark: params.get("benchmark")?.toUpperCase() ?? "",
  });
  const leftBenchmarkAssociations = useQuery({
    queryKey: ["asset-benchmark-associations", left.trim().toUpperCase()],
    queryFn: () => api.assetBenchmarkAssociations(left.trim().toUpperCase()),
    enabled: Boolean(left.trim()),
    retry: false,
  });
  const comparison = useQuery({
    queryKey: ["comparison", submitted],
    queryFn: () => api.comparison(submitted.left, submitted.right || undefined, submitted.benchmark || undefined),
    enabled: Boolean(submitted.left.trim()),
  });
  const setBenchmarkFromUser = (value: string) => {
    setBenchmarkTouched(true);
    setBenchmark(value);
  };
  useEffect(() => {
    if (benchmarkTouched || benchmark.trim()) return;
    const core = leftBenchmarkAssociations.data?.associations.find((item) => item.role === "core");
    if (core) setBenchmark(core.benchmark_index_id);
  }, [benchmark, benchmarkTouched, leftBenchmarkAssociations.data]);
  const data = comparison.data;
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Company and benchmark analysis</p><h1>Compare</h1><p className="page-subtitle">Compare two companies, then add benchmark, sector, industry, and historical valuation context from local data.</p></div>
    </div>
    <section className="card compare-control">
      <form onSubmit={(event) => { event.preventDefault(); setSubmitted({ left: left.trim().toUpperCase(), right: right.trim().toUpperCase(), benchmark: benchmark.trim().toUpperCase() }); }}>
        <TickerPicker label="Left ticker" value={left} onChange={(value) => { setLeft(value); setBenchmarkTouched(false); setBenchmark(""); }} />
        <TickerPicker label="Right ticker" value={right} onChange={setRight} />
        <BenchmarkPicker
          value={benchmark}
          onChange={setBenchmarkFromUser}
          associations={leftBenchmarkAssociations.data?.associations}
        />
        <button className="primary" disabled={!left.trim() || comparison.isFetching}><BarChart3 size={17}/>Compare</button>
      </form>
    </section>
    {!submitted.left ? <section className="card"><EmptyRow text="Enter a ticker pair, then compare companies, sector context, industry context, and optional benchmark metrics." /></section> : comparison.error ? <ErrorPanel error={comparison.error} /> : comparison.isLoading ? <Loading /> : data ? <>
      <section className="compare-grid">
        <CompareAssetCard asset={data.left} label="Left" />
        {data.right ? <CompareAssetCard asset={data.right} label="Right" /> : <section className="card"><EmptyRow text="Add a right ticker to compare two companies side by side." /></section>}
      </section>
      <CompareMetricMatrix left={data.left} right={data.right} />
      <section className="compare-grid">
        <CompareSectorContextCard context={data.sector_context} left={data.left} right={data.right} />
        <section className="card">
          <div className="card-heading"><div><p className="eyebrow">Insights</p><h2>Plain English readout</h2></div><span>{data.insights.length} notes</span></div>
          {data.insights.length ? <div className="insight-list">{data.insights.map((item) => <p key={item}>{item}</p>)}</div> : <EmptyRow text="Not enough comparison data yet. Add price history and income statements for richer insights." />}
        </section>
        <section className="card">
          <div className="card-heading"><div><p className="eyebrow">Benchmark</p><h2>{data.benchmark?.name ?? "Optional benchmark"}</h2></div><span>{data.benchmark?.index_id ?? "none"}</span></div>
          {data.benchmark ? <div className="comparison-table">
            <ComparisonRow label="1 day" left={percent(data.left.returns.return_1d)} right={percent(data.benchmark.return_1d)} />
            <ComparisonRow label="21 days" left={percent(data.left.returns.return_21d)} right={percent(data.benchmark.return_21d)} />
            <ComparisonRow label="252 days" left={percent(data.left.returns.return_252d)} right={percent(data.benchmark.return_252d)} />
            <ComparisonRow label="Benchmark vol" left="-" right={percent(data.benchmark.volatility_252d)} />
          </div> : <EmptyRow text="Add a benchmark id like SP500 once benchmark metrics are seeded." />}
        </section>
      </section>
    </> : null}
  </div>;
}

function CompareAssetCard({ asset, label }: { asset: ComparisonAsset; label: string }) {
  return <section className="card compare-card">
    <div className="card-heading">
      <div><p className="eyebrow">{label}</p><h2>{asset.symbol}</h2></div>
      <div className="card-tools"><HelpDisclosure title="Company metric basics" items={compareHelp} /><span>{asset.sector ?? "Unclassified"}</span></div>
    </div>
    <div className="compare-summary">
      <strong>{asset.name ?? asset.asset_id}</strong>
      <span>{[asset.industry, asset.country, asset.currency].filter(Boolean).join(" - ")}</span>
    </div>
    <div className="comparison-table">
      <ComparisonRow label="Latest price" left={money(asset.latest_price, asset.currency)} />
      <ComparisonRow label="Market cap" left={money(asset.market_cap, asset.currency)} />
      <ComparisonRow label="Beta" left={number(asset.market_beta)} />
      <ComparisonRow label="Revenue" left={money(asset.fundamentals.revenue, asset.currency)} />
      <ComparisonRow label="Net income" left={money(asset.fundamentals.net_income, asset.currency)} />
      <ComparisonRow label="EPS" left={ratio(asset.fundamentals.eps)} />
      <ComparisonRow label="P/E" left={ratio(asset.fundamentals.pe_ratio)} />
      <ComparisonRow label="Price/sales" left={ratio(asset.fundamentals.price_to_sales)} />
      <ComparisonRow label="Historical P/E avg" left={ratio(asset.valuation.historical_pe_average)} />
      <ComparisonRow label="Sector P/E avg" left={ratio(asset.valuation.sector_pe_average)} />
      <ComparisonRow label="Industry P/E avg" left={ratio(asset.valuation.industry_pe_average)} />
      <ComparisonRow label="Vs own history" left={gapLabel(asset.valuation.historical_pe_discount, "history")} />
      <ComparisonRow label="Vs sector" left={gapLabel(asset.valuation.sector_pe_premium, "sector")} />
      <ComparisonRow label="Vs industry" left={gapLabel(asset.valuation.industry_pe_premium, "industry")} />
      <ComparisonRow label="1 day return" left={percent(asset.returns.return_1d)} />
      <ComparisonRow label="5 day return" left={percent(asset.returns.return_5d)} />
      <ComparisonRow label="21 day return" left={percent(asset.returns.return_21d)} />
      <ComparisonRow label="252 day return" left={percent(asset.returns.return_252d)} />
    </div>
  </section>;
}

function CompareMetricMatrix({ left, right }: { left: ComparisonAsset; right: ComparisonAsset | null }) {
  const rows = [
    { group: "Market", label: "Latest price", left: money(left.latest_price, left.currency), right: right ? money(right.latest_price, right.currency) : "No peer", delta: valueDelta(left.latest_price, right?.latest_price, "money") },
    { group: "Market", label: "Market cap", left: money(left.market_cap, left.currency), right: right ? money(right.market_cap, right.currency) : "No peer", delta: valueDelta(left.market_cap, right?.market_cap, "money") },
    { group: "Market", label: "Beta", left: number(left.market_beta), right: right ? number(right.market_beta) : "No peer", delta: valueDelta(left.market_beta, right?.market_beta, "number") },
    { group: "Fundamentals", label: "Revenue", left: money(left.fundamentals.revenue, left.currency), right: right ? money(right.fundamentals.revenue, right.currency) : "No peer", delta: valueDelta(left.fundamentals.revenue, right?.fundamentals.revenue, "money") },
    { group: "Fundamentals", label: "Net income", left: money(left.fundamentals.net_income, left.currency), right: right ? money(right.fundamentals.net_income, right.currency) : "No peer", delta: valueDelta(left.fundamentals.net_income, right?.fundamentals.net_income, "money") },
    { group: "Fundamentals", label: "EPS", left: ratio(left.fundamentals.eps), right: right ? ratio(right.fundamentals.eps) : "No peer", delta: valueDelta(left.fundamentals.eps, right?.fundamentals.eps, "number") },
    { group: "Valuation", label: "P/E", left: ratio(left.fundamentals.pe_ratio), right: right ? ratio(right.fundamentals.pe_ratio) : "No peer", delta: valueDelta(left.fundamentals.pe_ratio, right?.fundamentals.pe_ratio, "number") },
    { group: "Valuation", label: "Price/sales", left: ratio(left.fundamentals.price_to_sales), right: right ? ratio(right.fundamentals.price_to_sales) : "No peer", delta: valueDelta(left.fundamentals.price_to_sales, right?.fundamentals.price_to_sales, "number") },
    { group: "Valuation", label: "Vs history", left: gapLabel(left.valuation.historical_pe_discount, "history"), right: right ? gapLabel(right.valuation.historical_pe_discount, "history") : "No peer", delta: percentDelta(left.valuation.historical_pe_discount, right?.valuation.historical_pe_discount) },
    { group: "Valuation", label: "Vs sector", left: gapLabel(left.valuation.sector_pe_premium, "sector"), right: right ? gapLabel(right.valuation.sector_pe_premium, "sector") : "No peer", delta: percentDelta(left.valuation.sector_pe_premium, right?.valuation.sector_pe_premium) },
    { group: "Returns", label: "1 day", left: percent(left.returns.return_1d), right: right ? percent(right.returns.return_1d) : "No peer", delta: percentDelta(left.returns.return_1d, right?.returns.return_1d) },
    { group: "Returns", label: "5 day", left: percent(left.returns.return_5d), right: right ? percent(right.returns.return_5d) : "No peer", delta: percentDelta(left.returns.return_5d, right?.returns.return_5d) },
    { group: "Returns", label: "21 day", left: percent(left.returns.return_21d), right: right ? percent(right.returns.return_21d) : "No peer", delta: percentDelta(left.returns.return_21d, right?.returns.return_21d) },
    { group: "Returns", label: "252 day", left: percent(left.returns.return_252d), right: right ? percent(right.returns.return_252d) : "No peer", delta: percentDelta(left.returns.return_252d, right?.returns.return_252d) },
  ];
  return <section className="card compare-matrix-card">
    <div className="card-heading">
      <div><p className="eyebrow">Company metrics</p><h2>{right ? `${left.symbol} vs ${right.symbol}` : `${left.symbol} full metric view`}</h2></div>
      <div className="card-tools"><HelpDisclosure title="How comparisons work" items={compareHelp} /><span>{right ? "left / right / spread" : "left ticker only"}</span></div>
    </div>
    <div className="comparison-matrix">
      <div className="comparison-matrix-head"><span>Metric</span><strong>{left.symbol}</strong><strong>{right?.symbol ?? "Peer"}</strong><strong>Spread</strong></div>
      {rows.map((row) => <div className="comparison-matrix-row" key={`${row.group}-${row.label}`}>
        <span><em>{row.group}</em>{row.label}</span>
        <b>{row.left}</b>
        <b>{row.right}</b>
        <strong className={row.delta.className}>{row.delta.label}</strong>
      </div>)}
    </div>
  </section>;
}

function CompareSectorContextCard({ context, left, right }: { context: SectorComparisonContext | null; left: ComparisonAsset; right: ComparisonAsset | null }) {
  const diff = (value: number | null | undefined, kind: "money" | "number" | "percent" = "number") => {
    if (value == null) return "Unavailable";
    if (kind === "money") return money(value, left.currency);
    if (kind === "percent") return percent(value);
    return signedNumber(value, 2);
  };
  return <section className="card">
    <div className="card-heading"><div><p className="eyebrow">Sector context</p><h2>{context?.sector ?? left.sector ?? "Unclassified"}</h2></div><span>{context?.benchmark?.index_id ?? "no sector benchmark"}</span></div>
    {context ? <div className="comparison-table">
      <ComparisonRow label="Median P/E" left={ratio(context.median.pe_ratio)} right={`Diff ${diff(context.left_diff_to_median.pe_ratio)}`} />
      <ComparisonRow label="Median price/sales" left={ratio(context.median.price_to_sales)} right={`Diff ${diff(context.left_diff_to_median.price_to_sales)}`} />
      <ComparisonRow label="Median market cap" left={money(context.median.market_cap, left.currency)} right={`Diff ${diff(context.left_diff_to_median.market_cap, "money")}`} />
      <ComparisonRow label="Median beta" left={number(context.median.beta)} right={`Diff ${diff(context.left_diff_to_median.beta)}`} />
      <ComparisonRow label="Median 21d return" left={percent(context.median.return_21d)} right={`Diff ${diff(context.left_diff_to_median.return_21d, "percent")}`} />
      {right && context.right_diff_to_median ? <ComparisonRow label={`${right.symbol} 21d diff`} left={diff(context.right_diff_to_median.return_21d, "percent")} /> : null}
      <ComparisonRow label="Sector benchmark 21d" left={percent(context.benchmark?.return_21d)} right={context.benchmark?.name ?? "Unavailable"} />
      <ComparisonRow label="Sector benchmark 252d" left={percent(context.benchmark?.return_252d)} right={percent(context.benchmark?.volatility_252d)} />
    </div> : <EmptyRow text="Add sector classification and same-sector peers to show sector median context." />}
  </section>;
}

function ComparisonRow({ label, left, right }: { label: string; left: string; right?: string }) {
  return <div className="comparison-row"><span>{label}</span><strong>{left}</strong>{right != null ? <b>{right}</b> : null}</div>;
}

function SettingsPage({ settings, onChange }: { settings: AppSettings; onChange: (next: Partial<AppSettings>) => void }) {
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Workspace preferences</p><h1>Settings</h1><p className="page-subtitle">Control visual tone, default list behavior, and compactness for repeated dashboard work.</p></div>
    </div>
    <section className="settings-grid">
      <article className="card settings-card">
        <div><p className="eyebrow">Appearance</p><h2>Theme</h2></div>
        <div className="segmented-control" role="group" aria-label="Theme">
          <button className={settings.theme === "light" ? "selected" : ""} onClick={() => onChange({ theme: "light" })}>Light</button>
          <button className={settings.theme === "dark" ? "selected" : ""} onClick={() => onChange({ theme: "dark" })}>Dark</button>
        </div>
        <p>Both themes stay monochrome: the light theme is gray-first, and the dark theme leans black and charcoal.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Overview</p><h2>Movers list</h2></div>
        <label className="setting-row"><span>Default holdings shown</span><select value={settings.moverDefault} onChange={(event) => onChange({ moverDefault: event.target.value as MoverDefault })}><option value="8">8 holdings</option><option value="all">All holdings</option></select></label>
        <p>The Overview page always allows switching between the compact eight-row view and the full mover list.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Data surfaces</p><h2>Density</h2></div>
        <div className="segmented-control" role="group" aria-label="Density">
          <button className={settings.density === "comfortable" ? "selected" : ""} onClick={() => onChange({ density: "comfortable" })}>Comfortable</button>
          <button className={settings.density === "compact" ? "selected" : ""} onClick={() => onChange({ density: "compact" })}>Compact</button>
        </div>
        <p>Compact mode trims repeated table and card spacing without changing the information shown.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Feature color</p><h2>Accents</h2></div>
        <label className="toggle-row"><input type="checkbox" checked={settings.featureColor} onChange={(event) => onChange({ featureColor: event.target.checked })} /><span>Use color for feature icons and semantic states</span></label>
        <p>Turn this off for a stricter monochrome workspace. Warnings and losses remain visually distinct through contrast.</p>
      </article>
    </section>
  </div>;
}
const ratio = (value: number | null | undefined) => value == null ? "Unavailable" : value.toFixed(2);
const valueDelta = (left: number | null | undefined, right: number | null | undefined, format: "money" | "number") => {
  if (left == null || right == null) return { label: "Unavailable", className: "" };
  const delta = left - right;
  const label = format === "money" ? money(delta) : number(delta);
  return { label, className: delta >= 0 ? "positive" : "negative" };
};
const percentDelta = (left: number | null | undefined, right: number | null | undefined) => {
  if (left == null || right == null) return { label: "Unavailable", className: "" };
  const delta = left - right;
  return { label: percent(delta), className: delta >= 0 ? "positive" : "negative" };
};
const gapLabel = (value: number | null | undefined, label: string) => {
  if (value == null) return "Unavailable";
  const direction = value >= 0 ? "above" : "below";
  return `${percent(Math.abs(value))} ${direction} ${label}`;
};
const valuationMixLabel = (valuation: AnyRecord) => {
  const undervalued = num(valuation?.undervalued_weight);
  const fair = num(valuation?.fair_value_weight);
  const overvalued = num(valuation?.overvalued_weight);
  const total = (undervalued ?? 0) + (fair ?? 0) + (overvalued ?? 0);
  if (!total) return "Needs DCF inputs";
  return `${percent(undervalued)} under / ${percent(fair)} fair / ${percent(overvalued)} over`;
};

type TrancheDimension = "sector" | "country" | "industry" | "asset_type" | "currency";
const trancheLabels: Record<TrancheDimension, string> = {
  sector: "Unclassified sector",
  country: "Unclassified geography",
  industry: "Unclassified industry",
  asset_type: "Unclassified type",
  currency: "Unknown currency",
};
function groupPositions(positions: Position[], dimension: TrancheDimension) {
  const total = positions.reduce((sum, item) => sum + (item.market_value ?? 0), 0);
  const grouped = new Map<string, { label: string; marketValue: number; count: number }>();
  positions.forEach((item) => {
    const raw = dimension === "asset_type" ? item.asset_type : item[dimension];
    const label = raw?.trim() || trancheLabels[dimension];
    const current = grouped.get(label) ?? { label, marketValue: 0, count: 0 };
    current.marketValue += item.market_value ?? 0;
    current.count += 1;
    grouped.set(label, current);
  });
  return Array.from(grouped.values())
    .map((item) => ({ ...item, weight: total ? item.marketValue / total : 0 }))
    .sort((a, b) => b.marketValue - a.marketValue);
}

function TickerPicker({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState("");
  const query = search.trim() || value.trim();
  const assets = useQuery({
    queryKey: ["asset-picker", query],
    queryFn: () => api.assets(query, 8),
    enabled: Boolean(query),
  });
  const selectAsset = (asset: AssetSearchResult) => {
    onChange(asset.asset_id);
    setSearch("");
  };
  return <div className="ticker-picker">
    <label>{label}<input value={value} onChange={(event) => onChange(event.target.value.toUpperCase())} placeholder="NVDA" /></label>
    <label>Find ticker<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search assets" /></label>
    {assets.data?.length ? <div className="ticker-picker-results">
      {assets.data.slice(0, 5).map((item) => (
        <button type="button" key={item.asset_id} onClick={() => selectAsset(item)}>
          <strong>{item.symbol}</strong>
          <span>{[item.name, item.sector, item.industry].filter(Boolean).join(" - ")}</span>
        </button>
      ))}
    </div> : null}
  </div>;
}

function BenchmarkPicker({
  value,
  onChange,
  defaultBenchmark,
  associations,
}: {
  value: string;
  onChange: (value: string) => void;
  defaultBenchmark?: BenchmarkDefaultResponse;
  associations?: BenchmarkAssociation[];
}) {
  const [search, setSearch] = useState("");
  const benchmarks = useQuery({
    queryKey: ["benchmark-picker", search],
    queryFn: () => api.benchmarks({ q: search.trim() || undefined, limit: 8 }),
  });
  return <div className="benchmark-picker">
    <label>Benchmark<input value={value} onChange={(event) => onChange(event.target.value.toUpperCase())} placeholder={defaultBenchmark?.benchmark_index_id ?? "SP500"} /></label>
    <label>Find index<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search indexes" /></label>
    <div className="benchmark-picker-actions">
      {defaultBenchmark?.benchmark_index_id ? <button type="button" onClick={() => onChange(defaultBenchmark.benchmark_index_id ?? "")}>Use default</button> : null}
      {value ? <button type="button" onClick={() => onChange("")}>Clear</button> : null}
    </div>
    {associations?.length ? <div className="benchmark-associations">
      {associations.map((item) => (
        <button
          type="button"
          key={`${item.role}-${item.benchmark_index_id}`}
          className={value === item.benchmark_index_id ? "selected-row" : ""}
          onClick={() => onChange(item.benchmark_index_id)}
        >
          <strong>{item.role}</strong>
          <span>{item.benchmark_index_id}</span>
        </button>
      ))}
    </div> : null}
    {benchmarks.data?.length ? <div className="benchmark-picker-results">
      {benchmarks.data.slice(0, 5).map((item) => <button type="button" key={item.index_id} onClick={() => onChange(item.index_id)}><strong>{item.index_id}</strong><span>{item.index_name} - {item.currency}</span></button>)}
    </div> : null}
  </div>;
}

function AssetPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const { assetId = "" } = useParams();
  const [priceLimit, setPriceLimit] = useState("365");
  const [activityLimit, setActivityLimit] = useState("20");
  const [activityOffset, setActivityOffset] = useState(0);
  const [analyticsBenchmark, setAnalyticsBenchmark] = useState("");
  const asset = useQuery({ queryKey: ["asset", assetId], queryFn: () => api.asset(assetId) });
  const holdings = useQuery({ queryKey: ["asset-holdings", assetId], queryFn: () => api.assetHoldings(assetId) });
  const activity = useQuery({
    queryKey: ["asset-activity", assetId, activityLimit, activityOffset],
    queryFn: () => api.assetActivity(assetId, boundedInt(activityLimit, 20, 1, 200), activityOffset),
  });
  const prices = useQuery({
    queryKey: ["prices", assetId, priceLimit],
    queryFn: () => api.prices(assetId, boundedInt(priceLimit, 365, 1, 5000)),
  });
  const analytics = useQuery({
    queryKey: ["asset-analytics", assetId, analyticsBenchmark],
    queryFn: () => api.assetAnalytics(assetId, analyticsBenchmark.trim().toUpperCase() || undefined),
  });
  const defaultBenchmark = useQuery({
    queryKey: ["asset-default-benchmark", assetId],
    queryFn: () => api.assetDefaultBenchmark(assetId),
    enabled: Boolean(assetId),
  });
  const benchmarkAssociations = useQuery({
    queryKey: ["asset-benchmark-associations", assetId],
    queryFn: () => api.assetBenchmarkAssociations(assetId),
    enabled: Boolean(assetId),
    retry: false,
  });
  const deletePosition = useMutation({
    mutationFn: ({ portfolioId, holdingAssetId }: { portfolioId: number; holdingAssetId: string }) =>
      api.deletePosition(portfolioId, holdingAssetId),
    onSuccess: (_result, deleted) => {
      notify(`${deleted.holdingAssetId} removed from portfolio.`);
      client.invalidateQueries({ queryKey: ["asset-holdings", assetId] });
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["overview-updates"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const underlyingAssetId = asset.data?.underlying_asset_id;
  useEffect(() => {
    setActivityOffset(0);
  }, [assetId, activityLimit]);
  const deleteHolding = (holding: AssetHolding) => {
    const warning = holding.broker_linked
      ? `Delete ${holding.symbol} from ${holding.portfolio_name}? This holding is linked to a brokerage account, so the portfolio will fall out of sync with the brokerage account.`
      : `Delete ${holding.symbol} from ${holding.portfolio_name}?`;
    if (window.confirm(warning)) {
      deletePosition.mutate({ portfolioId: holding.portfolio_id, holdingAssetId: holding.asset_id });
    }
  };
  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorPanel error={asset.error} />;
  return <div className="page">
    <div className="page-title"><div><p className="eyebrow">{asset.data?.sector ?? "Asset detail"}</p><h1>{asset.data?.symbol} <small>{asset.data?.name}</small></h1></div><div className="actions">{underlyingAssetId ? <Link className="button-link" to={`/asset/${underlyingAssetId}`}><Activity size={17}/>Underlying chart</Link> : null}<Link className="button-link" to={`/compare?left=${asset.data?.asset_id ?? assetId}`}><BarChart3 size={17}/>Compare</Link><strong className="asset-price">{money(asset.data?.latest_price, asset.data?.currency)}</strong></div></div>
    <section className="card chart-card">
      <div className="card-heading">
        <div><p className="eyebrow">Price observations</p><h2>Price history</h2></div>
        <div className="card-tools"><label>Rows<select value={priceLimit} onChange={(event) => setPriceLimit(event.target.value)}><option value="90">90</option><option value="365">365</option><option value="1000">1000</option><option value="5000">5000</option></select></label></div>
      </div>
      <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={prices.data}><defs><linearGradient id="price" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5da78b" stopOpacity={0.4}/><stop offset="100%" stopColor="#5da78b" stopOpacity={0}/></linearGradient></defs><XAxis dataKey="date" hide/><YAxis hide domain={["dataMin", "dataMax"]}/><Tooltip/><Area type="monotone" dataKey="close" stroke="#5da78b" fill="url(#price)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
    </section>
    <AssetHoldingsPanel holdings={holdings.data ?? []} isLoading={holdings.isLoading} isDeleting={deletePosition.isPending} onDelete={deleteHolding} />
    <AssetActivityPanel
      activity={activity.data?.items ?? []}
      total={activity.data?.total ?? 0}
      limit={activity.data?.limit ?? boundedInt(activityLimit, 20, 1, 200)}
      offset={activity.data?.offset ?? activityOffset}
      isLoading={activity.isLoading}
      selectedLimit={activityLimit}
      onLimitChange={setActivityLimit}
      onPageChange={setActivityOffset}
    />
    <AssetAnalyticsPanel
      payload={analytics.data}
      isLoading={analytics.isLoading}
      benchmark={analyticsBenchmark}
      onBenchmarkChange={setAnalyticsBenchmark}
      defaultBenchmark={defaultBenchmark.data}
      associations={benchmarkAssociations.data?.associations}
    />
    <section className="detail-grid">
      <div className="card"><p className="eyebrow">Classification</p><h2>{asset.data?.industry ?? "Not classified"}</h2><p>{[asset.data?.sector, asset.data?.asset_type, asset.data?.asset_subtype].filter(Boolean).join(" - ") || "Classification unavailable"}</p></div>
      <div className="card"><p className="eyebrow">Listing</p><h2>{asset.data?.exchange_code ?? "Exchange unknown"}</h2><p>{[asset.data?.country, asset.data?.region, asset.data?.currency].filter(Boolean).join(" - ") || "Geography unavailable"}</p></div>
      <div className="card"><p className="eyebrow">Scale</p><h2>{asset.data?.size ?? "Size unknown"}</h2><p>Market cap {money(asset.data?.market_cap, asset.data?.currency)} - Shares {number(asset.data?.shares_outstanding, 0)} - Beta {number(asset.data?.market_beta)}</p></div>
      <div className="card"><p className="eyebrow">Business profile</p><p>{asset.data?.description ?? "No company description has been ingested yet."}</p></div>
    </section>
  </div>;
}
void AssetPage;

function AssetActivityPanel({
  activity,
  total,
  limit,
  offset,
  isLoading,
  selectedLimit,
  onLimitChange,
  onPageChange,
}: {
  activity: AssetActivity[];
  total: number;
  limit: number;
  offset: number;
  isLoading: boolean;
  selectedLimit: string;
  onLimitChange: (value: string) => void;
  onPageChange: (value: number) => void;
}) {
  return <section className="card asset-activity-card">
    <div className="card-heading">
      <div><p className="eyebrow">Brokerage activity</p><h2>Activity for this asset</h2></div>
      <div className="card-tools">
        <label>Rows<select value={selectedLimit} onChange={(event) => onLimitChange(event.target.value)}><option value="10">10</option><option value="20">20</option><option value="50">50</option><option value="100">100</option></select></label>
        <span>{total} item{total === 1 ? "" : "s"}</span>
      </div>
    </div>
    {isLoading ? <Loading compact /> : activity.length ? (
      <>
        <div className="asset-activity-list">
          {activity.map((item) => {
            const key = item.provider_transaction_id ?? item.transaction_id ?? `${item.timestamp}-${item.transaction_type}`;
            const currency = item.currency ?? "CAD";
            const amount = item.cash_amount != null ? money(Math.abs(item.cash_amount), currency) : item.price != null && item.quantity != null ? money(Math.abs(item.quantity * item.price), currency) : "Unavailable";
            return <article key={key}>
              <div>
                <strong>{item.transaction_type}</strong>
                <span>{new Date(item.timestamp).toLocaleDateString()} - {item.portfolio_name ?? item.provider_account_id ?? item.source}</span>
              </div>
              <span>{number(item.quantity, 4)} @ {money(item.price, currency)}</span>
              <b>{amount}</b>
            </article>;
          })}
        </div>
        <Pager total={total} limit={limit} offset={offset} onChange={onPageChange} />
      </>
    ) : <EmptyRow text="No broker or local activity has been recorded for this asset yet." />}
  </section>;
}

function AssetHoldingsPanel({ holdings, isLoading, isDeleting, onDelete }: { holdings: AssetHolding[]; isLoading: boolean; isDeleting: boolean; onDelete: (holding: AssetHolding) => void }) {
  return <section className="card asset-holdings-card">
    <div className="card-heading"><div><p className="eyebrow">Portfolio holding</p><h2>Manage this asset</h2></div><span>{holdings.length} holding{holdings.length === 1 ? "" : "s"}</span></div>
    {isLoading ? <Loading compact /> : holdings.length ? <div className="asset-holding-list">
      {holdings.map((holding) => <article key={`${holding.portfolio_id}-${holding.asset_id}`} className={holding.broker_linked ? "asset-holding broker-linked" : "asset-holding"}>
        <div>
          <strong>{holding.portfolio_name}</strong>
          <span>{number(holding.quantity, 4)} shares - {money(holding.book_cost, holding.currency)} book - {percent(holding.total_return_percent)} return</span>
          {holding.broker_linked ? <em>Deleting will put this portfolio out of sync with the brokerage account.</em> : null}
        </div>
        <div>
          <b>{money(holding.market_value, holding.currency)}</b>
          <button className="danger" disabled={isDeleting} onClick={() => onDelete(holding)}><Trash2 size={16}/>Delete holding</button>
        </div>
      </article>)}
    </div> : <EmptyRow text="This asset is not currently held in a portfolio." />}
  </section>;
}

function BrokersPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const [userKey, setUserKey] = useState("default");
  const [providerUserId, setProviderUserId] = useState("");
  const [userSecret, setUserSecret] = useState("");
  const [portalBroker, setPortalBroker] = useState("");
  const [portalReconnect, setPortalReconnect] = useState("");
  const [importPortfolioId, setImportPortfolioId] = useState("");
  const [message, setMessage] = useState("");
  const [portalUrl, setPortalUrl] = useState("");
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const connections = useQuery({ queryKey: ["broker-connections"], queryFn: api.brokerConnections });
  const accounts = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const refreshBroker = () => {
    client.invalidateQueries({ queryKey: ["broker-accounts"] });
    client.invalidateQueries({ queryKey: ["broker-connections"] });
  };
  const register = useMutation({
    mutationFn: api.registerBrokerUser,
    onSuccess: () => {
      const next = "Broker user registered. Open the portal next to connect accounts.";
      setMessage(next);
      notify(next);
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const saveExisting = useMutation({
    mutationFn: () => api.saveExistingBrokerUser(userKey, providerUserId, userSecret),
    onSuccess: () => {
      const next = "Existing SnapTrade user saved locally. You can now open portal or sync.";
      setUserSecret("");
      setMessage(next);
      notify(next);
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const portal = useMutation({
    mutationFn: () => api.brokerPortal({
      user_key: userKey.trim(),
      broker: portalBroker.trim() || null,
      reconnect: portalReconnect.trim() || null,
    }),
    onSuccess: (result) => {
      const next = "Portal URL created. Connect the bank there, then run Sync accounts here.";
      setPortalUrl(result.url);
      setMessage(next);
      notify(next);
      window.open(result.url, "_blank", "noopener,noreferrer");
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const sync = useMutation({
    mutationFn: api.brokerSync,
    onSuccess: (result) => {
      const next = `Broker sync finished: ${formatActionResult(result.result)}`;
      setMessage(next);
      notify(next);
      refreshBroker();
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const mapper = useMutation({
    mutationFn: ({ accountId, portfolioId }: { accountId: string; portfolioId: number }) =>
      api.mapBrokerAccount(accountId, portfolioId),
    onSuccess: () => {
      const next = "Account mapping saved and portfolio holdings updated.";
      setMessage(next);
      notify(next);
      refreshBroker();
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const importer = useMutation({
    mutationFn: () => api.importBrokerTransactions(importPortfolioId ? Number(importPortfolioId) : null),
    onSuccess: (result) => {
      const next = `Import finished: ${formatActionResult(result.result)}`;
      setMessage(next);
      notify(next);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
    },
    onError: (error) => {
      const next = friendlyBrokerError(error);
      setMessage(next);
      notify(next, "error");
    },
  });
  const isBusy = register.isPending || saveExisting.isPending || portal.isPending || sync.isPending || mapper.isPending || importer.isPending;
  const accountCount = accounts.data?.length ?? 0;
  const mappedCount = accounts.data?.filter((account) => account.portfolio_id != null).length ?? 0;
  const connectionCount = connections.data?.length ?? 0;
  const userKeyReady = Boolean(userKey.trim());
  const nextStep = !connectionCount ? "Create a secure broker link" : !accountCount ? "Sync linked accounts" : mappedCount < accountCount ? "Map accounts to portfolios" : "Review imported portfolios";

  return <div className="page"><div className="page-title"><div><p className="eyebrow">Broker setup</p><h1>Connect your accounts</h1><p className="page-subtitle">Use a read-only broker connection to pull balances, holdings, and activity into local portfolios.</p></div><div className="actions"><button onClick={() => sync.mutate(userKey)} disabled={isBusy || !userKeyReady}><RefreshCw size={17}/>Sync accounts</button><button className="primary" onClick={() => importer.mutate()} disabled={isBusy || !accountCount}><RefreshCw size={17}/>Import activity</button></div></div>
    <section className="card broker-setup-card">
      <div className="setup-intro">
        <div><p className="eyebrow">Recommended flow</p><h2>{nextStep}</h2></div>
        <span>{mappedCount}/{accountCount || 0} accounts mapped</span>
      </div>
      <div className="setup-steps">
        <SetupStep
          done={connectionCount > 0}
          icon={<KeyRound />}
          title="1. Create your secure link"
          text="Pick a local nickname, then open the broker portal. The portal handles login; Quaint Dash only receives read-only sync data."
        />
        <SetupStep
          done={accountCount > 0}
          icon={<RefreshCw />}
          title="2. Sync accounts"
          text="After the portal is connected, sync once to pull account names, balances, holdings, and recent activity."
        />
        <SetupStep
          done={accountCount > 0 && mappedCount === accountCount}
          icon={<WalletCards />}
          title="3. Choose portfolios"
          text="Send each broker account to a local portfolio. Mapping updates holdings immediately and can be changed later."
        />
      </div>
      <div className="quick-connect">
        <label>Connection nickname<input value={userKey} onChange={(event) => setUserKey(event.target.value)} placeholder="default" /></label>
        <div className="actions">
          <button onClick={() => register.mutate(userKey)} disabled={isBusy || !userKeyReady}>Create profile</button>
          <button className="primary" onClick={() => portal.mutate()} disabled={isBusy || !userKeyReady}><ExternalLink size={17}/>Open broker portal</button>
          <button onClick={() => sync.mutate(userKey)} disabled={isBusy || !userKeyReady}><RefreshCw size={17}/>Sync after linking</button>
        </div>
      </div>
      {message ? <p className="action-message">{message}</p> : <p className="action-message muted"><ShieldCheck size={16}/>Read-only connection. No trading permissions are requested or stored.</p>}
      {portalUrl ? <a className="portal-link" href={portalUrl} target="_blank" rel="noreferrer">Portal did not open? Click here to continue linking.</a> : null}
      <details className="advanced-broker">
        <summary>Advanced: portal and SnapTrade credentials</summary>
        <div className="advanced-grid">
          <label>Broker slug<input value={portalBroker} onChange={(event) => setPortalBroker(event.target.value)} placeholder="Optional portal broker slug" /></label>
          <label>Reconnect connection<input value={portalReconnect} onChange={(event) => setPortalReconnect(event.target.value)} placeholder="Optional connection id" /></label>
          <span className="inline-help">These optional fields are passed directly to the backend portal request.</span>
          <label>SnapTrade user ID<input value={providerUserId} onChange={(event) => setProviderUserId(event.target.value)} placeholder="Existing SnapTrade userId" /></label>
          <label>User secret<input type="password" value={userSecret} onChange={(event) => setUserSecret(event.target.value)} placeholder="Existing SnapTrade userSecret" /></label>
          <button onClick={() => saveExisting.mutate()} disabled={isBusy || !userKeyReady || !providerUserId.trim() || !userSecret.trim()}>Save existing user</button>
        </div>
      </details>
    </section>
    <section className="broker-grid">
      <div className="card">
        <div className="card-heading"><div><p className="eyebrow">Linked institutions</p><h2>Connections</h2></div><span>{connectionCount} linked</span></div>
        {connections.isLoading ? <Loading compact /> : connections.data?.length ? <div className="mini-list">{connections.data.map((item) => <article key={item.provider_connection_id}><div><strong>{item.institution_name}</strong><span>{item.provider}</span></div><span>{item.provider_connection_id}</span><b><span className={`pill ${item.status}`}>{item.status}</span></b></article>)}</div> : <EmptyRow text="No broker connections synced yet." />}
      </div>
      <div className="card">
        <div className="card-heading"><div><p className="eyebrow">What happens next</p><h2>Portfolio import</h2></div><span>read-only</span></div>
        <div className="broker-help">
          <p><strong>Mapping</strong> sends current holdings into the selected local portfolio.</p>
          <p><strong>Import activity</strong> adds broker transactions when available, without duplicating ones already imported.</p>
          <p><strong>All portfolios</strong> on the overview combines every mapped portfolio into one view.</p>
          <label className="mapping-label">Import scope<select value={importPortfolioId} onChange={(event) => setImportPortfolioId(event.target.value)} disabled={isBusy || !portfolios.data?.length}><option value="">All mapped portfolios</option>{portfolios.data?.map((portfolio) => <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>)}</select><em>The backend can import every mapped account or just one portfolio.</em></label>
          <button className="primary" onClick={() => importer.mutate()} disabled={isBusy || !accountCount}><RefreshCw size={17}/>Import selected scope</button>
        </div>
      </div>
    </section>
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Step 3</p><h2>Choose where each account goes</h2></div><span>{accountCount} account(s)</span></div>{accounts.isLoading ? <Loading compact /> : accounts.data?.length ? <div className="account-grid">{accounts.data.map((item) => <article className="account" key={item.provider_account_id}><Building2/><div><strong>{item.account_name ?? item.provider_account_id}</strong><span>{[item.provider, item.account_type, item.currency].filter(Boolean).join(" - ") || "Broker account"}</span><span className="muted-id">{item.provider_account_id} - {item.provider_connection_id}</span><label className="mapping-label">Local portfolio<select value={item.portfolio_id ?? ""} onChange={(event) => { if (event.target.value) mapper.mutate({ accountId: item.provider_account_id, portfolioId: Number(event.target.value) }); }} disabled={isBusy || !portfolios.data?.length}><option value="">Choose portfolio</option>{portfolios.data?.map((portfolio) => <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>)}</select><em>Mapping updates holdings right away.</em></label></div><div className="account-value"><b>{money(item.total_value ?? item.balance, item.currency ?? "CAD")}</b><span>holdings {money(item.holdings_value, item.currency ?? "CAD")}</span><span>cash {money(item.cash_balance, item.currency ?? "CAD")}</span><span>{item.position_count} position{item.position_count === 1 ? "" : "s"}{item.latest_position_date ? ` as of ${item.latest_position_date}` : ""}</span><span className={item.portfolio_id ? "pill done" : "pill"}>{item.portfolio_id ? "mapped" : "needs map"}</span></div></article>)}</div> : <EmptyRow text="No synced broker accounts yet. Open the portal, connect a brokerage, then sync accounts." />}</section>
  </div>;
}

function SetupStep({ done, icon, title, text }: { done: boolean; icon: React.ReactNode; title: string; text: string }) {
  return <article className={done ? "setup-step done" : "setup-step"}>
    <div>{done ? <CheckCircle2 /> : icon}</div>
    <strong>{title}</strong>
    <p>{text}</p>
  </article>;
}

function OperationsPage() {
  const client = useQueryClient();
  const [status, setStatus] = useState("");
  const [domain, setDomain] = useState("");
  const [jobLimit, setJobLimit] = useState("100");
  const [pipeline, setPipeline] = useState("all");
  const [assetId, setAssetId] = useState("");
  const [maxAssets, setMaxAssets] = useState("25");
  const [years, setYears] = useState("10");
  const [pricesOnly, setPricesOnly] = useState(false);
  const [scheduleRankingFactor, setScheduleRankingFactor] = useState<StockRankingFactor>("aggregate");
  const [scheduleRankingUniverse, setScheduleRankingUniverse] = useState<StockRankingUniverse>("tracked");
  const [rankingMissingOnly, setRankingMissingOnly] = useState(true);
  const [rankingStaleOnly, setRankingStaleOnly] = useState(false);
  const [runDomain, setRunDomain] = useState("all");
  const [runMaxJobs, setRunMaxJobs] = useState("1");
  const [retryMaxJobs, setRetryMaxJobs] = useState("25");
  const [message, setMessage] = useState("");
  type ScheduleOverride = {
    pipeline?: string;
    assetId?: string;
    maxAssets?: string;
    years?: string;
    pricesOnly?: boolean;
    rankingFactor?: StockRankingFactor;
    rankingUniverse?: StockRankingUniverse;
    missingOnly?: boolean;
    staleOnly?: boolean;
  };
  const jobs = useQuery({
    queryKey: ["jobs", status, domain, jobLimit],
    queryFn: () => api.ingestionJobs(status, domain, boundedInt(jobLimit, 100, 1, 500)),
    refetchInterval: 10000,
  });
  const background = useQuery({
    queryKey: ["ingestion-background-status"],
    queryFn: api.ingestionBackgroundStatus,
    refetchInterval: 10000,
  });
  const readiness = useQuery({
    queryKey: ["ingestion-readiness"],
    queryFn: api.ingestionReadiness,
    refetchInterval: 10000,
  });
  const rankingReadiness = useQuery({
    queryKey: ["ranking-readiness", scheduleRankingUniverse],
    queryFn: () => api.rankingReadiness({
      universe: scheduleRankingUniverse,
      limit: boundedInt(maxAssets, 25, 1, 100),
    }),
    refetchInterval: 10000,
  });
  const schedule = useMutation({
    mutationFn: (override?: ScheduleOverride) => api.scheduleIngestion({
      pipeline: override?.pipeline ?? pipeline,
      asset_id: (override?.assetId ?? assetId.trim()) || null,
      max_assets: boundedInt(override?.maxAssets ?? maxAssets, 25, 1, 100),
      years: boundedInt(override?.years ?? years, 10, 1, 30),
      prices_only: override?.pricesOnly ?? pricesOnly,
      ranking_factor: override?.rankingFactor ?? scheduleRankingFactor,
      ranking_universe: override?.rankingUniverse ?? scheduleRankingUniverse,
      missing_only: override?.missingOnly ?? rankingMissingOnly,
      stale_only: override?.staleOnly ?? rankingStaleOnly,
    }),
    onSuccess: (result) => {
      setMessage(`Scheduled: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
    },
  });
  const run = useMutation({
    mutationFn: () => api.runIngestion({
      domain: runDomain,
      max_jobs: boundedInt(runMaxJobs, 1, 1, 25),
    }),
    onSuccess: (result) => {
      setMessage(`Run finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
    },
  });
  const retry = useMutation({
    mutationFn: () => api.retryFailedIngestion({
      domain: domain || null,
      max_jobs: boundedInt(retryMaxJobs, 25, 1, 100),
    }),
    onSuccess: (result) => {
      setMessage(`Retry queued: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
    },
  });
  const clearHistory = useMutation({
    mutationFn: api.clearIngestionHistory,
    onSuccess: (result) => {
      setMessage(`Cleared: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
    },
  });
  const startBackground = useMutation({
    mutationFn: api.startIngestionBackground,
    onSuccess: () => {
      setMessage("Auto worker started.");
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
    },
  });
  const stopBackground = useMutation({
    mutationFn: api.stopIngestionBackground,
    onSuccess: () => {
      setMessage("Auto worker stopped.");
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
    },
  });
  const tickBackground = useMutation({
    mutationFn: api.tickIngestionBackground,
    onSuccess: (result) => {
      setMessage(`Auto worker cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
    },
  });
  const isBusy = schedule.isPending || run.isPending || retry.isPending || clearHistory.isPending || startBackground.isPending || stopBackground.isPending || tickBackground.isPending;
  const actionError = schedule.error ?? run.error ?? retry.error ?? clearHistory.error ?? startBackground.error ?? stopBackground.error ?? tickBackground.error;
  const scheduleAsset = (selectedAssetId: string) => {
    setPipeline("all");
    setAssetId(selectedAssetId);
    schedule.mutate({ pipeline: "all", assetId: selectedAssetId, maxAssets: "1" });
  };
  const scheduleRankingAsset = (selectedAssetId: string, factor: StockRankingFactor) => {
    setPipeline("ranking");
    setAssetId(selectedAssetId);
    setScheduleRankingFactor(factor);
    schedule.mutate({
      pipeline: "ranking",
      assetId: selectedAssetId,
      maxAssets: "1",
      rankingFactor: factor,
      rankingUniverse: scheduleRankingUniverse,
      missingOnly: true,
      staleOnly: true,
    });
  };
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1><p className="page-subtitle">Background due work keeps routine data moving. Manual controls remain here for backfills, retries, provider-sensitive refreshes, and explicit runs.</p></div><div className="actions"><button onClick={() => { jobs.refetch(); background.refetch(); readiness.refetch(); rankingReadiness.refetch(); }} disabled={jobs.isFetching || background.isFetching || readiness.isFetching || rankingReadiness.isFetching}><RefreshCw size={17}/>Refresh</button><button className="danger" onClick={() => window.confirm("Clear ingestion job history and sync status rows? Market data and broker connections will stay intact.") && clearHistory.mutate()} disabled={isBusy}><Trash2 size={17}/>Clear history</button><button className="primary" onClick={() => window.confirm("Run pending ingestion jobs with these options?") && run.mutate()} disabled={isBusy}><RefreshCw size={17}/>Run jobs</button></div></div>
    <IngestionBackgroundCard status={background.data} isLoading={background.isLoading} error={background.error} onStart={() => startBackground.mutate()} onStop={() => stopBackground.mutate()} onTick={() => tickBackground.mutate()} isBusy={isBusy} />
    <IngestionReadinessCard readiness={readiness.data} isLoading={readiness.isLoading} error={readiness.error} onScheduleAsset={scheduleAsset} isBusy={isBusy} />
    <RankingReadinessCard readiness={rankingReadiness.data} isLoading={rankingReadiness.isLoading} error={rankingReadiness.error} onScheduleAsset={scheduleRankingAsset} isBusy={isBusy} />
    <section className="card operations-control">
      <div className="card-heading"><div><p className="eyebrow">Manual controls</p><h2>Ingestion actions</h2></div><div className="card-tools"><HelpDisclosure title="Manual ingestion actions" items={ingestionHelp} /><span>{isBusy ? "working" : "ready"}</span></div></div>
      <div className="operations-grid">
        <div className="control-panel">
          <strong>Schedule jobs</strong>
          <div className="control-fields">
            <label>Pipeline<select value={pipeline} onChange={(event) => setPipeline(event.target.value)}><option value="all">All</option><option value="ranking">Ranking</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
            <label>Asset ID<input value={assetId} onChange={(event) => setAssetId(event.target.value.toUpperCase())} placeholder="Optional ticker" /></label>
            <label>Max assets<input type="number" min="1" max="100" value={maxAssets} onChange={(event) => setMaxAssets(event.target.value)} /></label>
            <label>Years<input type="number" min="1" max="30" value={years} onChange={(event) => setYears(event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={pricesOnly} onChange={(event) => setPricesOnly(event.target.checked)} />Prices only</label>
            <label>Ranking factor<select value={scheduleRankingFactor} onChange={(event) => setScheduleRankingFactor(event.target.value as StockRankingFactor)}>{stockRankingFactors.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
            <label>Ranking universe<select value={scheduleRankingUniverse} onChange={(event) => setScheduleRankingUniverse(event.target.value as StockRankingUniverse)}><option value="tracked">Tracked</option><option value="all">All stocks</option></select></label>
            <label className="check-row"><input type="checkbox" checked={rankingMissingOnly} onChange={(event) => setRankingMissingOnly(event.target.checked)} />Missing only</label>
            <label className="check-row"><input type="checkbox" checked={rankingStaleOnly} onChange={(event) => setRankingStaleOnly(event.target.checked)} />Stale only</label>
          </div>
          <button onClick={() => window.confirm("Schedule ingestion jobs with these options?") && schedule.mutate({})} disabled={isBusy}>Schedule</button>
        </div>
        <div className="control-panel">
          <strong>Run pending jobs</strong>
          <div className="control-fields two">
            <label>Domain<select value={runDomain} onChange={(event) => setRunDomain(event.target.value)}><option value="all">All</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
            <label>Max jobs<input type="number" min="1" max="25" value={runMaxJobs} onChange={(event) => setRunMaxJobs(event.target.value)} /></label>
          </div>
          <button className="primary" onClick={() => window.confirm("Run pending ingestion jobs with these options?") && run.mutate()} disabled={isBusy}><RefreshCw size={17}/>Run</button>
        </div>
        <div className="control-panel">
          <strong>Retry failed jobs</strong>
          <div className="control-fields two">
            <label>Domain<span>{domain || "Any filtered domain"}</span></label>
            <label>Max jobs<input type="number" min="1" max="100" value={retryMaxJobs} onChange={(event) => setRetryMaxJobs(event.target.value)} /></label>
          </div>
          <button onClick={() => window.confirm("Move failed jobs back to pending with these options?") && retry.mutate()} disabled={isBusy}>Retry failed</button>
        </div>
      </div>
      {message ? <p className="action-message">{message}</p> : null}
      {actionError ? <ErrorPanel error={actionError} /> : null}
    </section>
    <section className="card">
      <div className="card-heading">
        <h2>Ingestion jobs</h2>
        <div className="card-tools">
          <label>Rows<select value={jobLimit} onChange={(event) => setJobLimit(event.target.value)}><option value="25">25</option><option value="100">100</option><option value="250">250</option><option value="500">500</option></select></label>
          <span>{jobs.data?.length ?? 0} shown</span>
        </div>
      </div>
      <div className="filter-row">
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Any</option><option value="pending">Pending</option><option value="running">Running</option><option value="done">Done</option><option value="failed">Failed</option></select></label>
        <label>Domain<select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">Any</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
      </div>
      {jobs.error ? <ErrorPanel error={jobs.error} /> : jobs.isLoading ? <Loading compact /> : (
        <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Dataset</th><th>Type</th><th>Domain</th><th>Window</th><th>Status</th><th>Priority</th><th>Attempts</th><th>Updated</th><th>Error</th></tr></thead><tbody>{jobs.data?.map((job) => <tr key={job.job_id}><td>{job.asset_id ?? "Global"}</td><td>{job.dataset}</td><td>{job.job_type}</td><td>{job.domain}</td><td>{dateRange(job.requested_start_date, job.requested_end_date)}</td><td><span className={`pill ${job.status}`}>{job.status}</span></td><td>{job.priority}</td><td>{job.attempt_count}</td><td>{new Date(job.updated_at).toLocaleDateString()}</td><td className="job-error" title={job.error_message ?? ""}>{job.error_message ?? "-"}</td></tr>)}</tbody></table></div>
      )}
      {!jobs.isLoading && !jobs.data?.length ? <EmptyRow text="No ingestion jobs match the current filters." /> : null}
    </section>
  </div>;
}

function IngestionBackgroundCard({
  status,
  isLoading,
  error,
  onStart,
  onStop,
  onTick,
  isBusy,
}: {
  status?: IngestionBackgroundStatus;
  isLoading: boolean;
  error: Error | null;
  onStart: () => void;
  onStop: () => void;
  onTick: () => void;
  isBusy: boolean;
}) {
  const stateLabel = status?.enabled ? (status.running ? "running" : "enabled") : "disabled";
  return <section className="card operations-background">
    <div className="card-heading">
      <div><p className="eyebrow">Background due work</p><h2>Routine ingestion worker</h2></div>
      <div className="card-tools"><HelpDisclosure title="Ingestion basics" items={ingestionHelp} /><span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Last scheduled" value={isLoading ? "Loading" : formatCount(status?.last_schedule_count, "job")} />
        <Signal label="Last completed" value={isLoading ? "Loading" : formatCount(status?.last_completed_count, "job")} />
        <Signal label="Schedule cadence" value={status ? formatDuration(status.schedule_interval_seconds) : "Unavailable"} />
        <Signal label="Run cadence" value={status ? `${formatDuration(status.run_interval_seconds)} / ${status.max_jobs_per_tick} job cap` : "Unavailable"} />
        <div className="background-actions">
          <button className={status?.enabled ? "" : "primary"} onClick={() => window.confirm("Start the routine ingestion worker for this API session? It will schedule due work and run bounded batches in the background.") && onStart()} disabled={isBusy || isLoading || status?.enabled}>Start worker</button>
          <button onClick={() => window.confirm("Stop the routine ingestion worker? Manual controls will still work.") && onStop()} disabled={isBusy || isLoading || !status?.enabled}>Stop worker</button>
          <button onClick={() => window.confirm("Run one background worker cycle now? This schedules due routine jobs and runs a bounded batch.") && onTick()} disabled={isBusy || isLoading}><RefreshCw size={17}/>Run one cycle</button>
        </div>
        <div className="background-status-note">
          <strong>{status?.enabled ? "Routine maintenance is configured." : "Routine maintenance is off."}</strong>
          <span>{status ? backgroundStatusDetail(status) : "Status has not loaded yet."}</span>
          {status?.last_error ? <em>{status.last_error}</em> : null}
        </div>
      </div>
    )}
  </section>;
}

function IngestionReadinessCard({
  readiness,
  isLoading,
  error,
  onScheduleAsset,
  isBusy,
}: {
  readiness?: IngestionReadiness;
  isLoading: boolean;
  error: Error | null;
  onScheduleAsset: (assetId: string) => void;
  isBusy: boolean;
}) {
  const missingItems = readiness?.items.filter((item) => !item.ready) ?? [];
  return <section className="card operations-readiness">
    <div className="card-heading">
      <div><p className="eyebrow">Portfolio tickers</p><h2>Projection input readiness</h2></div>
      <div className="card-tools"><HelpDisclosure title="Readiness checks" items={dataReadinessHelp} /><span>{isLoading ? "loading" : `${readiness?.ready_count ?? 0}/${readiness?.total ?? 0} ready`}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : isLoading ? <Loading compact /> : readiness?.items.length ? (
      <div className="readiness-list">
        {missingItems.slice(0, 6).map((item) => <article className="readiness-row" key={item.asset_id}>
          <div><strong>{item.symbol}</strong><span>{item.asset_type ?? "asset"}</span></div>
          <div className="readiness-detail">
            <p>{item.missing.slice(0, 4).join(", ")}</p>
            <div>
              {item.requirements.filter((requirement) => !requirement.ready).slice(0, 4).map((requirement) => (
                <span className="readiness-chip" key={requirement.key}>
                  {requirement.label}: {requirement.detail}
                </span>
              ))}
            </div>
          </div>
          <div className="readiness-actions">
            <span className="pill failed">{item.missing.length} missing</span>
            <button onClick={() => onScheduleAsset(item.asset_id)} disabled={isBusy}>Schedule</button>
          </div>
        </article>)}
        {!missingItems.length ? <div className="empty-row">All portfolio tickers have the required projection and valuation inputs.</div> : null}
      </div>
    ) : <EmptyRow text="No active portfolio or watchlist tickers found." />}
  </section>;
}

function RankingReadinessCard({
  readiness,
  isLoading,
  error,
  onScheduleAsset,
  isBusy,
}: {
  readiness?: StockRankingReadiness;
  isLoading: boolean;
  error: Error | null;
  onScheduleAsset: (assetId: string, factor: StockRankingFactor) => void;
  isBusy: boolean;
}) {
  const missingItems = readiness?.items.filter((item) => !item.ready) ?? [];
  return <section className="card operations-readiness">
    <div className="card-heading">
      <div><p className="eyebrow">Stock rankings</p><h2>Ranking input readiness</h2></div>
      <div className="card-tools"><HelpDisclosure title="Readiness checks" items={dataReadinessHelp} /><span>{isLoading ? "loading" : `${readiness?.ready_count ?? 0}/${readiness?.total ?? 0} complete`}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : isLoading ? <Loading compact /> : readiness?.items.length ? (
      <div className="readiness-list">
        {missingItems.slice(0, 6).map((item) => {
          const firstMissing = item.requirements.find((requirement) => !requirement.ready);
          return <article className="readiness-row" key={item.asset_id}>
            <div><strong>{item.symbol}</strong><span>{item.name ?? item.universe}</span></div>
            <div className="readiness-detail">
              <p>{item.complete_factor_count}/{item.total_factor_count} factors complete</p>
              <div>
                {item.requirements.filter((requirement) => !requirement.ready).slice(0, 4).map((requirement) => (
                  <span className="readiness-chip" key={requirement.key}>
                    {requirement.label}: {requirement.detail}
                  </span>
                ))}
              </div>
            </div>
            <div className="readiness-actions">
              <span className="pill failed">{item.missing.length} missing</span>
              <button onClick={() => onScheduleAsset(item.asset_id, (firstMissing?.key ?? "aggregate") as StockRankingFactor)} disabled={isBusy}>Schedule</button>
            </div>
          </article>;
        })}
        {!missingItems.length ? <div className="empty-row">All checked stock ranking inputs are complete.</div> : null}
      </div>
    ) : <EmptyRow text="No ranking universe assets found. Seed the stock catalog or add tracked stocks to populate this check." />}
  </section>;
}

function Metric({ icon, label, value, detail, positive }: { icon: React.ReactNode; label: string; value: string; detail?: string; positive?: boolean }) {
  return <article className="metric card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong>{detail && <span className={positive ? "positive" : "negative"}>{detail}</span>}</article>;
}
function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  const nextOffset = offset + limit;
  const previousOffset = Math.max(offset - limit, 0);
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + limit, total);
  return <div className="pager">
    <span>{start}-{end} of {total}</span>
    <div className="actions">
      <button onClick={() => onChange(previousOffset)} disabled={offset <= 0}>Previous</button>
      <button onClick={() => onChange(nextOffset)} disabled={nextOffset >= total}>Next</button>
    </div>
  </div>;
}
function AnalyticsPanel({
  payload,
  isLoading,
}: {
  payload?: Record<string, unknown>;
  isLoading: boolean;
}) {
  const report = payload?.report as AnyRecord | undefined;
  const performance = record(report?.performance);
  const risk = record(report?.risk);
  const decomposition = record(report?.risk_decomposition);
  const valuation = record(report?.valuation);
  const forecast = record(report?.forecast);
  const simulation = record(forecast?.simulation);
  const aiContext = record(payload?.ai_context);
  const anomalies = arrayOfRecords(aiContext?.anomalies);
  const volatilityContributions = arrayOfRecords(decomposition?.volatility_contributions).slice(0, 4);
  const valuationContributions = arrayOfRecords(valuation?.position_contributions).slice(0, 6);
  const healthItems: DataHealthItem[] = [
    {
      label: "DCF rollup",
      detail: "Holding intrinsic value and margin of safety",
      missing: missingList(valuation?.missing_inputs),
      ready: num(valuation?.weighted_margin_of_safety) != null || num(valuation?.weighted_pe_ratio) != null,
    },
    {
      label: "Monte Carlo",
      detail: "Projected value band and expected CAGR",
      missing: missingList(forecast?.missing_inputs),
      ready: num(simulation?.expected_value) != null,
    },
    {
      label: "Valuation models",
      detail: "Multiples, dividend yield, and holding-level forecasts",
      missing: uniqueStrings([
        ...missingList(valuation?.missing_inputs),
        ...missingList(forecast?.missing_inputs),
        ...missingList(performance?.missing_inputs),
      ]),
      ready: num(valuation?.weighted_expected_cagr) != null || num(valuation?.weighted_price_to_free_cash_flow) != null,
    },
  ];
  return <section className="card">
    <div className="card-heading">
      <div><p className="eyebrow">Phase 3 analytics</p><h2>Portfolio signals</h2></div>
      <div className="card-tools">
        <HelpDisclosure title="Portfolio analytics" items={portfolioAnalyticsHelp} note="These metrics are best used together. A high return with poor drawdown or weak data should still be treated cautiously." />
        <span>{payload?.schema_version as string ?? "loading"}</span>
      </div>
    </div>
    {isLoading ? <Loading compact /> : (
      <div className="analytics-stack">
        <div className="signal-grid deep">
          <Signal label="Modified Dietz" value={percent(num(performance?.modified_dietz_return))} />
          <Signal label="CAGR" value={percent(num(risk?.cagr))} />
          <Signal label="Volatility" value={percent(num(risk?.annualized_volatility))} />
          <Signal label="Sharpe" value={number(num(risk?.sharpe_ratio))} />
          <Signal label="Sortino" value={number(num(risk?.sortino_ratio))} />
          <Signal label="Max drawdown" value={percent(num(risk?.max_drawdown))} />
          <Signal label="Expected CAGR" value={percent(num(valuation?.weighted_expected_cagr))} />
          <Signal label="Dividend yield" value={percent(num(valuation?.weighted_dividend_yield))} />
        </div>
        <div className="analytics-detail-grid">
          <AnalyticsBlock title="Concentration">
            <MetricLine label="Largest holding" value={percent(num(decomposition?.largest_position_weight))} />
            <MetricLine label="Effective assets" value={number(num(decomposition?.effective_asset_count), 1)} />
            <MetricLine label="Diversification" value={number(num(decomposition?.diversification_score), 1)} />
            <MetricLine label="Average correlation" value={number(num(decomposition?.average_pairwise_correlation), 2)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Exposure">
            <ExposureBars values={record(decomposition?.sector_exposure)} />
            <ExposureBars values={record(decomposition?.country_exposure)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Risk contributors">
            {volatilityContributions.length ? volatilityContributions.map((item) => <MetricLine key={String(item.asset_id)} label={String(item.asset_id)} value={percent(num(item.percent_of_portfolio_volatility))} />) : <span className="muted-copy">No volatility contribution data yet.</span>}
          </AnalyticsBlock>
          <AnalyticsBlock title="Forecast">
            <MetricLine label="5y median" value={money(num(simulation?.p50_value))} />
            <MetricLine label="10th percentile" value={money(num(simulation?.p10_value))} />
            <MetricLine label="90th percentile" value={money(num(simulation?.p90_value))} />
            <MetricLine label="Blended CAGR" value={percent(num(forecast?.blended_expected_cagr))} />
          </AnalyticsBlock>
        </div>
        <div className="model-grid">
          <AnalyticsBlock title="Monte Carlo projection">
            <MetricLine label="Expected value" value={money(num(simulation?.expected_value))} />
            <MetricLine label="Expected CAGR" value={percent(num(simulation?.expected_cagr))} />
            <MetricLine label="Bear CAGR" value={percent(num(simulation?.p10_cagr))} />
            <MetricLine label="Bull CAGR" value={percent(num(simulation?.p90_cagr))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Valuation rollup">
            <MetricLine label="Expected CAGR" value={percent(num(valuation?.weighted_expected_cagr))} />
            <MetricLine label="Dividend yield" value={percent(num(valuation?.weighted_dividend_yield))} />
            <MetricLine label="Margin of safety" value={num(valuation?.weighted_margin_of_safety) == null ? "Needs DCF inputs" : percent(num(valuation?.weighted_margin_of_safety))} />
            <MetricLine label="Valuation mix" value={valuationMixLabel(valuation)} />
          </AnalyticsBlock>
        </div>
        <DataHealthPanel items={healthItems} />
        {valuationContributions.length ? <div className="model-table"><table><thead><tr><th>Holding</th><th>Weight</th><th>Expected CAGR</th><th>Margin</th><th>P/E</th><th>P/FCF</th></tr></thead><tbody>{valuationContributions.map((item) => <tr key={String(item.asset_id)}><td>{String(item.asset_id)}</td><td>{percent(num(item.weight))}</td><td>{percent(num(item.expected_cagr))}</td><td>{percent(num(item.margin_of_safety))}</td><td>{number(num(item.pe_ratio))}</td><td>{number(num(item.price_to_free_cash_flow))}</td></tr>)}</tbody></table></div> : null}
        {anomalies.length ? <InsightList items={anomalies.map((item) => `${String(item.severity).toUpperCase()}: ${String(item.message)}`)} /> : null}
      </div>
    )}
  </section>;
}
function Signal({ label, value }: { label: string; value: string }) {
  return <div className="signal"><span>{label}</span><strong>{value}</strong></div>;
}

function AssetAnalyticsPanel({
  payload,
  isLoading,
  benchmark,
  onBenchmarkChange,
  defaultBenchmark,
  associations,
}: {
  payload?: Record<string, unknown>;
  isLoading: boolean;
  benchmark: string;
  onBenchmarkChange: (value: string) => void;
  defaultBenchmark?: BenchmarkDefaultResponse;
  associations?: BenchmarkAssociation[];
}) {
  const report = payload?.report as AnyRecord | undefined;
  const risk = record(report?.risk);
  const relative = record(report?.relative);
  const valuation = record(report?.valuation_depth);
  const dividend = record(report?.dividend_discount);
  const dcf = record(report?.discounted_cash_flow);
  const forecast = record(report?.forecast);
  const simulation = record(forecast?.simulation);
  const dcfInputs = record(dcf?.inputs_used);
  const dividendInputs = record(dividend?.inputs_used);
  const dcfScenarios = arrayOfRecords(valuation?.dcf_scenarios);
  const aiContext = record(payload?.ai_context);
  const anomalies = arrayOfRecords(aiContext?.anomalies);
  const healthItems: DataHealthItem[] = [
    {
      label: "DCF",
      detail: "Intrinsic value per share and margin of safety",
      missing: missingList(dcf?.missing_inputs),
      ready: num(dcf?.intrinsic_value_per_share) != null,
    },
    {
      label: "Monte Carlo",
      detail: "Forecast range from expected return and volatility",
      missing: missingList(forecast?.missing_inputs),
      ready: num(simulation?.expected_value) != null,
    },
    {
      label: "Valuation models",
      detail: "Fundamental ratios, DCF scenarios, and growth assumptions",
      missing: uniqueStrings([
        ...missingList(valuation?.missing_inputs),
        ...missingList(forecast?.missing_inputs),
        ...missingList(dividend?.missing_inputs),
      ]),
      ready: num(valuation?.pe_ratio) != null || dcfScenarios.some((item) => num(item.intrinsic_value_per_share) != null),
    },
  ];
  return <section className="card asset-analytics-card">
    <div className="card-heading">
      <div><p className="eyebrow">Phase 3 analytics</p><h2>Asset signals</h2></div>
      <div className="card-tools">
        <HelpDisclosure title="Asset analytics" items={assetAnalyticsHelp} note="Fair value models are sensitive to assumptions. Treat them as structured estimates, then compare against the business story and risk." />
        <BenchmarkPicker value={benchmark} onChange={onBenchmarkChange} defaultBenchmark={defaultBenchmark} associations={associations} />
        <span>{payload?.schema_version as string ?? "loading"}</span>
      </div>
    </div>
    {isLoading ? <Loading compact /> : (
      <div className="analytics-stack">
        <div className="signal-grid deep">
          <Signal label="Historical CAGR" value={percent(num(risk?.cagr))} />
          <Signal label="Volatility" value={percent(num(risk?.annualized_volatility))} />
          <Signal label="Sharpe" value={number(num(risk?.sharpe_ratio))} />
          <Signal label="Sortino" value={number(num(risk?.sortino_ratio))} />
          <Signal label="Max drawdown" value={percent(num(risk?.max_drawdown))} />
          <Signal label="Beta" value={number(num(relative?.beta))} />
          <Signal label="P/E" value={number(num(valuation?.pe_ratio))} />
          <Signal label="Blended CAGR" value={percent(num(forecast?.blended_expected_cagr))} />
        </div>
        <div className="analytics-detail-grid">
          <AnalyticsBlock title="Risk profile">
            <MetricLine label="Best day" value={percent(num(risk?.best_daily_return))} />
            <MetricLine label="Worst day" value={percent(num(risk?.worst_daily_return))} />
            <MetricLine label="Alpha" value={percent(num(relative?.alpha_annualized))} />
            <MetricLine label="Correlation" value={number(num(relative?.correlation), 2)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Valuation">
            <MetricLine label="DCF fair value" value={money(num(dcf?.intrinsic_value_per_share))} />
            <MetricLine label="DCF safety" value={percent(num(dcf?.margin_of_safety))} />
            <MetricLine label="DDM fair value" value={money(num(dividend?.intrinsic_value_per_share))} />
            <MetricLine label="P/FCF" value={number(num(valuation?.price_to_free_cash_flow))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Quality">
            <MetricLine label="Gross margin" value={percent(num(valuation?.gross_margin))} />
            <MetricLine label="Net margin" value={percent(num(valuation?.net_margin))} />
            <MetricLine label="ROE" value={percent(num(valuation?.return_on_equity))} />
            <MetricLine label="Debt/equity" value={number(num(valuation?.debt_to_equity))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Forecast band">
            <MetricLine label="5y median" value={money(num(simulation?.p50_value))} />
            <MetricLine label="10th percentile" value={money(num(simulation?.p10_value))} />
            <MetricLine label="90th percentile" value={money(num(simulation?.p90_value))} />
            <MetricLine label="Expected value" value={money(num(simulation?.expected_value))} />
          </AnalyticsBlock>
        </div>
        <div className="model-grid">
          <AnalyticsBlock title="DCF model">
            <MetricLine label="Cash flow/share" value={money(num(dcfInputs?.cashflow_per_share))} />
            <MetricLine label="Discount rate" value={percent(num(dcfInputs?.discount_rate))} />
            <MetricLine label="Growth rate" value={percent(num(dcfInputs?.growth_rate))} />
            <MetricLine label="Terminal growth" value={percent(num(dcfInputs?.terminal_growth_rate))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Dividend model">
            <MetricLine label="DDM fair value" value={money(num(dividend?.intrinsic_value_per_share))} />
            <MetricLine label="Annual dividend" value={money(num(dividendInputs?.annual_dividend))} />
            <MetricLine label="Implied growth" value={percent(num(dividend?.implied_growth_rate))} />
            <MetricLine label="Dividend growth" value={percent(num(forecast?.dividend_growth_projection))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Monte Carlo projection">
            <MetricLine label="Expected CAGR" value={percent(num(simulation?.expected_cagr))} />
            <MetricLine label="Bear CAGR" value={percent(num(simulation?.p10_cagr))} />
            <MetricLine label="Median CAGR" value={percent(num(simulation?.p50_cagr))} />
            <MetricLine label="Bull CAGR" value={percent(num(simulation?.p90_cagr))} />
          </AnalyticsBlock>
        </div>
        <DataHealthPanel items={healthItems} />
        {dcfScenarios.length ? <div className="model-table"><table><thead><tr><th>DCF scenario</th><th>Fair value</th><th>Margin</th><th>Growth</th><th>Discount</th><th>Terminal</th></tr></thead><tbody>{dcfScenarios.map((item) => <tr key={String(item.scenario_name)}><td>{String(item.scenario_name)}</td><td>{money(num(item.intrinsic_value_per_share))}</td><td>{percent(num(item.margin_of_safety))}</td><td>{percent(num(item.growth_rate))}</td><td>{percent(num(item.discount_rate))}</td><td>{percent(num(item.terminal_growth_rate))}</td></tr>)}</tbody></table></div> : null}
        {anomalies.length ? <InsightList items={anomalies.map((item) => `${String(item.severity).toUpperCase()}: ${String(item.message)}`)} /> : null}
      </div>
    )}
  </section>;
}
type AnyRecord = Record<string, unknown>;
type DataHealthItem = {
  label: string;
  detail: string;
  missing: string[];
  ready: boolean;
};
function record(value: unknown): AnyRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as AnyRecord : {};
}
function arrayOfRecords(value: unknown): AnyRecord[] {
  return Array.isArray(value) ? value.filter((item): item is AnyRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}
function missingList(value: unknown): string[] {
  return Array.isArray(value) ? uniqueStrings(value.map((item) => String(item)).filter(Boolean)) : [];
}
function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.map((item) => item.trim()).filter(Boolean)));
}
function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function boundedInt(value: string, fallback: number, min: number, max: number): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, min), max);
}
function formatActionResult(result: Record<string, unknown>): string {
  const entries = Object.entries(result);
  if (!entries.length) return "ok";
  return entries.map(([key, value]) => `${key.replace(/_/g, " ")} ${String(value)}`).join(", ");
}
function formatCount(value: number | null | undefined, noun: string): string {
  if (value == null) return "Not run yet";
  return `${value} ${noun}${value === 1 ? "" : "s"}`;
}
function formatDuration(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}
function formatTimestamp(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "never";
}
function backgroundStatusDetail(status: IngestionBackgroundStatus): string {
  const schedule = `Scheduled ${formatTimestamp(status.last_schedule_at)}`;
  const run = `ran ${formatTimestamp(status.last_run_at)}`;
  const scope = `${status.max_assets_per_schedule} assets, ${status.years} years, ${status.prices_only ? "prices only" : "prices/dividends/splits"}`;
  return `${schedule}; ${run}. Scope: ${scope}.`;
}
function dateRange(start?: string | null, end?: string | null): string {
  if (start && end) return `${new Date(start).toLocaleDateString()} - ${new Date(end).toLocaleDateString()}`;
  if (start) return `From ${new Date(start).toLocaleDateString()}`;
  if (end) return `Until ${new Date(end).toLocaleDateString()}`;
  return "Any";
}
function DataHealthPanel({ items }: { items: DataHealthItem[] }) {
  return <div className="data-health-panel">
    <div className="data-health-heading">
      <div><p className="eyebrow">Analytics data health</p><strong>Model input readiness</strong></div>
      <div className="card-tools"><HelpDisclosure title="Model input readiness" items={dataReadinessHelp} /><span>{items.filter((item) => item.missing.length === 0 && item.ready).length}/{items.length} ready</span></div>
    </div>
    <div className="data-health-grid">
      {items.map((item) => {
        const status = item.missing.length ? "missing" : item.ready ? "ready" : "weak";
        return <article className={`data-health-card ${status}`} key={item.label}>
          <div><strong>{item.label}</strong><span className={`pill ${status === "ready" ? "done" : status === "missing" ? "failed" : "running"}`}>{status}</span></div>
          <p>{item.detail}</p>
          {item.missing.length ? <ul>{item.missing.map((missing) => <li key={missing}>{missing}</li>)}</ul> : <em>{item.ready ? "Required inputs are present." : "No explicit missing inputs, but output is still unavailable."}</em>}
        </article>;
      })}
    </div>
  </div>;
}
function AnalyticsBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="analytics-block"><strong>{title}</strong><div>{children}</div></div>;
}
function MetricLine({ label, value }: { label: string; value: string }) {
  return <p className="metric-line"><span>{label}</span><b>{value}</b></p>;
}
function ExposureBars({ values }: { values: AnyRecord }) {
  const entries = Object.entries(values)
    .map(([label, value]) => ({ label, value: num(value) ?? 0 }))
    .filter((item) => item.value > 0)
    .sort((left, right) => right.value - left.value)
    .slice(0, 4);
  if (!entries.length) return <span className="muted-copy">No exposure data yet.</span>;
  return <div className="exposure-bars">{entries.map((item) => <div key={item.label}><p><span>{item.label}</span><b>{percent(item.value)}</b></p><div className="bar"><span style={{ width: `${Math.max(item.value * 100, 2)}%` }} /></div></div>)}</div>;
}
function InsightList({ items }: { items: string[] }) {
  return <div className="analytics-insights">{items.slice(0, 3).map((item) => <p key={item}>{item}</p>)}</div>;
}
function AggregatePanel() {
  return <section className="card">
    <div className="card-heading"><div><p className="eyebrow">Combined view</p><h2>All portfolios</h2></div><span>aggregate</span></div>
    <div className="aggregate-note">
      <strong>Portfolio totals are rolled up across every active local portfolio.</strong>
      <span>Analytics are still calculated per portfolio for now, so the combined view focuses on value, holdings, and recent ledger activity.</span>
    </div>
  </section>;
}
function Loading({ compact = false }: { compact?: boolean }) { return <div className={compact ? "loading compact" : "loading"}><RefreshCw />Loading dashboard data</div>; }
function ErrorPanel({ error }: { error: Error }) { return <div className="error-panel"><strong>Unable to load data</strong><span>{error.message}</span></div>; }
function EmptyRow({ text }: { text: string }) { return <div className="empty-row">{text}</div>; }

function portfolioSelectionFromParam(value: string | null): number | "all" | null {
  if (value === "all") return "all";
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}
