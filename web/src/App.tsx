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
    <section className="detail-grid"><div className="card"><p className="eyebrow">Classification</p><h2>{asset.data?.industry ?? "Not classified"}</h2><p>{asset.data?.country ?? "Country unavailable"} · {asset.data?.currency}</p></div><div className="card"><p className="eyebrow">Business profile</p><p>{asset.data?.description ?? "No company description has been ingested yet."}</p></div></section>
  </div>;
}

function BrokersPage() {
  const client = useQueryClient();
  const accounts = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const importer = useMutation({ mutationFn: api.importBrokerTransactions, onSuccess: () => client.invalidateQueries() });
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Read-only connections</p><h1>Broker accounts</h1></div><button className="primary" onClick={() => importer.mutate()}><RefreshCw size={17}/>Import transactions</button></div>
    <section className="card"><div className="card-heading"><h2>Connected accounts</h2></div>{accounts.data?.length ? <div className="account-grid">{accounts.data.map((item) => <article className="account" key={item.provider_account_id}><Building2/><div><strong>{item.account_name ?? item.provider_account_id}</strong><span>{item.account_type ?? "Broker account"}</span></div><b>{money(item.balance, item.currency ?? "CAD")}</b></article>)}</div> : <EmptyRow text="No synced broker accounts." />}</section>
  </div>;
}

function OperationsPage() {
  const client = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.ingestionJobs });
  const schedule = useMutation({ mutationFn: api.scheduleIngestion, onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }) });
  const run = useMutation({ mutationFn: api.runIngestion, onSuccess: () => client.invalidateQueries({ queryKey: ["jobs"] }) });
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1></div><div className="actions"><button onClick={() => schedule.mutate()}>Schedule due</button><button className="primary" onClick={() => run.mutate()}><RefreshCw size={17}/>Run next job</button></div></div>
    <section className="card"><div className="card-heading"><h2>Ingestion jobs</h2><span>{jobs.data?.length ?? 0} shown</span></div><div className="table-wrap"><table><thead><tr><th>Asset</th><th>Dataset</th><th>Domain</th><th>Status</th><th>Attempts</th></tr></thead><tbody>{jobs.data?.map((job) => <tr key={job.job_id}><td>{job.asset_id ?? "Global"}</td><td>{job.dataset}</td><td>{job.domain}</td><td><span className={`pill ${job.status}`}>{job.status}</span></td><td>{job.attempt_count}</td></tr>)}</tbody></table></div></section>
  </div>;
}

function Metric({ icon, label, value, detail, positive }: { icon: React.ReactNode; label: string; value: string; detail?: string; positive?: boolean }) {
  return <article className="metric card"><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong>{detail && <span className={positive ? "positive" : "negative"}>{detail}</span>}</article>;
}
function Loading({ compact = false }: { compact?: boolean }) { return <div className={compact ? "loading compact" : "loading"}><RefreshCw />Loading dashboard data</div>; }
function ErrorPanel({ error }: { error: Error }) { return <div className="error-panel"><strong>Unable to load data</strong><span>{error.message}</span></div>; }
function EmptyRow({ text }: { text: string }) { return <div className="empty-row">{text}</div>; }
