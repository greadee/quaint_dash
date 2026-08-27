import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, MessageSquare, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type RetailSentimentOverviewItem, type StockRankingItem } from "../api";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar } from "../pageFeatureStore";
import { usePageFeature } from "../pageFeatureHooks";
import { money, percent, signedNumber } from "./routeFormatters";
import { EmptyRow, ErrorPanel, Loading, Metric } from "./routeShared";

export function RetailSentimentPage() {
  const [view, setView] = useState<"holdings" | "popular">("holdings");
  const [ratingDirection, setRatingDirection] = useState<"buy" | "sell">("buy");
  const [includeRetailRatings, setIncludeRetailRatings] = useState(false);
  const showSummary = usePageFeature("retailSentiment", "retailSentiment.summary");
  const showHoldings = usePageFeature("retailSentiment", "retailSentiment.holdings");
  const showPopular = usePageFeature("retailSentiment", "retailSentiment.popular");
  const showMethodology = usePageFeature("retailSentiment", "retailSentiment.methodology");
  const sentiment = useQuery({
    queryKey: ["retail-sentiment-overview"],
    queryFn: () => api.retailSentimentOverview(30),
    placeholderData: (previous) => previous,
  });
  const ratings = useQuery({
    queryKey: ["retail-sentiment-ratings", ratingDirection, includeRetailRatings],
    queryFn: () => api.stockRankings({
      factor: "aggregate",
      universe: "tracked",
      direction: ratingDirection,
      include_retail_sentiment: includeRetailRatings,
      limit: 10,
    }),
    placeholderData: (previous) => previous,
  });
  useEffect(() => {
    document.title = "Retail Sentiment - Quaint Dash";
  }, []);
  const holdings = sentiment.data?.holdings ?? [];
  const popular = sentiment.data?.popular ?? [];
  const activeItems = view === "holdings" ? holdings : popular;
  return <div className="page retail-sentiment-page">
    <div className="page-title">
      <div>
        <p className="eyebrow">Social attention</p>
        <h1>Retail sentiment</h1>
        <p className="page-subtitle">Reddit and X crowd tone for held stocks and high-activity names. It is a light social layer beside analyst, news, institutional, earnings, and price evidence.</p>
      </div>
      <div className="actions">
        <PageLayoutButton pageId="retailSentiment" />
        <PageFeatureMenu pageId="retailSentiment" />
        <button onClick={() => sentiment.refetch()} disabled={sentiment.isFetching}><RefreshCw size={17} />Refresh</button>
        <Link className="button-link" to="/operations"><MessageSquare size={17} />Ingestion</Link>
        <Link className="button-link primary" to="/signals?include_retail_sentiment=true"><Activity size={17} />Signals with retail</Link>
      </div>
    </div>
    <PageLayoutToolbar pageId="retailSentiment" />
    <OptionalFeaturesEmpty pageId="retailSentiment" />
    {sentiment.isError ? <ErrorPanel error={sentiment.error} /> : null}
    {showSummary ? <LayoutWidget pageId="retailSentiment" widgetId="retailSentiment.summary"><section className="metric-grid">
      <Metric icon={<MessageSquare />} label="Held stocks with social data" value={`${sentiment.data?.summary.holding_with_sentiment_count ?? 0}`} detail={`${sentiment.data?.summary.holding_count ?? 0} held stocks scanned`} positive />
      <Metric icon={<TrendingUp />} label="Popular social names" value={`${sentiment.data?.summary.popular_count ?? 0}`} detail={`${sentiment.data?.summary.total_recent_posts ?? 0} recent posts counted`} positive />
      <Metric icon={<Activity />} label="Decision weight" value="Optional" detail="10% add-on when enabled" positive />
    </section></LayoutWidget> : null}
    <div className="segmented-control retail-view-toggle" aria-label="Retail sentiment view">
      <button className={view === "holdings" ? "active" : ""} onClick={() => setView("holdings")}>Holdings</button>
      <button className={view === "popular" ? "active" : ""} onClick={() => setView("popular")}>Popular stocks</button>
    </div>
    {sentiment.isLoading ? <Loading /> : null}
    {view === "holdings" && showHoldings ? <LayoutWidget pageId="retailSentiment" widgetId="retailSentiment.holdings"><RetailSentimentTable title="Your holdings" items={holdings} empty="No held stocks have retail sentiment rows yet. Schedule retail sentiment ingestion from Operations." /></LayoutWidget> : null}
    {view === "popular" && showPopular ? <LayoutWidget pageId="retailSentiment" widgetId="retailSentiment.popular"><RetailSentimentTable title="Popular stocks by social activity" items={popular} empty="No popular retail sentiment rows are stored yet. Run retail sentiment ingestion to populate this view." /></LayoutWidget> : null}
    <RatingsAddOnPanel
      direction={ratingDirection}
      includeRetail={includeRetailRatings}
      items={ratings.data?.items ?? []}
      isLoading={ratings.isLoading}
      methodology={ratings.data?.methodology}
      onDirection={setRatingDirection}
      onIncludeRetail={setIncludeRetailRatings}
    />
    {activeItems.length ? <section className="retail-sentiment-cards" aria-label="Retail sentiment details">
      {activeItems.slice(0, 6).map((item) => <RetailSentimentCard key={`${view}-${item.asset_id}`} item={item} />)}
    </section> : null}
    {showMethodology ? <LayoutWidget pageId="retailSentiment" widgetId="retailSentiment.methodology"><p className="signal-methodology">{sentiment.data?.methodology ?? "Retail sentiment methodology loads with the server response."}</p></LayoutWidget> : null}
  </div>;
}

