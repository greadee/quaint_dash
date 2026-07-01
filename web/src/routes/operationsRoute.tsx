import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Trash2 } from "lucide-react";
import { api, type DataReadinessWorkerStatus, type IngestionBackgroundStatus, type IngestionReadiness, type MarketFreshnessStatus, type StockRankingReadiness } from "../api";
import { boundedInt, dateRange, formatActionResult, formatCount, formatDuration, formatTimestamp } from "./routeFormatters";
import { EmptyRow, ErrorPanel, HelpDisclosure, Loading, Signal } from "./routeShared";
import type { HelpItem } from "./routeTypes";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar, usePageFeature } from "../pageFeatureStore";

type StockRankingFactor = "aggregate" | "share_price_momentum" | "news_sentiment" | "retail_sentiment" | "earnings_momentum" | "institutional_buying";
type StockRankingUniverse = "tracked" | "all";

const stockRankingFactors: { value: StockRankingFactor; label: string }[] = [
  { value: "aggregate", label: "Aggregate" },
  { value: "share_price_momentum", label: "Price" },
  { value: "news_sentiment", label: "News" },
  { value: "retail_sentiment", label: "Retail" },
  { value: "earnings_momentum", label: "Earnings" },
  { value: "institutional_buying", label: "Institutions" },
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

function backgroundStatusDetail(status: IngestionBackgroundStatus): string {
  const schedule = `Scheduled ${formatTimestamp(status.last_schedule_at)}`;
  const run = `ran ${formatTimestamp(status.last_run_at)}`;
  const pending = status.last_pending_count === null ? "pending unknown" : `${status.last_pending_count} pending`;
  const scope = `${status.max_assets_per_schedule} assets, ${status.years} years, ${status.prices_only ? "prices only" : "prices/dividends/splits"}`;
  const drain = `${status.max_run_batches_per_tick} batches, ${status.max_jobs_per_tick} jobs each, ${pending}`;
  return `${schedule}; ${run}. Drain: ${drain}. Scope: ${scope}.`;
}

function marketFreshnessStatusDetail(status: MarketFreshnessStatus): string {
  const lastPoll = `Polled ${formatTimestamp(status.last_poll_at)}`;
  const coverage = `${formatCount(status.last_refreshed_count, "symbol")} refreshed from ${formatCount(status.last_subscription_count, "subscription")}`;
  const scope = `${status.max_symbols_per_tick} symbols, ${status.lookback_days} day lookback${status.include_watchlist ? ", watchlist included" : ""}`;
  return `${lastPoll}. ${coverage}. Scope: ${scope}.`;
}

function dataReadinessStatusDetail(status: DataReadinessWorkerStatus): string {
  const lastCheck = `Checked ${formatTimestamp(status.last_check_at)}`;
  const coverage = `${formatCount(status.last_ready_count, "ready")} of ${formatCount(status.last_target_count, "target")}`;
  const valuation = `${formatCount(status.last_valuation_count, "valuation")} calculated`;
  return `${lastCheck}. ${coverage}; ${valuation}. ${formatCount(status.last_pending_count, "job")} pending.`;
}

export function OperationsPage() {
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
  const showRoutineWorker = usePageFeature("operations", "operations.routineWorker");
  const showMarketFreshness = usePageFeature("operations", "operations.marketFreshness");
  const showDataReadiness = usePageFeature("operations", "operations.dataReadiness");
  const showProjectionReadiness = usePageFeature("operations", "operations.projectionReadiness");
  const showRankingReadiness = usePageFeature("operations", "operations.rankingReadiness");
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
    enabled: showRoutineWorker,
    refetchInterval: showRoutineWorker ? 10000 : false,
  });
  const marketFreshness = useQuery({
    queryKey: ["market-freshness-status"],
    queryFn: api.marketFreshnessStatus ?? (() => Promise.resolve(undefined)),
    enabled: showMarketFreshness && typeof api.marketFreshnessStatus === "function",
    refetchInterval: showMarketFreshness ? 10000 : false,
  });
  const dataReadiness = useQuery({
    queryKey: ["data-readiness-status"],
    queryFn: api.dataReadinessStatus ?? (() => Promise.resolve(undefined)),
    enabled: showDataReadiness && typeof api.dataReadinessStatus === "function",
    refetchInterval: showDataReadiness ? 10000 : false,
  });
  const readiness = useQuery({
    queryKey: ["ingestion-readiness"],
    queryFn: api.ingestionReadiness,
    enabled: showProjectionReadiness,
    refetchInterval: showProjectionReadiness ? 10000 : false,
  });
  const rankingReadiness = useQuery({
    queryKey: ["ranking-readiness", scheduleRankingUniverse],
    queryFn: () => api.rankingReadiness({
      universe: scheduleRankingUniverse,
      limit: boundedInt(maxAssets, 25, 1, 100),
    }),
    enabled: showRankingReadiness,
    refetchInterval: showRankingReadiness ? 10000 : false,
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
  const startMarketFreshness = useMutation({
    mutationFn: api.startMarketFreshness,
    onSuccess: () => {
      setMessage("Market freshness worker started.");
      client.invalidateQueries({ queryKey: ["market-freshness-status"] });
    },
  });
  const stopMarketFreshness = useMutation({
    mutationFn: api.stopMarketFreshness,
    onSuccess: () => {
      setMessage("Market freshness worker stopped.");
      client.invalidateQueries({ queryKey: ["market-freshness-status"] });
    },
  });
  const tickMarketFreshness = useMutation({
    mutationFn: api.tickMarketFreshness,
    onSuccess: (result) => {
      setMessage(`Market freshness cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["market-freshness-status"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
    },
  });
  const startDataReadiness = useMutation({
    mutationFn: api.startDataReadiness,
    onSuccess: () => {
      setMessage("Data readiness worker started.");
      client.invalidateQueries({ queryKey: ["data-readiness-status"] });
    },
  });
  const stopDataReadiness = useMutation({
    mutationFn: api.stopDataReadiness,
    onSuccess: () => {
      setMessage("Data readiness worker stopped.");
      client.invalidateQueries({ queryKey: ["data-readiness-status"] });
    },
  });
  const tickDataReadiness = useMutation({
    mutationFn: api.tickDataReadiness,
    onSuccess: (result) => {
      setMessage(`Data readiness cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["data-readiness-status"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
    },
  });
  const isBusy = schedule.isPending || run.isPending || retry.isPending || clearHistory.isPending || startBackground.isPending || stopBackground.isPending || tickBackground.isPending || startMarketFreshness.isPending || stopMarketFreshness.isPending || tickMarketFreshness.isPending || startDataReadiness.isPending || stopDataReadiness.isPending || tickDataReadiness.isPending;
  const actionError = schedule.error ?? run.error ?? retry.error ?? clearHistory.error ?? startBackground.error ?? stopBackground.error ?? tickBackground.error ?? startMarketFreshness.error ?? stopMarketFreshness.error ?? tickMarketFreshness.error ?? startDataReadiness.error ?? stopDataReadiness.error ?? tickDataReadiness.error;
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
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1><p className="page-subtitle">Background due work keeps routine data moving. Manual controls remain here for backfills, retries, provider-sensitive refreshes, and explicit runs.</p></div><div className="actions"><PageLayoutButton pageId="operations" /><PageFeatureMenu pageId="operations" /><button onClick={() => { jobs.refetch(); background.refetch(); marketFreshness.refetch(); dataReadiness.refetch(); readiness.refetch(); rankingReadiness.refetch(); }} disabled={jobs.isFetching || background.isFetching || marketFreshness.isFetching || dataReadiness.isFetching || readiness.isFetching || rankingReadiness.isFetching}><RefreshCw size={17}/>Refresh</button><button className="danger" onClick={() => window.confirm("Clear ingestion job history and sync status rows? Market data and broker connections will stay intact.") && clearHistory.mutate()} disabled={isBusy}><Trash2 size={17}/>Clear history</button><button className="primary" onClick={() => window.confirm("Run pending ingestion jobs with these options?") && run.mutate()} disabled={isBusy}><RefreshCw size={17}/>Run jobs</button></div></div>
    <PageLayoutToolbar pageId="operations" />
    <OptionalFeaturesEmpty pageId="operations" />
    {showRoutineWorker ? <LayoutWidget pageId="operations" widgetId="operations.routineWorker"><IngestionBackgroundCard status={background.data} isLoading={background.isLoading} error={background.error} onStart={() => startBackground.mutate()} onStop={() => stopBackground.mutate()} onTick={() => tickBackground.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showMarketFreshness ? <LayoutWidget pageId="operations" widgetId="operations.marketFreshness"><MarketFreshnessCard status={marketFreshness.data} isLoading={marketFreshness.isLoading} error={marketFreshness.error} onStart={() => startMarketFreshness.mutate()} onStop={() => stopMarketFreshness.mutate()} onTick={() => tickMarketFreshness.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showDataReadiness ? <LayoutWidget pageId="operations" widgetId="operations.dataReadiness"><DataReadinessCard status={dataReadiness.data} isLoading={dataReadiness.isLoading} error={dataReadiness.error} onStart={() => startDataReadiness.mutate()} onStop={() => stopDataReadiness.mutate()} onTick={() => tickDataReadiness.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showProjectionReadiness ? <LayoutWidget pageId="operations" widgetId="operations.projectionReadiness"><IngestionReadinessCard readiness={readiness.data} isLoading={readiness.isLoading} error={readiness.error} onScheduleAsset={scheduleAsset} isBusy={isBusy} /></LayoutWidget> : null}
    {showRankingReadiness ? <LayoutWidget pageId="operations" widgetId="operations.rankingReadiness"><RankingReadinessCard readiness={rankingReadiness.data} isLoading={rankingReadiness.isLoading} error={rankingReadiness.error} onScheduleAsset={scheduleRankingAsset} isBusy={isBusy} /></LayoutWidget> : null}
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
        <Signal label="Run cadence" value={status ? `${formatDuration(status.run_interval_seconds)} / ${status.max_run_batches_per_tick} batches` : "Unavailable"} />
        <Signal label="Pending jobs" value={isLoading ? "Loading" : formatCount(status?.last_pending_count, "job")} />
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

function MarketFreshnessCard({
  status,
  isLoading,
  error,
  onStart,
  onStop,
  onTick,
  isBusy,
}: {
  status?: MarketFreshnessStatus;
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
      <div><p className="eyebrow">Market freshness</p><h2>Holding price worker</h2></div>
      <div className="card-tools"><span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Last refreshed" value={isLoading ? "Loading" : formatCount(status?.last_refreshed_count, "symbol")} />
        <Signal label="Subscriptions" value={isLoading ? "Loading" : formatCount(status?.last_subscription_count, "symbol")} />
        <Signal label="Poll cadence" value={status ? formatDuration(status.poll_interval_seconds) : "Unavailable"} />
        <Signal label="Symbol cap" value={status ? formatCount(status.max_symbols_per_tick, "symbol") : "Unavailable"} />
        <div className="background-actions">
          <button className={status?.enabled ? "" : "primary"} onClick={() => window.confirm("Start the market freshness worker for this API session? It refreshes current prices for tracked holdings in the background.") && onStart()} disabled={isBusy || isLoading || status?.enabled}>Start worker</button>
          <button onClick={() => window.confirm("Stop the market freshness worker? Stored prices will remain available.") && onStop()} disabled={isBusy || isLoading || !status?.enabled}>Stop worker</button>
          <button onClick={() => window.confirm("Run one market freshness cycle now?") && onTick()} disabled={isBusy || isLoading}><RefreshCw size={17}/>Refresh prices</button>
        </div>
        <div className="background-status-note">
          <strong>{status?.enabled ? "Holding prices are being refreshed." : "Holding price refresh is off."}</strong>
          <span>{status ? marketFreshnessStatusDetail(status) : "Status has not loaded yet."}</span>
          {status?.last_error ? <em>{status.last_error}</em> : null}
        </div>
      </div>
    )}
  </section>;
}

function DataReadinessCard({
  status,
  isLoading,
  error,
  onStart,
  onStop,
  onTick,
  isBusy,
}: {
  status?: DataReadinessWorkerStatus;
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
      <div><p className="eyebrow">Valuation readiness</p><h2>Portfolio data worker</h2></div>
      <div className="card-tools"><span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Ready tickers" value={isLoading ? "Loading" : `${status?.last_ready_count ?? 0}/${status?.last_target_count ?? 0}`} />
        <Signal label="Valuations" value={isLoading ? "Loading" : formatCount(status?.last_valuation_count, "holding")} />
        <Signal label="Poll cadence" value={status ? formatDuration(status.poll_interval_seconds) : "Unavailable"} />
        <Signal label="Pending jobs" value={isLoading ? "Loading" : formatCount(status?.last_pending_count, "job")} />
        <div className="background-actions">
          <button className={status?.enabled ? "" : "primary"} onClick={() => window.confirm("Start the portfolio data readiness worker for this API session? It schedules missing stock/CDR valuation inputs and calculates portfolio valuations.") && onStart()} disabled={isBusy || isLoading || status?.enabled}>Start worker</button>
          <button onClick={() => window.confirm("Stop the portfolio data readiness worker?") && onStop()} disabled={isBusy || isLoading || !status?.enabled}>Stop worker</button>
          <button onClick={() => window.confirm("Run one valuation readiness cycle now?") && onTick()} disabled={isBusy || isLoading}><RefreshCw size={17}/>Force readiness</button>
        </div>
        <div className="background-status-note">
          <strong>{status?.enabled ? "Portfolio valuation inputs are being maintained." : "Portfolio valuation readiness is off."}</strong>
          <span>{status ? dataReadinessStatusDetail(status) : "Status has not loaded yet."}</span>
          {status?.last_missing?.length ? <em>{status.last_missing.slice(0, 3).join(" | ")}</em> : null}
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
