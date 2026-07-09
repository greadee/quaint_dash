import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Info, Plus, RefreshCw, Save, SlidersHorizontal, X } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type SignalDetailResponse, type SignalRow } from "../api";
import { money, number, percent, signedNumber } from "./routeFormatters";
import { EmptyRow, ErrorPanel, Loading } from "./routeShared";
import type { AppNotification } from "./routeTypes";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar, usePageFeature } from "../pageFeatureStore";

const actionErrorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

export function StockRankingsPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [expandedId, setExpandedId] = useState<string | null>(params.get("signal"));
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [columnDetail, setColumnDetail] = useState<string | null>(null);
  const showSummaryStrip = usePageFeature("signals", "signals.summaryStrip");
  const showPriorityPanels = usePageFeature("signals", "signals.priorityPanels");
  const showMethodology = usePageFeature("signals", "signals.methodology");
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
  const inspectColumn = (label: string, sortKey: string) => {
    if (sortKey) updateFilter("sort", sortKey);
    setColumnDetail((current) => current === label ? null : label);
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
        <PageLayoutButton pageId="signals" />
        <PageFeatureMenu pageId="signals" />
        <button onClick={() => signals.refetch()} disabled={signals.isFetching}><RefreshCw size={17} />Refresh</button>
        <button onClick={() => notify("Saved views use URL filters in this local build.")}><Save size={17}/>Saved view</button>
        <a className="button-link" href="#signal-methodology"><Info size={17}/>Methodology</a>
      </div>
    </div>
    <PageLayoutToolbar pageId="signals" />
    <OptionalFeaturesEmpty pageId="signals" />
    {showSummaryStrip ? <LayoutWidget pageId="signals" widgetId="signals.summaryStrip"><section className="signal-summary-strip" aria-label="Signal summary">
      {signals.isLoading ? Array.from({ length: 6 }).map((_item, index) => <div className="signal-summary-tile skeleton" key={index} />) : signals.data?.metrics.map((metric) => (
        <button key={metric.key} className="signal-summary-tile" onClick={() => applyMetric(metric.filter_params)}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </button>
      ))}
    </section></LayoutWidget> : null}
    {signals.data?.partial_provider_failures.length ? <div className="signal-degraded" role="status">Partial provider coverage: {signals.data.partial_provider_failures.join(", ")}. Valid cached signals remain visible.</div> : null}
    {signals.isError ? <ErrorPanel error={signals.error} /> : null}
    {showPriorityPanels ? <LayoutWidget pageId="signals" widgetId="signals.priorityPanels"><section className="signal-priority-grid">
      <SignalPrioritySection title="Needs attention" items={signals.data?.needs_attention ?? []} empty="No high-priority risks currently meet the filters." onOpen={openSignal} />
      <SignalPrioritySection title="Top opportunities" items={signals.data?.top_opportunities ?? []} empty="No high-confidence opportunities currently meet the filters." onOpen={openSignal} />
    </section></LayoutWidget> : null}
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
                      {sortKey ? (
                        <button
                          className="sort-header"
                          onClick={() => inspectColumn(label, sortKey)}
                          aria-label={`Sort by ${label} and show calculation details`}
                        >
                          {label}{filters.sort === sortKey ? " desc" : ""}<Info size={12} />
                        </button>
                      ) : label}
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
          {columnDetail ? <SignalColumnDetailPanel column={columnDetail} onClose={() => setColumnDetail(null)} /> : null}
          <div className="signal-mobile-list">
            {signals.data.items.map((item) => (
              <SignalMobileCard
                key={item.signal_id}
                item={item}
                expanded={expandedId === item.signal_id}
                onOpen={() => openSignal(item.signal_id)}
                onClose={() => openSignal(item.signal_id)}
                onReview={() => markReviewed.mutate(item.signal_id)}
                onAlert={() => createAlert.mutate(item.signal_id)}
                onWatchlist={() => addWatchlist.mutate(item.asset_id)}
              />
            ))}
          </div>
        </>
      ) : <EmptyRow text={Object.keys(filters).length ? "No signals match the selected filters. Clear filters or broaden the confidence and priority thresholds." : "No active signals. Stored ranking inputs are not available for the tracked universe yet."} />}
      {signals.isFetching && !signals.isLoading ? <p className="signal-refreshing" role="status">Refreshing signals while keeping current results visible.</p> : null}
      {showMethodology ? <LayoutWidget pageId="signals" widgetId="signals.methodology"><p id="signal-methodology" className="signal-methodology">{signals.data?.methodology ?? "Signal methodology loads with the server-side signal response."}</p></LayoutWidget> : null}
    </section>
  </div>;
}

