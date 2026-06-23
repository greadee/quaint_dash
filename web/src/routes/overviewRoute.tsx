import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Building2, CircleDollarSign, Database, WalletCards } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { money, percent } from "./routeFormatters";
import { EmptyRow, Loading, Metric } from "./routeShared";
import type { MoverDefault } from "./routeTypes";

const MARKET_REFRESH_REFETCH_MS = 60_000;

export function OverviewPage({ moverDefault }: { moverDefault: MoverDefault }) {
  const [showAllMovers, setShowAllMovers] = useState(moverDefault === "all");
  const updates = useQuery({ queryKey: ["overview-updates"], queryFn: api.overviewUpdates, refetchInterval: MARKET_REFRESH_REFETCH_MS });
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: api.portfolios, refetchInterval: MARKET_REFRESH_REFETCH_MS });
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
