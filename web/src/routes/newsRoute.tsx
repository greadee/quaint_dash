import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Bookmark, BookmarkCheck, ExternalLink, RefreshCw, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type NewsArticle, type NewsFeed } from "../api";
import { EmptyRow, ErrorPanel, Loading, Pager, Signal, TabBar } from "./routeShared";
import { formatTimestamp, percent } from "./routeFormatters";

type NewsPreset = "all" | "breaking" | "earnings" | "corporate" | "macro" | "press";
type Density = "comfortable" | "compact" | "ultra";

const presets: { value: NewsPreset; label: string }[] = [
  { value: "all", label: "All News" },
  { value: "breaking", label: "Breaking" },
  { value: "earnings", label: "Earnings" },
  { value: "corporate", label: "Corporate Actions" },
  { value: "macro", label: "Macro" },
  { value: "press", label: "Press Releases" },
];

const corporateCategories = new Set(["merger_acquisition", "buyback", "dividend", "stock_split", "capital_raise"]);
const macroCategories = new Set(["macro", "central_bank", "economic_data", "government_policy"]);

export function NewsTerminalPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [visibleFeed, setVisibleFeed] = useState<NewsFeed | null>(null);
  const [pendingFeed, setPendingFeed] = useState<NewsFeed | null>(null);
  const [density, setDensity] = useState<Density>((params.get("density") as Density | null) ?? "compact");
  const preset = (params.get("preset") as NewsPreset | null) ?? "all";
  const q = params.get("q") ?? "";
  const provider = params.get("provider") ?? "";
  const category = params.get("category") ?? presetCategory(preset);
  const assetId = params.get("asset_id") ?? "";
  const portfolioId = params.get("portfolio_id") ?? "";
  const sort = ((params.get("sort") as "recency" | "relevance" | null) ?? "recency");
  const offset = Number(params.get("offset") ?? "0");
  const limit = density === "ultra" ? 50 : 25;
  const filters = {
    q: q || undefined,
    provider: provider || undefined,
    category: category || undefined,
    asset_id: assetId || undefined,
    portfolio_id: portfolioId ? Number(portfolioId) : undefined,
    breaking: preset === "breaking" ? true : undefined,
    press_release: preset === "press" ? true : undefined,
    sort,
    limit,
    offset,
  };
  const feed = useQuery({
    queryKey: ["news", filters],
    queryFn: () => api.news(filters),
    refetchInterval: 60_000,
  });
  const providers = useQuery({ queryKey: ["news-providers"], queryFn: api.newsProviders });
  const categories = useQuery({ queryKey: ["news-categories"], queryFn: api.newsCategories });
  const displayItems = useMemo(
    () => (visibleFeed?.items ?? []).filter((article) => categoryMatchesPreset(article, preset)),
    [preset, visibleFeed],
  );
  const selected = useMemo(() => displayItems.find((item) => item.article_id === selectedId) ?? displayItems[0] ?? null, [selectedId, displayItems]);
  const markRead = useMutation({
    mutationFn: api.markNewsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["news"] }),
  });
  const saveStory = useMutation({
    mutationFn: (article: NewsArticle) => article.is_saved ? api.unsaveNewsArticle(article.article_id) : api.saveNewsArticle(article.article_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["news"] }),
  });

  useEffect(() => {
    if (!feed.data) return;
    if (!visibleFeed) {
      setVisibleFeed(feed.data);
      return;
    }
    const currentFirst = visibleFeed.items[0]?.article_id;
    const nextFirst = feed.data.items[0]?.article_id;
    if (currentFirst && nextFirst && currentFirst !== nextFirst && offset === 0) {
      setPendingFeed(feed.data);
      return;
    }
    setVisibleFeed(feed.data);
  }, [feed.data, offset, visibleFeed]);

  const setParam = (key: string, value: string) => setParams((current) => {
    const next = new URLSearchParams(current);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "offset") next.delete("offset");
    return next;
  });
  const applyPending = () => {
    if (pendingFeed) setVisibleFeed(pendingFeed);
    setPendingFeed(null);
  };
  const selectStory = (article: NewsArticle) => {
    setSelectedId(article.article_id);
    if (!article.is_read) markRead.mutate(article.article_id);
  };

  if (feed.isLoading && !visibleFeed) return <Loading />;
  if (feed.error) return <ErrorPanel error={feed.error} />;

  return <div className="page news-terminal-page">
    <div className="page-title">
      <div><p className="eyebrow">Provider-normalized market news</p><h1>News Terminal</h1><p className="page-subtitle">Ranked financial news with provider attribution, asset mapping, clustering, and saved/read state.</p></div>
      <div className="actions">
        <button onClick={() => feed.refetch()}><RefreshCw size={16} />Refresh</button>
      </div>
    </div>
    <section className="news-toolbar card">
      <label className="search-box"><Search size={16} /><input value={q} onChange={(event) => setParam("q", event.target.value)} placeholder="Search headlines, tickers, companies" /></label>
      <select aria-label="Provider" value={provider} onChange={(event) => setParam("provider", event.target.value)}>
        <option value="">All providers</option>
        {(providers.data ?? []).map((item) => <option key={item.provider_code} value={item.provider_code}>{item.provider_name}</option>)}
      </select>
      <select aria-label="Category" value={category} onChange={(event) => setParam("category", event.target.value)}>
        <option value="">All categories</option>
        {(categories.data ?? []).map((item) => <option key={item.category_code} value={item.category_code}>{item.category_name}</option>)}
      </select>
      <select aria-label="Sort" value={sort} onChange={(event) => setParam("sort", event.target.value)}>
        <option value="recency">Recency</option>
        <option value="relevance">Relevance</option>
      </select>
      <div className="segmented-control compact" aria-label="Story density">
        {(["comfortable", "compact", "ultra"] as Density[]).map((item) => <button key={item} className={density === item ? "active" : ""} onClick={() => { setDensity(item); setParam("density", item); }}>{item}</button>)}
      </div>
    </section>
    <TabBar tabs={presets} selected={preset} onSelect={(value) => setParam("preset", value)} label="News presets" />
    {pendingFeed ? <button className="new-story-banner" onClick={applyPending}><Bell size={16} />New stories available</button> : null}
    <section className={`news-terminal-layout density-${density}`}>
      <aside className="news-filter-panel card">
        <div className="card-heading"><div><p className="eyebrow">Feed status</p><h2>Coverage</h2></div></div>
        <div className="signal-grid">
          <Signal label="Stories" value={String(visibleFeed?.total ?? 0)} />
          <Signal label="Providers" value={String(providers.data?.length ?? 0)} />
          <Signal label="Categories" value={String(categories.data?.filter((item) => item.article_count > 0).length ?? 0)} />
          <Signal label="Updated" value={formatTimestamp(visibleFeed?.generated_at)} />
        </div>
      </aside>
      <main className="news-stream card" aria-label="News stream">
        {displayItems.length ? displayItems.map((article) => <NewsRow key={article.article_id} article={article} selected={selected?.article_id === article.article_id} onSelect={() => selectStory(article)} onSave={() => saveStory.mutate(article)} density={density} />) : <EmptyRow text="No stories match the current filters." />}
        {visibleFeed ? <Pager total={visibleFeed.total} limit={visibleFeed.limit} offset={visibleFeed.offset} onChange={(nextOffset) => setParam("offset", String(nextOffset))} /> : null}
      </main>
      <aside className="news-detail-panel card">
        {selected ? <NewsDetail article={selected} onSave={() => saveStory.mutate(selected)} /> : <EmptyRow text="Select a story to inspect source, mappings, categories, and related coverage." />}
      </aside>
    </section>
  </div>;
}