const signalColumnDetails: Record<string, { title: string; body: string; details: string[] }> = {
  Strength: {
    title: "Strength calculation",
    body: "Strength is the absolute ranking score scaled from 0 to 100 into a 0% to 100% magnitude. It says how large the current signal is, not how reliable the inputs are.",
    details: [
      "Backend field: `strength = min(1, score_strength / 100)`.",
      "The raw score remains visible in Trigger as the observed value.",
      "Open Evidence on a row to see which ranking components supported or contradicted that strength.",
    ],
  },
  Confidence: {
    title: "Confidence calculation",
    body: "Confidence now measures input quality instead of defaulting to 100% when a factor has data. It blends component coverage, evidence breadth, and freshness of the latest source date.",
    details: [
      "Coverage is the share of available ranking components.",
      "Breadth rewards signals with at least two independent available components.",
      "Freshness steps down as inputs age beyond 7, 31, and 90 days.",
    ],
  },
  Trigger: {
    title: "Trigger calculation",
    body: "Trigger compares the raw observed ranking score with the adapter threshold for that signal family. Positive signals use a positive threshold; negative signals use the mirrored negative threshold.",
    details: [
      "Backend field: `trigger_threshold` comes from the signal adapter.",
      "Rows show `raw observed value vs threshold` so the crossing is auditable.",
      "Neutral rows show watch when no directional trigger threshold is active.",
    ],
  },
  Signal: {
    title: "Signal calculation",
    body: "The signal name maps a ranking factor to a deterministic server-side adapter such as price momentum, sentiment, earnings momentum, or institutional buying.",
    details: ["The summary sentence is built from the leading supporting evidence and current direction."],
  },
};

function SignalColumnDetailPanel({ column, onClose }: { column: string; onClose: () => void }) {
  const detail = signalColumnDetails[column] ?? {
    title: `${column} details`,
    body: "This column is sorted from the server response and can be inspected row-by-row through Evidence.",
    details: ["Open a row's Evidence panel for the supporting data, source, and timestamps."],
  };
  return <div className="signal-column-detail" role="status">
    <div><strong>{detail.title}</strong><button onClick={onClose} aria-label="Close column details"><X size={14} /></button></div>
    <p>{detail.body}</p>
    <ul>{detail.details.map((item) => <li key={item}>{item}</li>)}</ul>
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
      <SignalEfficacyBox item={item} />
    </div>
    <div className="signal-detail-actions">
      <Link to={`/asset/${item.asset_id}`}>Open ticker</Link>
      <Link to={`/compare?symbols=${item.ticker}`}>Compare asset</Link>
      <Link to="/benchmarks">Benchmarks</Link>
      <button onClick={onWatchlist}><Plus size={14}/>Watchlist</button>
      <button onClick={onReview}><CheckCircle2 size={14}/>Mark reviewed</button>
      <button onClick={onAlert}><Bell size={14}/>Create alert</button>
    </div>
  </div>;
}

function SignalEfficacyBox({ item }: { item: SignalRow | SignalDetailResponse }) {
  const efficacy = item.historical_efficacy;
  return <div className="signal-impact-box">
    <strong>Historical efficacy</strong>
    <p><b>{efficacy.label}</b><span>Sample size {efficacy.sample_size}; prior occurrences {efficacy.prior_occurrences ?? "unavailable"}.</span></p>
    {efficacy.warning ? <p>{efficacy.warning}</p> : <>
      <p>Median forward return: {percent(efficacy.median_forward_return)}</p>
      <p>Hit rate: {percent(efficacy.hit_rate)}</p>
      <p>Max adverse excursion: {percent(efficacy.max_adverse_excursion)}</p>
    </>}
  </div>;
}

function EvidenceList({ title, items }: { title: string; items: { label: string; metric: string; value: number | null; score: number | null; detail: string; source: string }[] }) {
  return <div className="signal-evidence-list"><strong>{title}</strong>{items.length ? items.map((item) => <p key={`${item.label}-${item.metric}`}><b>{item.label}</b><span>{item.metric}: {item.value == null ? "Unavailable" : number(item.value, 2)}; score {item.score == null ? "missing" : signedNumber(item.score, 1)}. {item.detail}</span></p>) : <p>No evidence in this direction.</p>}</div>;
}

function SignalMobileCard({
  item,
  expanded,
  onOpen,
  onClose,
  onReview,
  onAlert,
  onWatchlist,
}: {
  item: SignalRow;
  expanded: boolean;
  onOpen: () => void;
  onClose: () => void;
  onReview: () => void;
  onAlert: () => void;
  onWatchlist: () => void;
}) {
  return <article className="signal-mobile-card">
    <div><strong>{item.ticker}</strong><SignalTone value={item.direction} /></div>
    <h3>{item.signal_name}</h3>
    <p>{item.summary}</p>
    <dl><div><dt>Confidence</dt><dd>{percent(item.confidence)}</dd></div><div><dt>Priority</dt><dd>{percent(item.portfolio_priority)}</dd></div><div><dt>Age</dt><dd>{timeAgo(item.first_detected_at)}</dd></div></dl>
    <div className="signal-mobile-actions">
      <Link to={`/signals/${encodeURIComponent(item.signal_id)}`}>Details</Link>
      <button onClick={onOpen}>{expanded ? "Hide evidence" : "Inspect evidence"}</button>
    </div>
    {expanded ? (
      <SignalEvidencePanel
        item={item}
        onClose={onClose}
        onReview={onReview}
        onAlert={onAlert}
        onWatchlist={onWatchlist}
      />
    ) : null}
  </article>;
}

function SignalTone({ value }: { value: string }) {
  return <span className={`signal-tone ${value}`}>{labelize(value)}</span>;
}

function SignalTableSkeleton() {
  return <div className="signal-table-skeleton">{Array.from({ length: 6 }).map((_item, index) => <div key={index} className="skeleton-row" />)}</div>;
}

export function SignalDetailPage({ notify }: { notify: (message: string, tone?: AppNotification["tone"]) => void }) {
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
