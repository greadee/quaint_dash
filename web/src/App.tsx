import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Building2,
  ChartNoAxesCombined,
  CircleDollarSign,
  Database,
  LayoutDashboard,
  Menu,
  Plus,
  RefreshCw,
  WalletCards,
  X,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";

const money = (value: number | null | undefined, currency = "CAD") =>
  value == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-CA", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
const percent = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
const number = (value: number | null | undefined, digits = 2) =>
  value == null ? "Unavailable" : value.toFixed(digits);

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="app-shell">
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand"><ChartNoAxesCombined size={21} /><span>Quaint Dash</span></div>
        <button className="mobile-close" onClick={() => setMenuOpen(false)}><X /></button>
        <nav>
          <NavLink to="/" end><LayoutDashboard />Overview</NavLink>
          <NavLink to="/brokers"><Building2 />Brokers</NavLink>
          <NavLink to="/operations"><Database />Operations</NavLink>
        </nav>
        <div className="sidebar-note"><span className="status-dot" />Local API connected</div>
      </aside>
      <main>
        <header>
          <button className="mobile-menu" onClick={() => setMenuOpen(true)}><Menu /></button>
          <div><p className="eyebrow">Personal finance workspace</p><strong>Investment dashboard</strong></div>
          <div className="avatar">CP</div>
        </header>
        <Routes>
          <Route path="/" element={<PortfolioOverview />} />
          <Route path="/assets/:assetId" element={<AssetPage />} />
          <Route path="/brokers" element={<BrokersPage />} />
          <Route path="/operations" element={<OperationsPage />} />
        </Routes>
      </main>
    </div>
  );
}

