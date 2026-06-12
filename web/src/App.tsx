import { Component, useEffect, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleDollarSign,
  Database,
  ExternalLink,
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
  Trash2,
  WalletCards,
  X,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useLocation, useParams, useSearchParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  api,
  type AssetActivity,
  type AssetHolding,
  type AssetSearchResult,
  type BenchmarkAssociation,
  type BenchmarkDefaultResponse,
  type BenchmarkExposure,
  type BenchmarkIndexSummary,
  type BenchmarkPricePoint,
  type ComparisonAsset,
  type HoldingSignal,
  type IngestionReadiness,
  type IngestionBackgroundStatus,
  type Portfolio,
  type Position,
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
type SignalTimeframe = "1d" | "1w" | "1m" | "1y";
type AppNotification = { id: number; tone: "success" | "error"; message: string };
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
const signalTimeframes: { value: SignalTimeframe; label: string }[] = [
  { value: "1d", label: "1 day" },
  { value: "1w", label: "Week" },
  { value: "1m", label: "Month" },
  { value: "1y", label: "Year" },
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
            <Route path="/portfolios" element={<PortfoliosPage notify={notify} />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/benchmarks" element={<BenchmarkBrowserPage notify={notify} />} />
            <Route path="/asset/:assetId" element={<AssetPage notify={notify} />} />
            <Route path="/brokers" element={<BrokersPage />} />
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
  const [signalTimeframe, setSignalTimeframe] = useState<SignalTimeframe>("1d");
  const updates = useQuery({ queryKey: ["overview-updates"], queryFn: api.overviewUpdates });
  const signals = useQuery({
    queryKey: ["holding-signals", signalTimeframe],
    queryFn: () => api.holdingSignals(signalTimeframe),
  });
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const brokers = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const jobs = useQuery({ queryKey: ["jobs", "failed", ""], queryFn: () => api.ingestionJobs("failed") });
  const portfolioCount = portfolios.data?.length ?? 0;
  const mappedAccounts = brokers.data?.filter((account) => account.portfolio_id != null).length ?? 0;
  const failedJobs = jobs.data?.length ?? 0;
  const topMover = updates.data?.price_movers[0];
  const movers = updates.data?.price_movers ?? [];
  const visibleMovers = showAllMovers ? movers : movers.slice(0, 8);

  useEffect(() => {
    setShowAllMovers(moverDefault === "all");
  }, [moverDefault]);

  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Today at a glance</p><h1>Overview</h1><p className="page-subtitle">The landing page is now for updates, attention items, and fresh market context. Portfolio organization lives in its own workspace.</p></div>
      <div className="actions"><Link className="button-link" to="/portfolios"><WalletCards size={17}/>Open portfolios</Link><Link className="button-link primary" to="/brokers"><Building2 size={17}/>Broker setup</Link></div>
    </div>
    <section className="metric-grid">
      <Metric icon={<CircleDollarSign />} label="Total market value" value={money(updates.data?.total_market_value)} />
      <Metric icon={<Activity />} label="Active holdings" value={String(updates.data?.position_count ?? 0)} />
      <Metric icon={<WalletCards />} label="Portfolios" value={String(portfolioCount)} />
      <Metric icon={<Database />} label="Attention items" value={String(failedJobs)} detail={failedJobs ? "failed jobs" : "data healthy"} positive={!failedJobs} />
    </section>
    <section className="card holding-signals-card">
      <div className="card-heading">
        <div><p className="eyebrow">Signal rank</p><h2>Buy and sell signals</h2></div>
        <div className="card-tools signal-timeframes">
          {signalTimeframes.map((item) => (
            <button
              key={item.value}
              className={signalTimeframe === item.value ? "selected" : ""}
              onClick={() => setSignalTimeframe(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {signals.isLoading ? <Loading compact /> : signals.data?.items.length ? (
        <>
          <div className="holding-signal-list">
            {signals.data.items.map((item, index) => <HoldingSignalRow item={item} rank={index + 1} key={item.asset_id} />)}
          </div>
          <p className="signal-methodology">{signals.data.methodology}</p>
        </>
      ) : <EmptyRow text="No holding signals yet. Add held assets with daily price history to calculate ranked signals." />}
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
    <section className="update-grid slim">
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Next best action</p><h2>{mappedAccounts ? "Review imported portfolios" : "Connect a broker account"}</h2></div><span>{mappedAccounts} mapped</span></div>
        <div className="broker-help">
          <p>{mappedAccounts ? "Your broker accounts are mapped. Use Portfolios to review exposure by sector, geography, industry, and currency." : "Connect a broker, sync accounts, and map them to local portfolios so the dashboard can organize everything automatically."}</p>
          <Link className="portal-link" to={mappedAccounts ? "/portfolios" : "/brokers"}>{mappedAccounts ? "Open portfolio workspace" : "Start broker setup"}</Link>
        </div>
      </section>
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Largest move</p><h2>{topMover?.symbol ?? "Waiting for prices"}</h2></div><span>{topMover ? percent(topMover.change_percent) : "no data"}</span></div>
        <div className="broker-help">
          <p>{topMover ? `${topMover.name ?? topMover.asset_id} moved ${money(topMover.change)} since the prior close and represents ${percent(topMover.weight)} of tracked holdings.` : "Once held assets have at least two prices, this card will show what changed most."}</p>
        </div>
      </section>
    </section>
  </div>;
}

function HoldingSignalRow({ item, rank }: { item: HoldingSignal; rank: number }) {
  const tone = item.action.includes("Sell") ? "sell" : item.action.includes("Buy") ? "buy" : "hold";
  const scoreWidth = Math.min(100, Math.max(0, item.signal_strength));
  return (
    <Link to={`/asset/${item.asset_id}`} className={`holding-signal-row ${tone}`}>
      <div className="signal-rank">{rank}</div>
      <div className="signal-asset">
        <strong>{item.symbol}</strong>
        <span>{item.name ?? "Held asset"}</span>
      </div>
      <div className={`signal-action ${tone}`}>
        <b>{item.action}</b>
        <span>{signedNumber(item.signal_score, 0)} score</span>
      </div>
      <div className="signal-meter" aria-label={`Signal strength ${item.signal_strength}`}>
        <span style={{ width: `${scoreWidth}%` }} />
      </div>
      <div className="signal-facts">
        <span>{percent(item.return_value)} return</span>
        <span>{percent(item.confidence)} confidence</span>
        <span>{item.data_points} closes</span>
        <span>{money(item.market_value, item.currency)}</span>
      </div>
      <div className="signal-components">
        {item.components.map((component) => (
          <span title={component.detail} key={component.name}>
            <b>{component.name}</b>
            {component.contribution == null ? "missing" : signedNumber(component.contribution, 0)}
          </span>
        ))}
      </div>
    </Link>
  );
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
  const [analyticsBenchmark, setAnalyticsBenchmark] = useState("");
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
    queryKey: ["portfolio-analytics", selected?.portfolio_id, analyticsBenchmark],
    queryFn: () => api.portfolioAnalytics(selected!.portfolio_id, analyticsBenchmark.trim().toUpperCase() || undefined),
    enabled: Boolean(selected) && !isAggregate,
  });
  const defaultBenchmark = useQuery({
    queryKey: ["portfolio-default-benchmark", selected?.portfolio_id],
    queryFn: () => api.portfolioDefaultBenchmark(selected!.portfolio_id),
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
            benchmark={analyticsBenchmark}
            onBenchmarkChange={setAnalyticsBenchmark}
            defaultBenchmark={defaultBenchmark.data}
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
    <div className="card-heading"><div><p className="eyebrow">{label}</p><h2>{asset.symbol}</h2></div><span>{asset.sector ?? "Unclassified"}</span></div>
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
    <div className="card-heading"><div><p className="eyebrow">Company metrics</p><h2>{right ? `${left.symbol} vs ${right.symbol}` : `${left.symbol} full metric view`}</h2></div><span>{right ? "left / right / spread" : "left ticker only"}</span></div>
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
const weightToRatio = (value: number | null | undefined) => value == null ? null : value > 1 ? value / 100 : value;
const weightLabel = (value: number | null | undefined) => value == null ? "Unavailable" : value > 1 ? `${value.toFixed(1)}%` : percent(value);
const gapLabel = (value: number | null | undefined, label: string) => {
  if (value == null) return "Unavailable";
  const direction = value >= 0 ? "above" : "below";
  return `${percent(Math.abs(value))} ${direction} ${label}`;
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

function BenchmarkBrowserPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [currency, setCurrency] = useState("");
  const [coreOnly, setCoreOnly] = useState(false);
  const selectedId = params.get("index") ?? "";
  const benchmarks = useQuery({
    queryKey: ["benchmarks", query, category, currency, coreOnly],
    queryFn: () => api.benchmarks({
      q: query.trim() || undefined,
      category: category || undefined,
      currency: currency.trim().toUpperCase() || undefined,
      is_core: coreOnly ? true : undefined,
      is_active: true,
      limit: 100,
    }),
  });
  const firstId = benchmarks.data?.[0]?.index_id ?? "";
  const activeId = selectedId || firstId;
  const detail = useQuery({
    queryKey: ["benchmark-detail", activeId],
    queryFn: () => api.benchmark(activeId),
    enabled: Boolean(activeId),
  });
  const prices = useQuery({
    queryKey: ["benchmark-prices", activeId],
    queryFn: () => api.benchmarkPrices(activeId, { limit: 365 }),
    enabled: Boolean(activeId),
  });
  const metrics = useQuery({
    queryKey: ["benchmark-metrics", activeId],
    queryFn: () => api.benchmarkMetrics(activeId, 120),
    enabled: Boolean(activeId),
  });
  const exposures = useQuery({
    queryKey: ["benchmark-exposures", activeId],
    queryFn: () => api.benchmarkExposures(activeId),
    enabled: Boolean(activeId),
  });
  const constituents = useQuery({
    queryKey: ["benchmark-constituents", activeId],
    queryFn: () => api.benchmarkConstituents(activeId, { limit: 10 }),
    enabled: Boolean(activeId),
  });
  const seed = useMutation({
    mutationFn: api.seedBenchmarks,
    onSuccess: () => {
      notify("Core benchmarks seeded.");
      client.invalidateQueries({ queryKey: ["benchmarks"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const refreshOne = useMutation({
    mutationFn: ({ id, jobType }: { id: string; jobType: "daily_price" | "composition" | "metrics" }) =>
      api.refreshBenchmark(id, { job_type: jobType }),
    onSuccess: (_result, variables) => {
      notify(`${variables.id} ${variables.jobType.replace(/_/g, " ")} refresh started.`);
      client.invalidateQueries({ queryKey: ["benchmarks"] });
      client.invalidateQueries({ queryKey: ["benchmark-detail"] });
      client.invalidateQueries({ queryKey: ["benchmark-prices"] });
      client.invalidateQueries({ queryKey: ["benchmark-metrics"] });
      client.invalidateQueries({ queryKey: ["benchmark-exposures"] });
      client.invalidateQueries({ queryKey: ["benchmark-constituents"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const refreshBroad = useMutation({
    mutationFn: () => api.refreshBenchmarks({ category: "core_geo", job_type: "daily_price", lookback_days: 10 }),
    onSuccess: () => {
      notify("Core benchmark daily refresh started.");
      client.invalidateQueries({ queryKey: ["benchmarks"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const selectBenchmark = (id: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("index", id);
      return next;
    }, { replace: true });
  };
  const latestMetric = metrics.data?.at(-1);

  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Benchmark index browser</p><h1>Benchmarks</h1><p className="page-subtitle">Browse seeded indexes, inspect price and composition coverage, and run explicit refresh actions.</p></div>
      <div className="actions">
        <button disabled={seed.isPending} onClick={() => seed.mutate({ scope: "core" })}><Database size={16}/>Seed core</button>
        <button disabled={refreshBroad.isPending} onClick={() => window.confirm("Refresh daily prices for all core benchmarks?") && refreshBroad.mutate()}><RefreshCw size={16}/>Core daily</button>
      </div>
    </div>
    <section className="card benchmark-layout">
      <div className="benchmark-list-panel">
        <div className="benchmark-filters">
          <label>Search<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="SP500" /></label>
          <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All</option><option value="core_geo">Core geo</option><option value="sector">Sector</option><option value="industry">Industry</option><option value="theme">Theme</option></select></label>
          <label>Currency<input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} placeholder="USD" /></label>
          <label className="check-row compact"><input type="checkbox" checked={coreOnly} onChange={(event) => setCoreOnly(event.target.checked)} />Core</label>
        </div>
        {benchmarks.isLoading ? <Loading compact /> : benchmarks.data?.length ? <div className="benchmark-table">
          <table>
            <thead><tr><th>Index</th><th>Category</th><th>Return</th><th>Data</th></tr></thead>
            <tbody>{benchmarks.data.map((item) => <tr key={item.index_id} className={activeId === item.index_id ? "selected-row" : ""} onClick={() => selectBenchmark(item.index_id)}>
              <td><button className="link-button" onClick={(event) => { event.stopPropagation(); selectBenchmark(item.index_id); }}>{item.index_id}</button><span>{item.index_name}</span></td>
              <td>{item.index_category}<span>{item.currency}</span></td>
              <td>{percent(item.return_252d)}<span>{percent(item.volatility_252d_ann)} vol</span></td>
              <td><BenchmarkQuality item={item} /></td>
            </tr>)}</tbody>
          </table>
        </div> : <EmptyRow text="No benchmarks match the current filters." />}
      </div>
      <div className="benchmark-detail-panel">
        {!activeId ? <EmptyRow text="Select a benchmark to inspect details." /> : detail.error ? <ErrorPanel error={detail.error} /> : detail.isLoading ? <Loading compact /> : detail.data ? <>
          <div className="card-heading benchmark-detail-heading">
            <div><p className="eyebrow">{detail.data.index_category}</p><h2>{detail.data.index_name}</h2></div>
            <span>{detail.data.index_id}</span>
          </div>
          <div className="benchmark-summary-grid">
            <Signal label="Latest close" value={money(detail.data.latest_close, detail.data.currency)} />
            <Signal label="1 day" value={percent(detail.data.return_1d)} />
            <Signal label="252 days" value={percent(detail.data.return_252d)} />
            <Signal label="Volatility" value={percent(detail.data.volatility_252d_ann)} />
          </div>
          <div className="benchmark-chart"><BenchmarkPriceChart prices={prices.data ?? []} /></div>
          <div className="benchmark-actions">
            <button disabled={refreshOne.isPending} onClick={() => refreshOne.mutate({ id: detail.data.index_id, jobType: "daily_price" })}><RefreshCw size={16}/>Prices</button>
            <button disabled={refreshOne.isPending} onClick={() => refreshOne.mutate({ id: detail.data.index_id, jobType: "metrics" })}><Activity size={16}/>Metrics</button>
            <button disabled={refreshOne.isPending} onClick={() => window.confirm(`Refresh composition for ${detail.data.index_id}?`) && refreshOne.mutate({ id: detail.data.index_id, jobType: "composition" })}><Database size={16}/>Composition</button>
          </div>
          <div className="benchmark-data-grid">
            <AnalyticsBlock title="Metric range">
              <MetricLine label="Latest metric" value={detail.data.latest_metric_date ?? "Unavailable"} />
              <MetricLine label="5 day return" value={percent(latestMetric?.return_5d)} />
              <MetricLine label="YTD return" value={percent(latestMetric?.return_ytd)} />
              <MetricLine label="52w drawdown" value={percent(latestMetric?.drawdown_from_52w_high)} />
            </AnalyticsBlock>
            <AnalyticsBlock title="Composition">
              <MetricLine label="Snapshot" value={detail.data.latest_composition_date ?? "Unavailable"} />
              <MetricLine label="Constituents" value={String(detail.data.constituent_count ?? "Unavailable")} />
              <MetricLine label="Quality" value={detail.data.composition_quality ?? "Unavailable"} />
              <MetricLine label="Symbols" value={String(detail.data.symbols.length)} />
            </AnalyticsBlock>
            <AnalyticsBlock title="Sync state">
              {Object.values(detail.data.sync_state).length ? Object.values(detail.data.sync_state).slice(0, 4).map((item) => <MetricLine key={item.job_type} label={item.job_type} value={item.last_error ? "error" : item.last_success_date ?? "pending"} />) : <span className="muted-copy">No sync state yet.</span>}
            </AnalyticsBlock>
          </div>
          <div className="benchmark-data-grid wide">
            <AnalyticsBlock title="Exposures">
              <BenchmarkExposureBars exposures={exposures.data ?? []} />
            </AnalyticsBlock>
            <AnalyticsBlock title="Top constituents">
              {constituents.data?.items.length ? constituents.data.items.map((item) => <MetricLine key={item.constituent_symbol} label={item.constituent_symbol} value={percent(weightToRatio(item.weight_pct))} />) : <span className="muted-copy">No constituents available.</span>}
            </AnalyticsBlock>
          </div>
          {detail.data.last_error ? <div className="benchmark-error">{detail.data.last_error}</div> : null}
        </> : null}
      </div>
    </section>
  </div>;
}

function BenchmarkQuality({ item }: { item: BenchmarkIndexSummary }) {
  const stale = item.latest_metric_date ? (Date.now() - new Date(item.latest_metric_date).getTime()) / 86400000 > 14 : true;
  const label = item.last_error ? "error" : !item.latest_close ? "no price" : !item.latest_composition_date ? "no composition" : item.composition_quality === "proxy" ? "proxy" : stale ? "stale" : "ready";
  const tone = item.last_error ? "failed" : label === "ready" ? "done" : "running";
  return <span className={`pill ${tone}`}>{label}</span>;
}

function BenchmarkPriceChart({ prices }: { prices: BenchmarkPricePoint[] }) {
  if (!prices.length) return <EmptyRow text="No price history has been ingested for this benchmark." />;
  return <ResponsiveContainer width="100%" height="100%">
    <AreaChart data={prices}>
      <defs><linearGradient id="benchmarkPrice" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#497d8f" stopOpacity={0.35}/><stop offset="100%" stopColor="#497d8f" stopOpacity={0}/></linearGradient></defs>
      <XAxis dataKey="date" hide />
      <YAxis hide domain={["dataMin", "dataMax"]} />
      <Tooltip />
      <Area type="monotone" dataKey="close" stroke="#497d8f" fill="url(#benchmarkPrice)" strokeWidth={2} />
    </AreaChart>
  </ResponsiveContainer>;
}

function BenchmarkExposureBars({ exposures }: { exposures: BenchmarkExposure[] }) {
  const shown = exposures.filter((item) => item.dimension_type === "sector").slice(0, 6);
  if (!shown.length) return <span className="muted-copy">No exposure snapshot available.</span>;
  return <div className="exposure-bars">{shown.map((item) => {
    const width = Math.max(2, Math.min(100, item.weight_pct));
    return <div key={`${item.dimension_type}-${item.dimension_value}`}><p><span>{item.dimension_value}</span><b>{weightLabel(item.weight_pct)}</b></p><div className="bar"><span style={{ width: `${width}%` }} /></div></div>;
  })}</div>;
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

function BrokersPage() {
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
    onSuccess: () => setMessage("Broker user registered. Open the portal next to connect accounts."),
    onError: (error) => setMessage(friendlyBrokerError(error)),
  });
  const saveExisting = useMutation({
    mutationFn: () => api.saveExistingBrokerUser(userKey, providerUserId, userSecret),
    onSuccess: () => {
      setUserSecret("");
      setMessage("Existing SnapTrade user saved locally. You can now open portal or sync.");
    },
    onError: (error) => setMessage(friendlyBrokerError(error)),
  });
  const portal = useMutation({
    mutationFn: () => api.brokerPortal({
      user_key: userKey.trim(),
      broker: portalBroker.trim() || null,
      reconnect: portalReconnect.trim() || null,
    }),
    onSuccess: (result) => {
      setPortalUrl(result.url);
      setMessage("Portal URL created. Use the link below if the new tab did not open.");
      window.open(result.url, "_blank", "noopener,noreferrer");
    },
    onError: (error) => setMessage(friendlyBrokerError(error)),
  });
  const sync = useMutation({
    mutationFn: api.brokerSync,
    onSuccess: () => {
      setMessage("Broker sync finished.");
      refreshBroker();
    },
    onError: (error) => setMessage(friendlyBrokerError(error)),
  });
  const mapper = useMutation({
    mutationFn: ({ accountId, portfolioId }: { accountId: string; portfolioId: number }) =>
      api.mapBrokerAccount(accountId, portfolioId),
    onSuccess: () => {
      setMessage("Account mapping saved and portfolio holdings updated.");
      refreshBroker();
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (error) => setMessage(friendlyBrokerError(error)),
  });
  const importer = useMutation({
    mutationFn: () => api.importBrokerTransactions(importPortfolioId ? Number(importPortfolioId) : null),
    onSuccess: (result) => {
      setMessage(`Import finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
    },
    onError: (error) => setMessage(friendlyBrokerError(error)),
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
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Step 3</p><h2>Choose where each account goes</h2></div><span>{accountCount} account(s)</span></div>{accounts.isLoading ? <Loading compact /> : accounts.data?.length ? <div className="account-grid">{accounts.data.map((item) => <article className="account" key={item.provider_account_id}><Building2/><div><strong>{item.account_name ?? item.provider_account_id}</strong><span>{[item.provider, item.account_type, item.currency].filter(Boolean).join(" - ") || "Broker account"}</span><span className="muted-id">{item.provider_account_id} - {item.provider_connection_id}</span><label className="mapping-label">Local portfolio<select value={item.portfolio_id ?? ""} onChange={(event) => { if (event.target.value) mapper.mutate({ accountId: item.provider_account_id, portfolioId: Number(event.target.value) }); }} disabled={isBusy || !portfolios.data?.length}><option value="">Choose portfolio</option>{portfolios.data?.map((portfolio) => <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>)}</select><em>Mapping updates holdings right away.</em></label></div><div className="account-value"><b>{money(item.balance, item.currency ?? "CAD")}</b><span className={item.portfolio_id ? "pill done" : "pill"}>{item.portfolio_id ? "mapped" : "needs map"}</span></div></article>)}</div> : <EmptyRow text="No synced broker accounts yet. Open the portal, connect a brokerage, then sync accounts." />}</section>
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
  const [runDomain, setRunDomain] = useState("all");
  const [runMaxJobs, setRunMaxJobs] = useState("1");
  const [retryMaxJobs, setRetryMaxJobs] = useState("25");
  const [message, setMessage] = useState("");
  type ScheduleOverride = { pipeline?: string; assetId?: string; maxAssets?: string; years?: string; pricesOnly?: boolean };
  const jobs = useQuery({
    queryKey: ["jobs", status, domain, jobLimit],
    queryFn: () => api.ingestionJobs(status, domain, boundedInt(jobLimit, 100, 1, 500)),
  });
  const background = useQuery({
    queryKey: ["ingestion-background-status"],
    queryFn: api.ingestionBackgroundStatus,
  });
  const readiness = useQuery({
    queryKey: ["ingestion-readiness"],
    queryFn: api.ingestionReadiness,
  });
  const schedule = useMutation({
    mutationFn: (override?: ScheduleOverride) => api.scheduleIngestion({
      pipeline: override?.pipeline ?? pipeline,
      asset_id: (override?.assetId ?? assetId.trim()) || null,
      max_assets: boundedInt(override?.maxAssets ?? maxAssets, 25, 1, 100),
      years: boundedInt(override?.years ?? years, 10, 1, 30),
      prices_only: override?.pricesOnly ?? pricesOnly,
    }),
    onSuccess: (result) => {
      setMessage(`Scheduled: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
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
  const isBusy = schedule.isPending || run.isPending || retry.isPending || clearHistory.isPending;
  const actionError = schedule.error ?? run.error ?? retry.error ?? clearHistory.error;
  const scheduleAsset = (selectedAssetId: string) => {
    setPipeline("all");
    setAssetId(selectedAssetId);
    schedule.mutate({ pipeline: "all", assetId: selectedAssetId, maxAssets: "1" });
  };
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1><p className="page-subtitle">Background due work keeps routine data moving. Manual controls remain here for backfills, retries, provider-sensitive refreshes, and explicit runs.</p></div><div className="actions"><button onClick={() => { jobs.refetch(); background.refetch(); readiness.refetch(); }} disabled={jobs.isFetching || background.isFetching || readiness.isFetching}><RefreshCw size={17}/>Refresh</button><button className="danger" onClick={() => window.confirm("Clear ingestion job history and sync status rows? Market data and broker connections will stay intact.") && clearHistory.mutate()} disabled={isBusy}><Trash2 size={17}/>Clear history</button><button className="primary" onClick={() => window.confirm("Run pending ingestion jobs with these options?") && run.mutate()} disabled={isBusy}><RefreshCw size={17}/>Run jobs</button></div></div>
    <IngestionBackgroundCard status={background.data} isLoading={background.isLoading} error={background.error} />
    <IngestionReadinessCard readiness={readiness.data} isLoading={readiness.isLoading} error={readiness.error} onScheduleAsset={scheduleAsset} isBusy={isBusy} />
    <section className="card operations-control">
      <div className="card-heading"><div><p className="eyebrow">Manual controls</p><h2>Ingestion actions</h2></div><span>{isBusy ? "working" : "ready"}</span></div>
      <div className="operations-grid">
        <div className="control-panel">
          <strong>Schedule jobs</strong>
          <div className="control-fields">
            <label>Pipeline<select value={pipeline} onChange={(event) => setPipeline(event.target.value)}><option value="all">All</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
            <label>Asset ID<input value={assetId} onChange={(event) => setAssetId(event.target.value.toUpperCase())} placeholder="Optional ticker" /></label>
            <label>Max assets<input type="number" min="1" max="100" value={maxAssets} onChange={(event) => setMaxAssets(event.target.value)} /></label>
            <label>Years<input type="number" min="1" max="30" value={years} onChange={(event) => setYears(event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={pricesOnly} onChange={(event) => setPricesOnly(event.target.checked)} />Prices only</label>
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
}: {
  status?: IngestionBackgroundStatus;
  isLoading: boolean;
  error: Error | null;
}) {
  const stateLabel = status?.enabled ? (status.running ? "running" : "enabled") : "disabled";
  return <section className="card operations-background">
    <div className="card-heading">
      <div><p className="eyebrow">Background due work</p><h2>Routine ingestion worker</h2></div>
      <span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Last scheduled" value={isLoading ? "Loading" : formatCount(status?.last_schedule_count, "job")} />
        <Signal label="Last completed" value={isLoading ? "Loading" : formatCount(status?.last_completed_count, "job")} />
        <Signal label="Schedule cadence" value={status ? formatDuration(status.schedule_interval_seconds) : "Unavailable"} />
        <Signal label="Run cadence" value={status ? `${formatDuration(status.run_interval_seconds)} / ${status.max_jobs_per_tick} job cap` : "Unavailable"} />
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
      <span>{isLoading ? "loading" : `${readiness?.ready_count ?? 0}/${readiness?.total ?? 0} ready`}</span>
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
  benchmark,
  onBenchmarkChange,
  defaultBenchmark,
}: {
  payload?: Record<string, unknown>;
  isLoading: boolean;
  benchmark: string;
  onBenchmarkChange: (value: string) => void;
  defaultBenchmark?: BenchmarkDefaultResponse;
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
        <BenchmarkPicker value={benchmark} onChange={onBenchmarkChange} defaultBenchmark={defaultBenchmark} />
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
            <MetricLine label="Margin of safety" value={percent(num(valuation?.weighted_margin_of_safety))} />
            <MetricLine label="Undervalued weight" value={percent(num(valuation?.undervalued_weight))} />
            <MetricLine label="Fair value weight" value={percent(num(valuation?.fair_value_weight))} />
            <MetricLine label="Overvalued weight" value={percent(num(valuation?.overvalued_weight))} />
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
    <div className="data-health-heading"><div><p className="eyebrow">Analytics data health</p><strong>Model input readiness</strong></div><span>{items.filter((item) => item.missing.length === 0 && item.ready).length}/{items.length} ready</span></div>
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
