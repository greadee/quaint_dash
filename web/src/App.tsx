import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Building2,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleDollarSign,
  Database,
  ExternalLink,
  KeyRound,
  LayoutDashboard,
  Menu,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  WalletCards,
  X,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Position } from "./api";

const money = (value: number | null | undefined, currency = "CAD") =>
  value == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-CA", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
const percent = (value: number | null | undefined) =>
  value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
const number = (value: number | null | undefined, digits = 2) =>
  value == null ? "Unavailable" : value.toFixed(digits);
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

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="app-shell">
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand"><ChartNoAxesCombined size={21} /><span>Quaint Dash</span></div>
        <button className="mobile-close" onClick={() => setMenuOpen(false)}><X /></button>
        <nav>
          <NavLink to="/" end><LayoutDashboard />Overview</NavLink>
          <NavLink to="/portfolios"><WalletCards />Portfolios</NavLink>
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
          <Route path="/" element={<OverviewPage />} />
          <Route path="/portfolios" element={<PortfoliosPage />} />
          <Route path="/assets/:assetId" element={<AssetPage />} />
          <Route path="/brokers" element={<BrokersPage />} />
          <Route path="/operations" element={<OperationsPage />} />
        </Routes>
      </main>
    </div>
  );
}

function OverviewPage() {
  const updates = useQuery({ queryKey: ["overview-updates"], queryFn: api.overviewUpdates });
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const brokers = useQuery({ queryKey: ["broker-accounts"], queryFn: api.brokerAccounts });
  const jobs = useQuery({ queryKey: ["jobs", "failed", ""], queryFn: () => api.ingestionJobs("failed") });
  const portfolioCount = portfolios.data?.length ?? 0;
  const mappedAccounts = brokers.data?.filter((account) => account.portfolio_id != null).length ?? 0;
  const failedJobs = jobs.data?.length ?? 0;
  const topMover = updates.data?.price_movers[0];

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
    <section className="update-grid">
      <section className="card">
        <div className="card-heading"><div><p className="eyebrow">Price movers</p><h2>Holdings moving most</h2></div><span>{updates.data?.mover_count ?? 0} tracked</span></div>
        {updates.isLoading ? <Loading compact /> : updates.data?.price_movers.length ? <div className="mover-list">{updates.data.price_movers.map((item) => <Link to={`/assets/${item.asset_id}`} className="mover-row" key={item.asset_id}><div><strong>{item.symbol}</strong><span>{item.name ?? "Held asset"}</span></div><b className={(item.change_percent ?? 0) >= 0 ? "positive" : "negative"}>{percent(item.change_percent)}</b><span>{money(item.market_value)}</span></Link>)}</div> : <EmptyRow text="No price movers yet. Add price history for held assets to light this up." />}
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

function PortfoliosPage() {
  const client = useQueryClient();
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios });
  const [selectedId, setSelectedId] = useState<number | "all" | null>(null);
  const [groupBy, setGroupBy] = useState<TrancheDimension>("sector");
  const [newName, setNewName] = useState("");
  const isAggregate = selectedId === "all";
  const aggregate = useQuery({
    queryKey: ["portfolio-aggregate"],
    queryFn: api.aggregatePortfolio,
    enabled: isAggregate && Boolean(portfolios.data?.length),
  });
  const selectedPortfolio = portfolios.data?.find((item) => item.portfolio_id === selectedId) ?? portfolios.data?.[0];
  const selected = isAggregate ? aggregate.data : selectedPortfolio;
  const positions = useQuery({
    queryKey: ["positions", isAggregate ? "all" : selected?.portfolio_id],
    queryFn: () => isAggregate ? api.aggregatePositions() : api.positions(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const transactions = useQuery({
    queryKey: ["transactions", isAggregate ? "all" : selected?.portfolio_id],
    queryFn: () => isAggregate ? api.aggregateTransactions() : api.transactions(selected!.portfolio_id),
    enabled: Boolean(selected),
  });
  const analytics = useQuery({
    queryKey: ["portfolio-analytics", selected?.portfolio_id],
    queryFn: () => api.portfolioAnalytics(selected!.portfolio_id),
    enabled: Boolean(selected) && !isAggregate,
  });
  const create = useMutation({
    mutationFn: api.createPortfolio,
    onSuccess: (item) => {
      setNewName("");
      setSelectedId(item.portfolio_id);
      client.invalidateQueries({ queryKey: ["portfolios"] });
    },
  });
  const deletePortfolio = useMutation({
    mutationFn: api.deletePortfolio,
    onSuccess: () => {
      setSelectedId(null);
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["portfolio-aggregate"] });
      client.invalidateQueries({ queryKey: ["positions"] });
      client.invalidateQueries({ queryKey: ["transactions"] });
      client.invalidateQueries({ queryKey: ["broker-accounts"] });
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
  if (!selected) return <Loading />;

  const gain = selected.unrealized_gain ?? 0;
  const gainRate = selected.book_cost ? gain / selected.book_cost : null;
  const tranches = groupPositions(positions.data ?? [], groupBy);
  return (
    <div className="page">
      <div className="page-title">
        <div><p className="eyebrow">Portfolio workspace</p><h1>{selected.name}</h1><p className="page-subtitle">Organize one portfolio or all holdings into intuitive tranches by sector, geography, industry, asset type, or currency.</p></div>
        <div className="overview-actions">
          <select value={isAggregate ? "all" : selected.portfolio_id} onChange={(event) => setSelectedId(event.target.value === "all" ? "all" : Number(event.target.value))}>
            <option value="all">All portfolios</option>
            {portfolios.data?.map((item) => <option key={item.portfolio_id} value={item.portfolio_id}>{item.name}</option>)}
          </select>
          {!isAggregate ? <button className="danger" disabled={deletePortfolio.isPending} onClick={() => window.confirm(`Delete ${selected.name} from the overview? This removes its local transactions, mappings, and positions.`) && deletePortfolio.mutate(selected.portfolio_id)}><Trash2 size={16}/>Delete</button> : null}
        </div>
      </div>
      <section className="metric-grid">
        <Metric icon={<CircleDollarSign />} label="Market value" value={money(selected.market_value, selected.base_ccy)} />
        <Metric icon={<ArrowUpRight />} label="Unrealized gain" value={money(gain, selected.base_ccy)} detail={percent(gainRate)} positive={gain >= 0} />
        <Metric icon={<WalletCards />} label="Book cost" value={money(selected.book_cost, selected.base_ccy)} />
        <Metric icon={<Activity />} label="Active holdings" value={String(selected.position_count)} />
      </section>
      <section className="insight-grid">
        {isAggregate ? <AggregatePanel /> : <AnalyticsPanel payload={analytics.data} isLoading={analytics.isLoading} />}
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
      <section className="card tranche-card">
        <div className="card-heading">
          <div><p className="eyebrow">Tranches</p><h2>Organize holdings by exposure</h2></div>
          <label className="tranche-selector">Group by<select value={groupBy} onChange={(event) => setGroupBy(event.target.value as TrancheDimension)}><option value="sector">Sector</option><option value="country">Geography</option><option value="industry">Industry</option><option value="asset_type">Asset type</option><option value="currency">Currency</option></select></label>
        </div>
        {positions.isLoading ? <Loading compact /> : tranches.length ? <div className="tranche-grid">{tranches.map((group) => <article className="tranche" key={group.label}><div><strong>{group.label}</strong><span>{group.count} holding{group.count === 1 ? "" : "s"}</span></div><b>{money(group.marketValue, selected.base_ccy)}</b><div className="bar"><span style={{ width: `${Math.max(group.weight * 100, 2)}%` }} /></div><em>{percent(group.weight)} of selected scope</em></article>)}</div> : <EmptyRow text="No tranche data yet. Add holdings with sector, industry, country, or currency metadata." />}
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
  const [userKey, setUserKey] = useState("default");
  const [providerUserId, setProviderUserId] = useState("");
  const [userSecret, setUserSecret] = useState("");
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
    mutationFn: api.brokerPortal,
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
    mutationFn: api.importBrokerTransactions,
    onSuccess: (result) => {
      setMessage(`Import finished: ${JSON.stringify(result)}`);
      client.invalidateQueries({ queryKey: ["portfolios"] });
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
          <button className="primary" onClick={() => portal.mutate(userKey)} disabled={isBusy || !userKeyReady}><ExternalLink size={17}/>Open broker portal</button>
          <button onClick={() => sync.mutate(userKey)} disabled={isBusy || !userKeyReady}><RefreshCw size={17}/>Sync after linking</button>
        </div>
      </div>
      {message ? <p className="action-message">{message}</p> : <p className="action-message muted"><ShieldCheck size={16}/>Read-only connection. No trading permissions are requested or stored.</p>}
      {portalUrl ? <a className="portal-link" href={portalUrl} target="_blank" rel="noreferrer">Portal did not open? Click here to continue linking.</a> : null}
      <details className="advanced-broker">
        <summary>Advanced: I already have SnapTrade user credentials</summary>
        <div className="advanced-grid">
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
        </div>
      </div>
    </section>
    <section className="card"><div className="card-heading"><div><p className="eyebrow">Step 3</p><h2>Choose where each account goes</h2></div><span>{accountCount} account(s)</span></div>{accounts.isLoading ? <Loading compact /> : accounts.data?.length ? <div className="account-grid">{accounts.data.map((item) => <article className="account" key={item.provider_account_id}><Building2/><div><strong>{item.account_name ?? item.provider_account_id}</strong><span>{item.account_type ?? "Broker account"}</span><span className="muted-id">{item.provider_account_id}</span><label className="mapping-label">Local portfolio<select value={item.portfolio_id ?? ""} onChange={(event) => { if (event.target.value) mapper.mutate({ accountId: item.provider_account_id, portfolioId: Number(event.target.value) }); }} disabled={isBusy || !portfolios.data?.length}><option value="">Choose portfolio</option>{portfolios.data?.map((portfolio) => <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>)}</select><em>Mapping updates holdings right away.</em></label></div><div className="account-value"><b>{money(item.balance, item.currency ?? "CAD")}</b><span className={item.portfolio_id ? "pill done" : "pill"}>{item.portfolio_id ? "mapped" : "needs map"}</span></div></article>)}</div> : <EmptyRow text="No synced broker accounts yet. Open the portal, connect a brokerage, then sync accounts." />}</section>
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