export function NewsRow({ article, selected, onSelect, onSave, density = "compact" }: { article: NewsArticle; selected?: boolean; onSelect: () => void; onSave: () => void; density?: Density }) {
  const primaryCategory = article.categories[0]?.category_name ?? "General";
  const primaryAsset = article.assets[0];
  return <article className={`news-row ${selected ? "active" : ""} ${article.is_read ? "read" : ""}`} onClick={onSelect}>
    <button className="news-row-main" type="button">
      <div className="news-row-headline"><strong>{article.headline}</strong>{article.is_breaking ? <span className="pill danger">Breaking</span> : null}{article.is_press_release ? <span className="pill">PR</span> : null}</div>
      {density === "comfortable" && article.summary ? <p>{article.summary}</p> : null}
      <div className="news-row-meta"><span>{article.source_name}</span><span>{formatTimestamp(article.published_at)}</span><span>{primaryCategory}</span>{primaryAsset ? <span>{primaryAsset.symbol}</span> : null}<span>{percent(article.importance_score)}</span></div>
    </button>
    <button className="icon-button" aria-label={article.is_saved ? "Unsave story" : "Save story"} onClick={(event) => { event.stopPropagation(); onSave(); }}>{article.is_saved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}</button>
  </article>;
}

function NewsDetail({ article, onSave }: { article: NewsArticle; onSave: () => void }) {
  return <div className="news-detail">
    <div className="card-heading"><div><p className="eyebrow">{article.provider_name ?? article.provider_code}</p><h2>{article.headline}</h2></div><button className="icon-button" aria-label={article.is_saved ? "Unsave story" : "Save story"} onClick={onSave}>{article.is_saved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}</button></div>
    <p>{article.summary ?? "No provider summary is available for this story."}</p>
    <div className="signal-grid">
      <Signal label="Published" value={formatTimestamp(article.published_at)} />
      <Signal label="Importance" value={percent(article.importance_score)} />
      <Signal label="Relevance" value={percent(article.relevance_score)} />
      <Signal label="Sentiment" value={article.sentiment_label?.replace(/_/g, " ") ?? "not provided"} />
    </div>
    <section><h3>Affected assets</h3>{article.assets.length ? <div className="chip-list">{article.assets.map((asset) => <Link key={asset.asset_id} to={`/asset/${asset.asset_id}`}>{asset.symbol}<span>{asset.match_method.replace(/_/g, " ")} {percent(asset.confidence_score)}</span></Link>)}</div> : <EmptyRow text="No mapped asset was resolved with sufficient confidence." />}</section>
    <section><h3>Categories</h3><div className="chip-list">{article.categories.map((category) => <span key={category.category_code}>{category.category_name}</span>)}</div></section>
    {article.cluster ? <section><h3>Related coverage</h3><p>{article.cluster.article_count} article{article.cluster.article_count === 1 ? "" : "s"} in this story cluster.</p></section> : null}
    {article.canonical_url ? <a className="button-link" href={article.canonical_url} target="_blank" rel="noreferrer"><ExternalLink size={15} />Original source</a> : null}
  </div>;
}

function presetCategory(preset: NewsPreset) {
  if (preset === "earnings") return "earnings";
  if (preset === "press") return "press_release";
  return "";
}

export function categoryMatchesPreset(article: NewsArticle, preset: NewsPreset) {
  const codes = new Set(article.categories.map((item) => item.category_code));
  if (preset === "corporate") return [...codes].some((code) => corporateCategories.has(code));
  if (preset === "macro") return [...codes].some((code) => macroCategories.has(code));
  return true;
}