function RatingsAddOnPanel({
  direction,
  includeRetail,
  items,
  isLoading,
  methodology,
  onDirection,
  onIncludeRetail,
}: {
  direction: "buy" | "sell";
  includeRetail: boolean;
  items: StockRankingItem[];
  isLoading: boolean;
  methodology?: string;
  onDirection: (value: "buy" | "sell") => void;
  onIncludeRetail: (value: boolean) => void;
}) {
  return <section className="card retail-ratings-panel">
    <div className="section-heading">
      <div><p className="eyebrow">Buy/sell ratings</p><h2>Retail as an optional add-on</h2></div>
      <div className="actions">
        <div className="segmented-control compact" aria-label="Rating direction">
          <button className={direction === "buy" ? "active" : ""} onClick={() => onDirection("buy")}>Buy</button>
          <button className={direction === "sell" ? "active" : ""} onClick={() => onDirection("sell")}>Sell</button>
        </div>
        <label className="checkbox-label"><input type="checkbox" checked={includeRetail} onChange={(event) => onIncludeRetail(event.target.checked)} />Include retail</label>
      </div>
    </div>
    {methodology ? <p className="rating-methodology">{methodology}</p> : null}
    {isLoading ? <Loading compact /> : items.length ? <div className="table-wrap">
      <table className="data-table retail-rating-table">
        <thead><tr><th>Stock</th><th>Rating</th><th>Score</th><th>Confidence</th><th>Retail component</th></tr></thead>
        <tbody>
          {items.map((item) => {
            const retail = item.components.find((component) => component.name.toLowerCase().includes("retail"));
            return <tr key={`${direction}-${item.asset_id}`}>
              <td><strong>{item.symbol}</strong><span>{item.name ?? item.asset_id}</span></td>
              <td>{item.action}</td>
              <td>{signedNumber(item.score, 1)}</td>
              <td>{percent(item.confidence)}</td>
              <td>{retail ? signedNumber(retail.score, 1) : "Excluded"}</td>
            </tr>;
          })}
        </tbody>
      </table>
    </div> : <EmptyRow text="No tracked stock ratings are available yet." />}
  </section>;
}

function RetailSentimentTable({ title, items, empty }: { title: string; items: RetailSentimentOverviewItem[]; empty: string }) {
  return <section className="card">
    <div className="section-heading">
      <div><p className="eyebrow">Retail sentiment</p><h2>{title}</h2></div>
    </div>
    {items.length ? <div className="table-wrap">
      <table className="data-table retail-sentiment-table">
        <thead><tr><th>Stock</th><th>Social tone</th><th>Confidence</th><th>Posts</th><th>Bull / Bear</th><th>1d shift</th><th>Position</th></tr></thead>
        <tbody>
          {items.map((item) => <tr key={item.asset_id}>
            <td><strong>{item.symbol}</strong><span>{item.name ?? item.asset_id}</span></td>
            <td><SentimentBadge item={item} /></td>
            <td>{percent(item.confidence)}</td>
            <td>{item.source_count}<span>{item.reddit_post_count} reddit · {item.x_post_count} x</span></td>
            <td>{item.bullish_count} / {item.bearish_count}</td>
            <td>{signedNumber(item.sentiment_momentum_1d, 2)}</td>
            <td>{item.is_held ? money(item.market_value, "CAD") : item.is_watchlisted ? "Watchlist" : "Not held"}</td>
          </tr>)}
        </tbody>
      </table>
    </div> : <EmptyRow text={empty} />}
  </section>;
}

function RetailSentimentCard({ item }: { item: RetailSentimentOverviewItem }) {
  return <article className="retail-sentiment-card card">
    <div className="retail-card-title">
      <div><p className="eyebrow">{item.is_held ? "Holding" : item.is_watchlisted ? "Watchlist" : "Popular"}</p><h3>{item.symbol}</h3><span>{item.name ?? item.asset_id}</span></div>
      <SentimentBadge item={item} />
    </div>
    <div className="retail-meter" aria-label={`${item.symbol} retail sentiment score`}>
      <span style={{ width: `${Math.min(100, Math.max(0, ((item.retail_sentiment_score ?? 0) + 1) * 50))}%` }} />
    </div>
    <div className="retail-card-stats">
      <span><b>{percent(item.retail_sentiment_score)}</b> score</span>
      <span><b>{percent(item.confidence)}</b> confidence</span>
      <span><b>{item.source_count}</b> posts</span>
    </div>
    {item.portfolio_names.length ? <p className="retail-portfolios">Held in {item.portfolio_names.join(", ")}</p> : null}
    {item.latest_posts.length ? <ul className="retail-post-list">
      {item.latest_posts.map((post) => <li key={`${item.asset_id}-${post.provider}-${post.title}`}>
        {post.url ? <a href={post.url} target="_blank" rel="noreferrer">{post.title ?? post.source_name}</a> : <span>{post.title ?? post.source_name}</span>}
        <small>{post.source_name} · {post.comment_count ?? 0} comments</small>
      </li>)}
    </ul> : <p className="muted">No mapped post details stored for this ticker.</p>}
  </article>;
}

function SentimentBadge({ item }: { item: RetailSentimentOverviewItem }) {
  const score = item.retail_sentiment_score ?? 0;
  const className = score > 0.12 ? "positive" : score < -0.12 ? "negative" : "neutral";
  const Icon = score < -0.12 ? TrendingDown : TrendingUp;
  return <span className={`sentiment-badge ${className}`}><Icon size={14} />{item.sentiment_label}</span>;
}