function PortfolioOverview() {
  const client = useQueryClient();
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const selected = portfolios.data?.find((item) => item.portfolio_id === selectedId) ?? portfolios.data?.[0];
  const positions = useQuery({
    queryKey: ["positions", selected?.portfolio_id],
    queryFn: () => api.positions(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const transactions = useQuery({
    queryKey: ["transactions", selected?.portfolio_id],
    queryFn: () => api.transactions(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const analytics = useQuery({
    queryKey: ["portfolio-analytics", selected?.portfolio_id],
    queryFn: () => api.portfolioAnalytics(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const create = useMutation({
    mutationFn: api.createPortfolio,
    onSuccess: (item) => {
      setNewName("");
      setSelectedId(item.portfolio_id);
      client.invalidateQueries({ queryKey: ["portfolios"] });
    },
  });

  if (portfolios.isLoading) return <Loading />;
  if (portfolios.error) return <ErrorPanel error={portfolios.error} />;
  if (!selected) {
    return (
      <section className="empty-state">
        <WalletCards size={42} />
        <h1>Create your first portfolio</h1>
        <p>Start with a named portfolio, then import transactions through the CLI or a linked broker.</p>
        <form onSubmit={(event) => { event.preventDefault(); create.mutate(newName); }}>
          <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="Long-term investments" />
          <button className="primary" disabled={!newName.trim()}><Plus size={17} />Create portfolio</button>
        </form>
      </section>
    );
  }

  const gain = selected.unrealized_gain ?? 0;
  const gainRate = selected.book_cost ? gain / selected.book_cost : null;
  return (
    <div className="page">
      <div className="page-title">
        <div><p className="eyebrow">Portfolio overview</p><h1>{selected.name}</h1></div>
        <select value={selected.portfolio_id} onChange={(event) => setSelectedId(Number(event.target.value))}>
          {portfolios.data?.map((item) => <option key={item.portfolio_id} value={item.portfolio_id}>{item.name}</option>)}
        </select>
      </div>
      <section className="metric-grid">
        <Metric icon={<CircleDollarSign />} label="Market value" value={money(selected.market_value, selected.base_ccy)} />
        <Metric icon={<ArrowUpRight />} label="Unrealized gain" value={money(gain, selected.base_ccy)} detail={percent(gainRate)} positive={gain >= 0} />
        <Metric icon={<WalletCards />} label="Book cost" value={money(selected.book_cost, selected.base_ccy)} />
        <Metric icon={<Activity />} label="Active holdings" value={String(selected.position_count)} />
      </section>
      <section className="insight-grid">
        <AnalyticsPanel payload={analytics.data} isLoading={analytics.isLoading} />
        <section className="card">
          <div className="card-heading"><div><p className="eyebrow">Recent ledger activity</p><h2>Transactions</h2></div><span>{transactions.data?.total ?? 0} total</span></div>
          {transactions.isLoading ? <Loading compact /> : transactions.data?.items.length ? (
            <div className="mini-list">
              {transactions.data.items.map((item) => (
                <article key={item.transaction_id}>
                  <div><strong>{item.transaction_type}</strong><span>{new Date(item.timestamp).toLocaleDateString()}</span></div>
                  <span>{item.asset_id ?? item.currency ?? "cash"}</span>
                  <b>{item.cash_amount != null ? money(item.cash_amount, item.currency ?? selected.base_ccy) : number(item.quantity, 4)}</b>
                </article>
              ))}
            </div>
          ) : <EmptyRow text="No transactions recorded yet." />}
        </section>
      </section>
      <section className="card holdings-card">
        <div className="card-heading"><div><p className="eyebrow">Composition</p><h2>Holdings</h2></div><span>{positions.data?.length ?? 0} positions</span></div>
        {positions.isLoading ? <Loading compact /> : positions.data?.length ? (
          <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Value</th><th>Weight</th><th>Book cost</th><th>Gain</th></tr></thead>
          <tbody>{positions.data.map((item) => <tr key={item.asset_id}>
            <td><Link className="asset-link" to={`/assets/${item.asset_id}`}><strong>{item.symbol}</strong><span>{item.name ?? item.asset_type ?? "Asset"}</span></Link></td>
            <td>{money(item.market_value, selected.base_ccy)}</td><td>{percent(item.weight)}</td>
            <td>{money(item.book_cost, selected.base_ccy)}</td>
            <td className={(item.unrealized_gain ?? 0) >= 0 ? "positive" : "negative"}>{money(item.unrealized_gain, selected.base_ccy)}</td>
          </tr>)}</tbody></table></div>
        ) : <EmptyRow text="No active positions yet." />}
      </section>
    </div>
  );
}

function AssetPage() {
  const { assetId = "" } = useParams();
  const asset = useQuery({ queryKey: ["asset", assetId], queryFn: () => api.asset(assetId) });
  const prices = useQuery({ queryKey: ["prices", assetId], queryFn: () => api.prices(assetId) });
  if (asset.isLoading) return <Loading />;
  if (asset.error) return <ErrorPanel error={asset.error} />;
  return <div className="page">
    <div className="page-title"><div><p className="eyebrow">{asset.data?.sector ?? "Asset detail"}</p><h1>{asset.data?.symbol} <small>{asset.data?.name}</small></h1></div><strong className="asset-price">{money(asset.data?.latest_price, asset.data?.currency)}</strong></div>
    <section className="card chart-card"><div className="card-heading"><div><p className="eyebrow">Last 365 observations</p><h2>Price history</h2></div></div>
      <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={prices.data}><defs><linearGradient id="price" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5da78b" stopOpacity={0.4}/><stop offset="100%" stopColor="#5da78b" stopOpacity={0}/></linearGradient></defs><XAxis dataKey="date" hide/><YAxis hide domain={["dataMin", "dataMax"]}/><Tooltip/><Area type="monotone" dataKey="close" stroke="#5da78b" fill="url(#price)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
    </section>
    <section className="detail-grid"><div className="card"><p className="eyebrow">Classification</p><h2>{asset.data?.industry ?? "Not classified"}</h2><p>{asset.data?.country ?? "Country unavailable"} - {asset.data?.currency}</p></div><div className="card"><p className="eyebrow">Business profile</p><p>{asset.data?.description ?? "No company description has been ingested yet."}</p></div></section>
  </div>;
}

function BrokersPage() {
  const client = useQueryClient();
  const [userKey, setUserKey] = useState("");
  const [message, setMessage] = useState("");
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
    onError: (error) => setMessage((error as Error).message),
  });
  const portal = useMutation({
    mutationFn: api.brokerPortal,
    onSuccess: (result) => {
      setMessage("Portal URL created. Complete the read-only connection in the opened tab.");
      window.open(result.url, "_blank", "noopener,noreferrer");
    },
    onError: (error) => setMessage((error as Error).message),
  });
  const sync = useMutation({
    mutationFn: api.brokerSync,
    onSuccess: () => {
      setMessage("Broker sync finished.");
      refreshBroker();
    },
    onError: (error) => setMessage((error as Error).message),
  });
  const mapper = useMutation({
    mutationFn: ({ accountId, portfolioId }: { accountId: string; portfolioId: number }) =>
      api.mapBrokerAccount(accountId, portfolioId),
    onSuccess: () => {
      setMessage("Account mapping saved.");
      refreshBroker();
    },
    onError: (error) => setMessage((error as Error).message),
  });
  const importer = useMutation({
    mutationFn: api.importBrokerTransactions,
    onSuccess: (result) => {
      setMessage(`Import finished: ${JSON.stringify(result)}`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
    },
    onError: (error) => setMessage((error as Error).message),
  });
  const isBusy = register.isPending || portal.isPending || sync.isPending || mapper.isPending || importer.isPending;
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Read-only connections</p><h1>Broker accounts</h1></div><button className="primary" onClick={() => importer.mutate()} disabled={isBusy || !accounts.data?.length}><RefreshCw size={17}/>Import transactions</button></div>
    <section className="broker-grid">
      <div className="card broker-control">
        <div className="card-heading"><div><p className="eyebrow">SnapTrade lifecycle</p><h2>Connect or refresh</h2></div></div>
        <div className="broker-form">
          <label>Broker user key<input value={userKey} onChange={(event) => setUserKey(event.target.value)} placeholder="connor-local" /></label>
          <div className="actions">
            <button onClick={() => register.mutate(userKey)} disabled={isBusy || !userKey.trim()}>Register</button>
            <button onClick={() => portal.mutate(userKey)} disabled={isBusy || !userKey.trim()}>Open portal</button>
            <button className="primary" onClick={() => sync.mutate(userKey)} disabled={isBusy || !userKey.trim()}><RefreshCw size={17}/>Sync</button>
          </div>
          {message ? <p className="action-message">{message}</p> : <p className="action-message muted">Credentials stay with SnapTrade. This app only stores read-only sync state.</p>}
        </div>
      </div>
      <div className="card">
        <div className="card-heading"><div><p className="eyebrow">Provider state</p><h2>Connections</h2></div><span>{connections.data?.length ?? 0} linked</span></div>
        {connections.isLoading ? <Loading compact /> : connections.data?.length ? <div className="mini-list">{connections.data.map((item) => <article key={item.provider_connection_id}><div><strong>{item.institution_name}</strong><span>{item.provider}</span></div><span>{item.provider_connection_id}</span><b><span className={`pill ${item.status}`}>{item.status}</span></b></article>)}</div> : <EmptyRow text="No broker connections synced yet." />}
      </div>
    </section>
    <section className="card"><div className="card-heading"><h2>Connected accounts</h2><span>{accounts.data?.length ?? 0} account(s)</span></div>{accounts.isLoading ? <Loading compact /> : accounts.data?.length ? <div className="account-grid">{accounts.data.map((item) => <article className="account" key={item.provider_account_id}><Building2/><div><strong>{item.account_name ?? item.provider_account_id}</strong><span>{item.account_type ?? "Broker account"} - {item.provider_account_id}</span><label className="mapping-label">Portfolio<select value={item.portfolio_id ?? ""} onChange={(event) => { if (event.target.value) mapper.mutate({ accountId: item.provider_account_id, portfolioId: Number(event.target.value) }); }} disabled={isBusy || !portfolios.data?.length}><option value="">Unmapped</option>{portfolios.data?.map((portfolio) => <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>)}</select></label></div><b>{money(item.balance, item.currency ?? "CAD")}</b></article>)}</div> : <EmptyRow text="No synced broker accounts." />}</section>
  </div>;
}

function OperationsPage() {
  const client = useQueryClient();
  const [status, setStatus] = useState("");
  const [domain, setDomain] = useState("");
  const jobs = useQuery({ queryKey: ["jobs", status, domain], queryFn: () => api.ingestionJobs(status, domain) });
  const schedule = useMutation({ mutationFn: api.scheduleIngestion, onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }) });
  const run = useMutation({ mutationFn: api.runIngestion, onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }) });
  const retry = useMutation({ mutationFn: () => api.retryFailedIngestion(domain), onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }) });
  const isBusy = schedule.isPending || run.isPending || retry.isPending;
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1></div><div className="actions"><button onClick={() => jobs.refetch()} disabled={jobs.isFetching}><RefreshCw size={17}/>Refresh</button><button onClick={() => window.confirm("Schedule due ingestion jobs now?") && schedule.mutate()} disabled={isBusy}>Schedule due</button><button onClick={() => window.confirm("Move failed jobs back to pending?") && retry.mutate()} disabled={isBusy}>Retry failed</button><button className="primary" onClick={() => window.confirm("Run one pending ingestion job now?") && run.mutate()} disabled={isBusy}><RefreshCw size={17}/>Run next job</button></div></div>
    <section className="card"><div className="card-heading"><h2>Ingestion jobs</h2><span>{jobs.data?.length ?? 0} shown</span></div>
      <div className="filter-row">
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Any</option><option value="pending">Pending</option><option value="running">Running</option><option value="done">Done</option><option value="failed">Failed</option></select></label>
        <label>Domain<select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">Any</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
      </div>
      {jobs.error ? <ErrorPanel error={jobs.error} /> : jobs.isLoading ? <Loading compact /> : (
        <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Dataset</th><th>Domain</th><th>Status</th><th>Attempts</th><th>Error</th></tr></thead><tbody>{jobs.data?.map((job) => <tr key={job.job_id}><td>{job.asset_id ?? "Global"}</td><td>{job.dataset}</td><td>{job.domain}</td><td><span className={`pill ${job.status}`}>{job.status}</span></td><td>{job.attempt_count}</td><td className="job-error" title={job.error_message ?? ""}>{job.error_message ?? "-"}</td></tr>)}</tbody></table></div>
      )}
      {!jobs.isLoading && !jobs.data?.length ? <EmptyRow text="No ingestion jobs match the current filters." /> : null}
    </section>
  </div>;
}

function Metric({ icon, label, value, detail, positive }: { icon: React.ReactNode; label: string; value: string; detail?: string; positive?: boolean }) {
  return <article className="metric card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong>{detail && <span className={positive ? "positive" : "negative"}>{detail}</span>}</article>;
}
function AnalyticsPanel({ payload, isLoading }: { payload?: Record<string, unknown>; isLoading: boolean }) {
  const report = payload?.report as Record<string, unknown> | undefined;
  const performance = report?.performance as Record<string, number | null> | undefined;
  const risk = report?.risk as Record<string, number | null> | undefined;
  const valuation = report?.valuation as Record<string, number | null> | undefined;
  const missing = report?.missing_inputs as string[] | undefined;
  return <section className="card">
    <div className="card-heading"><div><p className="eyebrow">Phase 3 analytics</p><h2>Portfolio signals</h2></div><span>{payload?.schema_version as string ?? "loading"}</span></div>
    {isLoading ? <Loading compact /> : (
      <div className="signal-grid">
        <Signal label="Modified Dietz" value={percent(performance?.modified_dietz_return)} />
        <Signal label="Volatility" value={percent(risk?.annualized_volatility)} />
        <Signal label="Sharpe" value={number(risk?.sharpe_ratio)} />
        <Signal label="Expected CAGR" value={percent(valuation?.weighted_expected_cagr)} />
        {missing?.length ? <p className="missing-inputs">Missing inputs: {missing.slice(0, 3).join(", ")}</p> : <p className="missing-inputs good">Analytics inputs look complete for this report.</p>}
      </div>
    )}
  </section>;
}
function Signal({ label, value }: { label: string; value: string }) {
  return <div className="signal"><span>{label}</span><strong>{value}</strong></div>;
}
function Loading({ compact = false }: { compact?: boolean }) { return <div className={compact ? "loading compact" : "loading"}><RefreshCw />Loading dashboard data</div>; }
function ErrorPanel({ error }: { error: Error }) { return <div className="error-panel"><strong>Unable to load data</strong><span>{error.message}</span></div>; }
function EmptyRow({ text }: { text: string }) { return <div className="empty-row">{text}</div>; }
