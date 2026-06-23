import { useMemo } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  Database,
  Eye,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  type BenchmarkConstituent,
  type BenchmarkDailyMetric,
  type BenchmarkExposure,
  type BenchmarkIndexDetail,
  type BenchmarkIndexSummary,
  type BenchmarkPricePoint,
} from "./api";
import {
  baselineDelta,
  benchmarkCategories,
  benchmarkCategoryLabel,
  benchmarkFreshness,
  benchmarkPeriods,
  formatCompact,
  formatDate,
  formatDateTime,
  formatLevel,
  formatMissing,
  formatPercent,
  freshnessLabel,
  isProxyBenchmark,
  mergeNormalizedSeries,
  normalizeSeries,
  parseSelected,
  periodStartDate,
  proxyLabel,
  sortBenchmarks,
  type BenchmarkCategoryFilter,
  type BenchmarkPeriod,
  type BenchmarkSortKey,
  type NormalizedSeries,
  type SortDirection,
} from "./benchmarkUtils";
import { ChartTypeToggle } from "./routes/routeShared";

type Notify = (message: string, tone?: "success" | "error") => void;

const seriesColors = ["#245c4f", "#6f4d9d", "#a85f34", "#376998", "#7b6f5c", "#a34440"];
const categoryValues: BenchmarkCategoryFilter[] = ["all", "core_geo", "sector", "industry", "theme"];
const periodValues = benchmarkPeriods.map((item) => item.value);
const sortValues: BenchmarkSortKey[] = ["return_252d", "return_21d", "return_1d", "volatility_252d_ann", "latest_close", "name", "freshness"];

function validCategory(value: string | null): BenchmarkCategoryFilter {
  return categoryValues.includes(value as BenchmarkCategoryFilter) ? value as BenchmarkCategoryFilter : "all";
}

function validPeriod(value: string | null): BenchmarkPeriod {
  return periodValues.includes(value as BenchmarkPeriod) ? value as BenchmarkPeriod : "1Y";
}

function validSort(value: string | null): BenchmarkSortKey {
  return sortValues.includes(value as BenchmarkSortKey) ? value as BenchmarkSortKey : "return_252d";
}

function validDirection(value: string | null): SortDirection {
  return value === "asc" ? "asc" : "desc";
}

export function BenchmarksWorkspacePage({ notify }: { notify: Notify }) {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const category = validCategory(params.get("category"));
  const period = validPeriod(params.get("range"));
  const search = params.get("q") ?? "";
  const currency = params.get("currency") ?? "";
  const proxy = params.get("proxy") ?? "all";
  const freshness = params.get("freshness") ?? "all";
  const sort = validSort(params.get("sort"));
  const direction = validDirection(params.get("direction"));
  const chartType = params.get("chart") === "bar" ? "bar" : "line";

  const benchmarks = useQuery({
    queryKey: ["benchmarks-workspace", search, category, currency],
    queryFn: () => api.benchmarks({
      q: search.trim() || undefined,
      category: category === "all" ? undefined : category,
      currency: currency.trim().toUpperCase() || undefined,
      is_active: true,
      limit: 500,
    }),
    placeholderData: (previous) => previous,
  });
  const allBenchmarks = useQuery({
    queryKey: ["benchmarks-baseline-options"],
    queryFn: () => api.benchmarks({ is_active: true, limit: 500 }),
    staleTime: 60000,
  });
  const baselineOptions = useMemo(() => allBenchmarks.data ?? [], [allBenchmarks.data]);
  const defaultBaseline = baselineOptions.find((item) => item.index_id === "SP500")?.index_id ?? baselineOptions[0]?.index_id ?? "SP500";
  const baseline = (params.get("baseline") ?? defaultBaseline).toUpperCase();

  const fallbackSelected = useMemo(() => {
    const rows = baselineOptions.length ? baselineOptions : benchmarks.data ?? [];
    return [baseline, ...rows.filter((item) => item.index_id !== baseline).slice(0, 2).map((item) => item.index_id)];
  }, [baseline, baselineOptions, benchmarks.data]);
  const selected = parseSelected(params.get("selected"), fallbackSelected);
  const selectedWithBaseline = Array.from(new Set([baseline, ...selected])).slice(0, 6);
  const rows = useMemo(() => {
    const raw = benchmarks.data ?? [];
    const filtered = raw.filter((item) => {
      if (proxy === "proxy" && !isProxyBenchmark(item)) return false;
      if (proxy === "direct" && isProxyBenchmark(item)) return false;
      if (freshness !== "all" && benchmarkFreshness(item) !== freshness) return false;
      return true;
    });
    return sortBenchmarks(filtered, sort, direction);
  }, [benchmarks.data, direction, freshness, proxy, sort]);
  const selectedBenchmarks = selectedWithBaseline
    .map((id) => (allBenchmarks.data ?? benchmarks.data ?? []).find((item) => item.index_id.toUpperCase() === id.toUpperCase()))
    .filter((item): item is BenchmarkIndexSummary => Boolean(item));

  const startDate = periodStartDate(period);
  const priceQueries = useQueries({
    queries: selectedBenchmarks.map((item) => ({
      queryKey: ["benchmark-compare-prices", item.index_id, period, startDate],
      queryFn: () => api.benchmarkPrices(item.index_id, { start_date: startDate, limit: 1400 }),
      staleTime: 30000,
    })),
  });
  const normalized = useMemo(() => selectedBenchmarks.map((item, index) =>
    normalizeSeries(item, priceQueries[index]?.data ?? [])
  ), [priceQueries, selectedBenchmarks]);
  const chartData = useMemo(() => mergeNormalizedSeries(normalized), [normalized]);
  const baselineSeries = normalized.find((item) => item.id.toUpperCase() === baseline.toUpperCase());
  const snapshot = useMemo(() => buildMarketSnapshot(rows), [rows]);

  const seed = useMutation({
    mutationFn: api.seedBenchmarks,
    onSuccess: () => {
      notify("Benchmark universe seeded.");
      queryClient.invalidateQueries({ queryKey: ["benchmarks"] });
      queryClient.invalidateQueries({ queryKey: ["benchmarks-workspace"] });
      queryClient.invalidateQueries({ queryKey: ["benchmarks-baseline-options"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const harden = useMutation({
    mutationFn: () => api.hardenBenchmarks({ category: category === "all" ? "all" : category, lookback_days: 730 }),
    onSuccess: () => {
      notify("Benchmark hardening finished.");
      queryClient.invalidateQueries({ queryKey: ["benchmarks"] });
      queryClient.invalidateQueries({ queryKey: ["benchmarks-workspace"] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-compare-prices"] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });

  const updateParam = (key: string, value: string) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (!value || value === "all" || (key === "range" && value === "1Y") || (key === "chart" && value === "line") || (key === "baseline" && value === defaultBaseline)) next.delete(key);
      else next.set(key, value);
      return next;
    });
  };
  const setSelected = (ids: string[]) => updateParam("selected", ids.join(","));
  const toggleSelected = (id: string) => {
    const upper = id.toUpperCase();
    if (selected.includes(upper)) {
      setSelected(selected.filter((item) => item !== upper));
      return;
    }
    if (selected.length >= 5) {
      notify("The chart is limited to five selected benchmarks plus the baseline.", "error");
      return;
    }
    setSelected([...selected, upper]);
  };
  const changeSort = (key: BenchmarkSortKey) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      const nextDirection = sort === key && direction === "desc" ? "asc" : "desc";
      next.set("sort", key);
      next.set("direction", nextDirection);
      return next;
    });
  };

  return (
    <div className="page benchmarks-page">
      <div className="page-title benchmarks-title">
        <div>
          <p className="eyebrow">Market comparison workspace</p>
          <h1>Benchmarks</h1>
          <p className="page-subtitle">Compare normalized index and ETF-proxy performance, inspect market leadership, and verify freshness before using benchmark data.</p>
          <div className="benchmarks-meta" aria-live="polite">
            <span>{rows.length} benchmarks</span>
            <span>Period {period}</span>
            <span>Baseline {baseline}</span>
            <span>Latest metric {formatDate(snapshot.latestMetricDate)}</span>
          </div>
        </div>
        <div className="actions benchmarks-admin-actions">
          <button disabled={seed.isPending} onClick={() => seed.mutate({ scope: "all" })}><Database size={16} />Seed all</button>
          <button disabled={harden.isPending} onClick={() => harden.mutate()}><ShieldCheck size={16} />Harden view</button>
        </div>
      </div>

      <section className="card benchmarks-control-card" aria-label="Benchmark controls">
        <label><Search size={15} />Search<input value={search} onChange={(event) => updateParam("q", event.target.value)} placeholder="Search name, id, ticker, provider" /></label>
        <label>Period<select value={period} onChange={(event) => updateParam("range", event.target.value)}>
          {benchmarkPeriods.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select></label>
        <label>Baseline<select value={baseline} onChange={(event) => updateParam("baseline", event.target.value)}>
          {baselineOptions.map((item) => <option key={item.index_id} value={item.index_id}>{item.index_id} - {item.index_name}</option>)}
        </select></label>
        <label>Currency<input value={currency} onChange={(event) => updateParam("currency", event.target.value.toUpperCase())} placeholder="Any" maxLength={3} /></label>
        <label><SlidersHorizontal size={15} />Proxy<select value={proxy} onChange={(event) => updateParam("proxy", event.target.value)}>
          <option value="all">All data types</option>
          <option value="direct">Direct index</option>
          <option value="proxy">ETF proxies</option>
        </select></label>
        <label>Freshness<select value={freshness} onChange={(event) => updateParam("freshness", event.target.value)}>
          <option value="all">Any status</option>
          <option value="fresh">Fresh</option>
          <option value="stale">Stale</option>
          <option value="partial">Partial</option>
          <option value="proxy">Proxy</option>
          <option value="error">Error</option>
          <option value="unavailable">Unavailable</option>
        </select></label>
      </section>

      <nav className="benchmark-tabs" aria-label="Benchmark categories">
        {benchmarkCategories.map((item) => (
          <button key={item.value} className={category === item.value ? "selected" : ""} onClick={() => updateParam("category", item.value)}>
            {item.label}
          </button>
        ))}
        <button className={selected.length > 1 ? "selected" : ""} onClick={() => document.getElementById("benchmark-compare-chart")?.focus()}>Compare</button>
      </nav>

      {benchmarks.error ? <BenchmarkError message={actionErrorMessage(benchmarks.error)} /> : null}
      <BenchmarkSnapshot snapshot={snapshot} period={period} />
      <BenchmarkComparisonChart
        normalized={normalized}
        chartData={chartData}
        baseline={baseline}
        baselineSeries={baselineSeries}
        selected={selected}
        onRemove={(id) => setSelected(selected.filter((item) => item !== id))}
        isLoading={priceQueries.some((query) => query.isLoading)}
        period={period}
        chartType={chartType}
        onChartTypeChange={(value) => updateParam("chart", value)}
      />
      <BenchmarkExplorer
        rows={rows}
        isLoading={benchmarks.isLoading}
        selected={selected}
        baseline={baseline}
        sort={sort}
        direction={direction}
        onSort={changeSort}
        onToggle={toggleSelected}
      />
      <BenchmarkLeadership rows={rows} />
      <BenchmarkStatusPanel rows={rows} />
    </div>
  );
}

function BenchmarkSnapshot({ snapshot, period }: { snapshot: MarketSnapshot; period: BenchmarkPeriod }) {
  return (
    <section className="benchmark-snapshot-grid" aria-label="Market snapshot">
      <MetricTile label={`Best performer (${period})`} value={snapshot.best ? formatPercent(snapshot.best.return_252d) : "-"} detail={snapshot.best?.index_name ?? "No return data"} tone="positive" />
      <MetricTile label={`Worst performer (${period})`} value={snapshot.worst ? formatPercent(snapshot.worst.return_252d) : "-"} detail={snapshot.worst?.index_name ?? "No return data"} tone="negative" />
      <MetricTile label="Median 1Y return" value={formatPercent(snapshot.medianReturn)} detail={`${snapshot.returnCount} benchmarks with metrics`} />
      <MetricTile label="Fresh data" value={`${snapshot.freshCount}/${snapshot.total}`} detail="Fresh, direct benchmark rows" />
      <MetricTile label="Proxy coverage" value={`${snapshot.proxyCount}`} detail="ETF-proxy-backed rows" />
      <MetricTile label="Highest volatility" value={snapshot.highestVol ? formatPercent(snapshot.highestVol.volatility_252d_ann) : "-"} detail={snapshot.highestVol?.index_name ?? "No volatility data"} />
    </section>
  );
}

function BenchmarkComparisonChart({
  normalized,
  chartData,
  baseline,
  baselineSeries,
  selected,
  onRemove,
  isLoading,
  period,
  chartType,
  onChartTypeChange,
}: {
  normalized: NormalizedSeries[];
  chartData: Record<string, string | number | null>[];
  baseline: string;
  baselineSeries?: NormalizedSeries;
  selected: string[];
  onRemove: (id: string) => void;
  isLoading: boolean;
  period: BenchmarkPeriod;
  chartType: "line" | "bar";
  onChartTypeChange: (value: "line" | "bar") => void;
}) {
  return (
    <section className="card benchmark-chart-card" id="benchmark-compare-chart" tabIndex={-1}>
      <div className="card-heading">
        <div>
          <p className="eyebrow">Actual benchmark levels</p>
          <h2>Benchmark price comparison</h2>
          <span>Stored closes for the selected {period} window. Delta values compare period return against {baseline}.</span>
        </div>
        <div className="card-tools benchmark-chart-tools">
          <ChartTypeToggle value={chartType} onChange={onChartTypeChange} />
          <div className="benchmark-chip-row" aria-label="Selected benchmarks">
            {selected.map((id) => <button key={id} onClick={() => onRemove(id)} aria-label={`Remove ${id} from comparison`}>{id}<X size={13} /></button>)}
          </div>
        </div>
      </div>
      {isLoading ? <BenchmarkSkeleton rows={6} /> : chartData.length < 2 ? (
        <BenchmarkEmpty title="No overlapping chart history" detail="Select benchmarks with daily prices for this period, or run benchmark hardening to backfill history." />
      ) : (
        <>
          <div className="benchmark-comparison-chart" aria-label={`Actual benchmark chart with ${normalized.length} series`}>
            <ResponsiveContainer width="100%" height="100%">
              {chartType === "bar" ? <BarChart data={chartData} margin={{ top: 8, right: 18, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" minTickGap={42} tick={{ fontSize: 11 }} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={42} />
                <Tooltip content={<BenchmarkTooltip series={normalized} baseline={baselineSeries} />} />
                <Legend />
                {normalized.map((item, index) => (
                  <Bar
                    key={item.id}
                    dataKey={item.id}
                    name={item.id}
                    fill={seriesColors[index % seriesColors.length]}
                  />
                ))}
              </BarChart> : <LineChart data={chartData} margin={{ top: 8, right: 18, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" minTickGap={42} tick={{ fontSize: 11 }} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={42} />
                <Tooltip content={<BenchmarkTooltip series={normalized} baseline={baselineSeries} />} />
                <Legend />
                {normalized.map((item, index) => (
                  <Line
                    key={item.id}
                    type="monotone"
                    dataKey={item.id}
                    name={item.id}
                    dot={false}
                    connectNulls
                    stroke={seriesColors[index % seriesColors.length]}
                    strokeWidth={item.id.toUpperCase() === baseline.toUpperCase() ? 3 : 2}
                  />
                ))}
              </LineChart>}
            </ResponsiveContainer>
          </div>
          <p className="sr-summary">Screen-reader summary: {normalized.map((item) => `${item.id} returned ${formatPercent(item.periodReturn)}; delta versus ${baseline} is ${formatPercent(baselineDelta(item, baselineSeries))}`).join(". ")}</p>
        </>
      )}
    </section>
  );
}

function BenchmarkTooltip({ active, payload, label, series, baseline }: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number; payload?: Record<string, unknown> }[];
  label?: string;
  series: NormalizedSeries[];
  baseline?: NormalizedSeries;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="benchmark-tooltip">
      <strong>{label}</strong>
      {payload.map((entry) => {
        const id = String(entry.dataKey);
        const item = series.find((candidate) => candidate.id === id);
        const rawClose = entry.payload?.[`${id}Close`] as number | undefined;
        return <p key={id}><span>{id}{item?.isProxy ? " proxy" : ""}</span><b>{formatLevel(rawClose ?? entry.value)}</b><em>{formatPercent(item?.periodReturn)} ({formatPercent(baselineDelta(item ?? series[0], baseline))} vs baseline)</em></p>;
      })}
    </div>
  );
}

function BenchmarkExplorer({
  rows,
  isLoading,
  selected,
  baseline,
  sort,
  direction,
  onSort,
  onToggle,
}: {
  rows: BenchmarkIndexSummary[];
  isLoading: boolean;
  selected: string[];
  baseline: string;
  sort: BenchmarkSortKey;
  direction: SortDirection;
  onSort: (key: BenchmarkSortKey) => void;
  onToggle: (id: string) => void;
}) {
  return (
    <section className="card benchmark-explorer">
      <div className="card-heading">
        <div><p className="eyebrow">Explorer</p><h2>Benchmark universe</h2></div>
        <span>{rows.length} visible</span>
      </div>
      {isLoading ? <BenchmarkSkeleton rows={8} /> : rows.length ? (
        <>
          <div className="benchmark-table-wrap">
            <table>
              <caption>Searchable benchmark universe with return, risk, proxy, and freshness columns.</caption>
              <thead>
                <tr>
                  <th>Compare</th>
                  <SortableTh label="Benchmark" value="name" sort={sort} direction={direction} onSort={onSort} />
                  <SortableTh label="Category" value="category" sort={sort} direction={direction} onSort={onSort} />
                  <SortableTh label="Level" value="latest_close" sort={sort} direction={direction} onSort={onSort} align="right" />
                  <SortableTh label="1D" value="return_1d" sort={sort} direction={direction} onSort={onSort} align="right" />
                  <SortableTh label="1M" value="return_21d" sort={sort} direction={direction} onSort={onSort} align="right" />
                  <SortableTh label="1Y" value="return_252d" sort={sort} direction={direction} onSort={onSort} align="right" />
                  <SortableTh label="Vol" value="volatility_252d_ann" sort={sort} direction={direction} onSort={onSort} align="right" />
                  <SortableTh label="Data" value="freshness" sort={sort} direction={direction} onSort={onSort} />
                  <th>Open</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => <BenchmarkRow key={item.index_id} item={item} selected={selected.includes(item.index_id)} baseline={baseline === item.index_id} onToggle={onToggle} />)}
              </tbody>
            </table>
          </div>
          <div className="benchmark-mobile-list">
            {rows.map((item) => <BenchmarkMobileCard key={item.index_id} item={item} selected={selected.includes(item.index_id)} baseline={baseline === item.index_id} onToggle={onToggle} />)}
          </div>
        </>
      ) : <BenchmarkEmpty title="No benchmarks match these filters" detail="Clear search, proxy, freshness, or category filters. If the universe is empty, seed the benchmark universe first." />}
    </section>
  );
}

function SortableTh({ label, value, sort, direction, onSort, align }: { label: string; value: BenchmarkSortKey; sort: BenchmarkSortKey; direction: SortDirection; onSort: (value: BenchmarkSortKey) => void; align?: "right" }) {
  return <th aria-sort={sort === value ? (direction === "asc" ? "ascending" : "descending") : "none"} className={align === "right" ? "numeric" : ""}><button onClick={() => onSort(value)}>{label}{sort === value ? (direction === "asc" ? " up" : " down") : ""}</button></th>;
}

function BenchmarkRow({ item, selected, baseline, onToggle }: { item: BenchmarkIndexSummary; selected: boolean; baseline: boolean; onToggle: (id: string) => void }) {
  return (
    <tr>
      <td><button className={selected ? "selected mini-button" : "mini-button"} onClick={() => onToggle(item.index_id)} aria-pressed={selected}>{selected ? "Selected" : "Add"}</button></td>
      <td><strong>{item.index_id}</strong><span>{item.index_name}</span>{baseline ? <em>Baseline</em> : null}</td>
      <td>{benchmarkCategoryLabel(item.index_category)}<span>{formatMissing(item.region)} / {item.currency}</span></td>
      <td className="numeric">{formatLevel(item.latest_close)}</td>
      <td className="numeric">{formatPercent(item.return_1d)}</td>
      <td className="numeric">{formatPercent(item.return_21d)}</td>
      <td className="numeric">{formatPercent(item.return_252d)}</td>
      <td className="numeric">{formatPercent(item.volatility_252d_ann)}</td>
      <td><BenchmarkDataBadge item={item} /></td>
      <td><Link className="icon-link" to={`/benchmarks/${item.index_id}${window.location.search}`} aria-label={`Open ${item.index_name}`}><ArrowUpRight size={16} /></Link></td>
    </tr>
  );
}

function BenchmarkMobileCard({ item, selected, baseline, onToggle }: { item: BenchmarkIndexSummary; selected: boolean; baseline: boolean; onToggle: (id: string) => void }) {
  return (
    <article className="benchmark-mobile-card">
      <div><strong>{item.index_id}</strong><span>{item.index_name}</span></div>
      <BenchmarkDataBadge item={item} />
      <dl>
        <div><dt>1Y</dt><dd>{formatPercent(item.return_252d)}</dd></div>
        <div><dt>Vol</dt><dd>{formatPercent(item.volatility_252d_ann)}</dd></div>
        <div><dt>Level</dt><dd>{formatLevel(item.latest_close)}</dd></div>
      </dl>
      <div className="benchmark-card-actions">
        <button className={selected ? "selected" : ""} onClick={() => onToggle(item.index_id)}>{selected ? "Selected" : "Compare"}</button>
        <Link className="button-link" to={`/benchmarks/${item.index_id}${window.location.search}`}><Eye size={15} />Open</Link>
        {baseline ? <span>Baseline</span> : null}
      </div>
    </article>
  );
}

function BenchmarkLeadership({ rows }: { rows: BenchmarkIndexSummary[] }) {
  const top = [...rows].filter((item) => item.return_252d != null).sort((left, right) => (right.return_252d ?? 0) - (left.return_252d ?? 0)).slice(0, 5);
  const risk = [...rows].filter((item) => item.volatility_252d_ann != null).sort((left, right) => (right.volatility_252d_ann ?? 0) - (left.volatility_252d_ann ?? 0)).slice(0, 5);
  return (
    <section className="benchmark-two-column">
      <BenchmarkRanking title="Leadership" eyebrow="Top 1Y returns" rows={top} metric={(item) => formatPercent(item.return_252d)} />
      <BenchmarkRanking title="Risk watch" eyebrow="Highest volatility" rows={risk} metric={(item) => formatPercent(item.volatility_252d_ann)} />
    </section>
  );
}

function BenchmarkRanking({ title, eyebrow, rows, metric }: { title: string; eyebrow: string; rows: BenchmarkIndexSummary[]; metric: (item: BenchmarkIndexSummary) => string }) {
  return (
    <section className="card benchmark-ranking">
      <div className="card-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div></div>
      {rows.length ? rows.map((item) => <Link to={`/benchmarks/${item.index_id}`} key={item.index_id}><span>{item.index_id}</span><strong>{item.index_name}</strong><b>{metric(item)}</b></Link>) : <BenchmarkEmpty title="No ranked data" detail="This panel needs computed daily metrics." />}
    </section>
  );
}

function BenchmarkStatusPanel({ rows }: { rows: BenchmarkIndexSummary[] }) {
  const stale = rows.filter((item) => ["stale", "partial", "unavailable", "error", "proxy"].includes(benchmarkFreshness(item))).slice(0, 8);
  return (
    <section className="card benchmark-status-panel">
      <div className="card-heading"><div><p className="eyebrow">Data status</p><h2>Freshness and proxy diagnostics</h2></div><span>{stale.length} flagged</span></div>
      {stale.length ? <div className="benchmark-status-list">{stale.map((item) => <p key={item.index_id}><strong>{item.index_id}</strong><span>{freshnessLabel(benchmarkFreshness(item))}</span><em>price {formatDateTime(item.daily_price_last_success_at)} / metrics {formatDate(item.latest_metric_date)} / composition {formatDate(item.latest_composition_date)}</em></p>)}</div> : <BenchmarkEmpty title="No flagged benchmark data" detail="Visible benchmarks have current metrics and composition metadata." />}
    </section>
  );
}

export function BenchmarkDetailPage({ notify }: { notify: Notify }) {
  const { benchmarkId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const id = benchmarkId.toUpperCase();
  const detail = useQuery({ queryKey: ["benchmark-detail-route", id], queryFn: () => api.benchmark(id), enabled: Boolean(id) });
  const prices = useQuery({ queryKey: ["benchmark-detail-prices", id], queryFn: () => api.benchmarkPrices(id, { limit: 1400 }), enabled: Boolean(id) });
  const metrics = useQuery({ queryKey: ["benchmark-detail-metrics", id], queryFn: () => api.benchmarkMetrics(id, 1400), enabled: Boolean(id) });
  const exposures = useQuery({ queryKey: ["benchmark-detail-exposures", id], queryFn: () => api.benchmarkExposures(id), enabled: Boolean(id) });
  const constituents = useQuery({ queryKey: ["benchmark-detail-constituents", id], queryFn: () => api.benchmarkConstituents(id, { limit: 25 }), enabled: Boolean(id) });
  const refresh = useMutation({
    mutationFn: ({ jobType }: { jobType: "daily_price" | "composition" | "metrics" }) => api.refreshBenchmark(id, { job_type: jobType }),
    onSuccess: () => {
      notify(`${id} refresh finished.`);
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail"] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail-route", id] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail-prices", id] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail-metrics", id] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail-exposures", id] });
      queryClient.invalidateQueries({ queryKey: ["benchmark-detail-constituents", id] });
    },
    onError: (error) => notify(actionErrorMessage(error), "error"),
  });
  const latestMetric = metrics.data?.at(-1);
  const normalized = detail.data ? normalizeSeries(detail.data, prices.data ?? []) : null;

  return (
    <div className="page benchmarks-page">
      <button className="button-link" onClick={() => navigate(`/benchmarks${window.location.search}`)}><ArrowLeft size={16} />Back to benchmarks</button>
      {detail.error ? <BenchmarkError message={actionErrorMessage(detail.error)} /> : detail.isLoading ? <BenchmarkSkeleton rows={10} /> : detail.data ? (
        <>
          <BenchmarkDetailHeader detail={detail.data} />
          <section className="benchmark-detail-grid">
            <BenchmarkDetailChart detail={detail.data} prices={prices.data ?? []} normalized={normalized} />
            <BenchmarkRiskPanel metric={latestMetric} detail={detail.data} metrics={metrics.data ?? []} />
          </section>
          <section className="benchmark-detail-grid">
            <BenchmarkIdentityPanel detail={detail.data} />
            <BenchmarkQualityPanel detail={detail.data} />
          </section>
          <section className="benchmark-detail-grid">
            <BenchmarkExposurePanel exposures={exposures.data ?? []} isLoading={exposures.isLoading} />
            <BenchmarkConstituentPanel constituents={constituents.data?.items ?? []} isLoading={constituents.isLoading} />
          </section>
          <section className="card benchmark-actions-card">
            <div className="card-heading"><div><p className="eyebrow">Manual refresh</p><h2>Data actions</h2></div></div>
            <div className="benchmark-card-actions">
              <button disabled={refresh.isPending} onClick={() => refresh.mutate({ jobType: "daily_price" })}><RefreshCw size={16} />Prices</button>
              <button disabled={refresh.isPending} onClick={() => refresh.mutate({ jobType: "metrics" })}><Activity size={16} />Metrics</button>
              <button disabled={refresh.isPending} onClick={() => refresh.mutate({ jobType: "composition" })}><Database size={16} />Composition</button>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function BenchmarkDetailHeader({ detail }: { detail: BenchmarkIndexDetail }) {
  return (
    <div className="page-title benchmark-detail-title">
      <div>
        <p className="eyebrow">{benchmarkCategoryLabel(detail.index_category)}</p>
        <h1>{detail.index_name} <small>{detail.index_id}</small></h1>
        <p className="page-subtitle">{detail.notes ?? "Benchmark metadata is available, but no provider note was stored."}</p>
        <div className="benchmarks-meta">
          <BenchmarkDataBadge item={detail} />
          <span>{proxyLabel(detail)}</span>
          <span>{detail.currency}</span>
          <span>Last price {formatDate(detail.available_price_range.last_price_date)}</span>
        </div>
      </div>
      <Link className="button-link" to={`/benchmarks?selected=${detail.index_id}&baseline=SP500`}><BarChart3 size={16} />Compare</Link>
    </div>
  );
}

function BenchmarkDetailChart({ detail, prices, normalized }: { detail: BenchmarkIndexDetail; prices: BenchmarkPricePoint[]; normalized: NormalizedSeries | null }) {
  const data = normalized?.points ?? [];
  return (
    <section className="card benchmark-chart-card">
      <div className="card-heading"><div><p className="eyebrow">Performance</p><h2>Price and normalized level</h2></div><span>{prices.length} observations</span></div>
      {data.length ? <div className="benchmark-comparison-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" minTickGap={42} tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} width={42} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} width={42} />
            <Tooltip />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="close" name="Level" stroke="#376998" dot={false} />
            <Line yAxisId="right" type="monotone" dataKey="normalized" name="Normalized to 100" stroke="#245c4f" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div> : <BenchmarkEmpty title="No price history" detail={`No daily prices are stored for ${detail.index_id}. Run price refresh or harden this benchmark.`} />}
    </section>
  );
}

function BenchmarkRiskPanel({ metric, detail, metrics }: { metric?: BenchmarkDailyMetric; detail: BenchmarkIndexDetail; metrics: BenchmarkDailyMetric[] }) {
  const drawdowns = metrics.filter((item) => item.drawdown_from_52w_high != null).slice(-90);
  return (
    <section className="card benchmark-risk-panel">
      <div className="card-heading"><div><p className="eyebrow">Return and risk</p><h2>Computed metrics</h2></div><span>{formatDate(metric?.metric_date)}</span></div>
      <div className="benchmark-detail-metrics">
        <MetricLine label="1 day return" value={formatPercent(metric?.return_1d ?? detail.return_1d)} />
        <MetricLine label="1 month return" value={formatPercent(metric?.return_21d)} />
        <MetricLine label="YTD return" value={formatPercent(metric?.return_ytd)} />
        <MetricLine label="1 year return" value={formatPercent(metric?.return_252d ?? detail.return_252d)} />
        <MetricLine label="21d volatility" value={formatPercent(metric?.volatility_21d_ann)} />
        <MetricLine label="1y volatility" value={formatPercent(metric?.volatility_252d_ann ?? detail.volatility_252d_ann)} />
        <MetricLine label="52w drawdown" value={formatPercent(metric?.drawdown_from_52w_high)} />
        <MetricLine label="SMA 200" value={formatLevel(metric?.sma_200)} />
      </div>
      {drawdowns.length ? <div className="benchmark-mini-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={drawdowns}>
            <XAxis dataKey="metric_date" hide />
            <YAxis hide />
            <Tooltip formatter={(value) => formatPercent(Number(value))} />
            <Bar dataKey="drawdown_from_52w_high" fill="#a34440" />
          </BarChart>
        </ResponsiveContainer>
      </div> : null}
      <p className="benchmark-methodology">Volatility is annualized from computed daily return windows. Drawdown is measured from the stored 52-week high; missing windows remain unavailable.</p>
    </section>
  );
}

function BenchmarkIdentityPanel({ detail }: { detail: BenchmarkIndexDetail }) {
  const primary = detail.symbols.find((item) => item.is_primary);
  return (
    <section className="card benchmark-info-panel">
      <div className="card-heading"><div><p className="eyebrow">Identity</p><h2>Benchmark profile</h2></div></div>
      <div className="benchmark-detail-metrics">
        <MetricLine label="Symbol" value={primary?.provider_symbol ?? "-"} />
        <MetricLine label="Provider" value={primary?.provider ?? "-"} />
        <MetricLine label="Family" value={detail.index_family} />
        <MetricLine label="Category" value={benchmarkCategoryLabel(detail.index_category)} />
        <MetricLine label="Region" value={formatMissing(detail.region)} />
        <MetricLine label="Country" value={formatMissing(detail.country_code)} />
        <MetricLine label="Currency" value={detail.currency} />
        <MetricLine label="Type" value={proxyLabel(detail)} />
      </div>
    </section>
  );
}

function BenchmarkQualityPanel({ detail }: { detail: BenchmarkIndexDetail }) {
  return (
    <section className="card benchmark-info-panel">
      <div className="card-heading"><div><p className="eyebrow">Quality</p><h2>Freshness and disclosure</h2></div><BenchmarkDataBadge item={detail} /></div>
      <div className="benchmark-detail-metrics">
        <MetricLine label="Price range" value={`${formatDate(detail.available_price_range.first_price_date)} - ${formatDate(detail.available_price_range.last_price_date)}`} />
        <MetricLine label="Metric range" value={`${formatDate(detail.available_metric_range.first_metric_date)} - ${formatDate(detail.available_metric_range.last_metric_date)}`} />
        <MetricLine label="Composition snapshot" value={formatDate(detail.latest_composition_date)} />
        <MetricLine label="Composition quality" value={formatMissing(detail.composition_quality)} />
        <MetricLine label="Constituents" value={detail.constituent_count == null ? "-" : String(detail.constituent_count)} />
        <MetricLine label="Price sync" value={formatDateTime(detail.daily_price_last_success_at)} />
      </div>
      {isProxyBenchmark(detail) ? <p className="benchmark-warning">This benchmark uses ETF proxy data for at least one data domain. ETF holdings can approximate exposure, but they are not exact official index composition.</p> : null}
      {detail.last_error ? <p className="benchmark-warning failed">{detail.last_error}</p> : null}
    </section>
  );
}

function BenchmarkExposurePanel({ exposures, isLoading }: { exposures: BenchmarkExposure[]; isLoading: boolean }) {
  const sector = exposures.filter((item) => item.dimension_type === "sector").slice(0, 8);
  return (
    <section className="card benchmark-info-panel">
      <div className="card-heading"><div><p className="eyebrow">Composition</p><h2>Exposure snapshot</h2></div><span>{exposures[0] ? formatDate(exposures[0].snapshot_date) : "-"}</span></div>
      {isLoading ? <BenchmarkSkeleton rows={5} /> : sector.length ? <div className="benchmark-exposure-bars">{sector.map((item) => <div key={`${item.dimension_type}-${item.dimension_value}`}><p><span>{item.dimension_value}</span><b>{formatPercent(item.weight_pct > 1 ? item.weight_pct / 100 : item.weight_pct)}</b></p><div className="bar"><span style={{ width: `${Math.max(2, Math.min(100, item.weight_pct > 1 ? item.weight_pct : item.weight_pct * 100))}%` }} /></div></div>)}</div> : <BenchmarkEmpty title="No exposure data" detail="No sector, country, industry, or currency exposure snapshot is stored for this benchmark." />}
      {exposures.some((item) => item.is_proxy) ? <p className="benchmark-warning">Exposure rows are proxy-derived.</p> : null}
    </section>
  );
}

function BenchmarkConstituentPanel({ constituents, isLoading }: { constituents: BenchmarkConstituent[]; isLoading: boolean }) {
  return (
    <section className="card benchmark-info-panel">
      <div className="card-heading"><div><p className="eyebrow">Holdings</p><h2>Top constituents</h2></div><span>{constituents[0] ? formatDate(constituents[0].snapshot_date) : "-"}</span></div>
      {isLoading ? <BenchmarkSkeleton rows={5} /> : constituents.length ? <div className="benchmark-status-list">{constituents.map((item) => <p key={item.constituent_symbol}><strong>{item.constituent_symbol}</strong><span>{formatPercent(item.weight_pct != null && item.weight_pct > 1 ? item.weight_pct / 100 : item.weight_pct)}</span><em>{item.constituent_name ?? "Unnamed"} / {item.sector ?? "No sector"} / {formatCompact(item.market_cap)}</em></p>)}</div> : <BenchmarkEmpty title="No constituent data" detail="No latest constituent snapshot is available. This may be structural for direct indices without holdings access." />}
      {constituents.some((item) => item.is_proxy) ? <p className="benchmark-warning">Constituents are ETF proxy holdings, not exact official index composition.</p> : null}
    </section>
  );
}

function BenchmarkDataBadge({ item }: { item: BenchmarkIndexSummary }) {
  const status = benchmarkFreshness(item);
  return <span className={`benchmark-data-badge ${status}`}>{freshnessLabel(status)} / {proxyLabel(item)}</span>;
}

function MetricTile({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "positive" | "negative" }) {
  return <article className="card benchmark-metric-tile"><span>{label}</span><strong className={tone}>{value}</strong><p>{detail}</p></article>;
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return <p className="metric-line"><span>{label}</span><b>{value}</b></p>;
}

function BenchmarkSkeleton({ rows }: { rows: number }) {
  return <div className="benchmark-skeleton" aria-label="Loading benchmark data">{Array.from({ length: rows }, (_, index) => <span key={index} />)}</div>;
}

function BenchmarkEmpty({ title, detail }: { title: string; detail: string }) {
  return <div className="benchmark-empty"><strong>{title}</strong><span>{detail}</span></div>;
}

function BenchmarkError({ message }: { message: string }) {
  return <div className="error-panel"><strong>Unable to load benchmark data</strong><span>{message}</span></div>;
}

type MarketSnapshot = {
  total: number;
  best: BenchmarkIndexSummary | null;
  worst: BenchmarkIndexSummary | null;
  medianReturn: number | null;
  returnCount: number;
  freshCount: number;
  proxyCount: number;
  highestVol: BenchmarkIndexSummary | null;
  latestMetricDate: string | null;
};

function buildMarketSnapshot(rows: BenchmarkIndexSummary[]): MarketSnapshot {
  const withReturn = rows.filter((item) => item.return_252d != null).sort((left, right) => (left.return_252d ?? 0) - (right.return_252d ?? 0));
  const returns = withReturn.map((item) => item.return_252d as number);
  const middle = Math.floor(returns.length / 2);
  const medianReturn = !returns.length ? null : returns.length % 2 ? returns[middle] : (returns[middle - 1] + returns[middle]) / 2;
  const withVol = rows.filter((item) => item.volatility_252d_ann != null).sort((left, right) => (right.volatility_252d_ann ?? 0) - (left.volatility_252d_ann ?? 0));
  return {
    total: rows.length,
    best: withReturn.at(-1) ?? null,
    worst: withReturn[0] ?? null,
    medianReturn,
    returnCount: returns.length,
    freshCount: rows.filter((item) => benchmarkFreshness(item) === "fresh").length,
    proxyCount: rows.filter(isProxyBenchmark).length,
    highestVol: withVol[0] ?? null,
    latestMetricDate: rows.map((item) => item.latest_metric_date).filter((value): value is string => Boolean(value)).sort().at(-1) ?? null,
  };
}

function actionErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
