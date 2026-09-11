import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api, type DataReadinessWorkerStatus, type IngestionBackgroundStatus, type IngestionQueueStatus, type IngestionReadiness, type MarketFreshnessStatus, type OperationsHealthSummary, type RetailSentimentStatus, type StockRankingReadiness, type WorkerDiagnostics } from "../api";
import { boundedInt, dateRange, formatActionResult, formatCount, formatDuration, formatTimestamp, percent, signedNumber } from "./routeFormatters";
import { EmptyRow, ErrorPanel, HelpDisclosure, Loading, Signal } from "./routeShared";
import type { HelpItem } from "./routeTypes";
import { LayoutWidget, OptionalFeaturesEmpty, PageFeatureMenu, PageLayoutButton, PageLayoutToolbar } from "../pageFeatureStore";
import { usePageFeature } from "../pageFeatureHooks";
import { backgroundStatusDetail, dataReadinessStatusDetail, marketFreshnessStatusDetail, queueAgeLabel, workerStateLabel } from "./operationsViewModels";
import "./operationsDiagnostics.css";
import { useSearchParams } from "react-router-dom";

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

const WORKER_STATUS_REFETCH_MS = 30_000;

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

export function OperationsPage() {
  const client = useQueryClient();
  const [searchParams] = useSearchParams();
  const selectedIncident = searchParams.get("incident");
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  const [domain, setDomain] = useState("");
  const [jobLimit, setJobLimit] = useState("25");
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
  const showRetailSentiment = usePageFeature("operations", "operations.retailSentiment");
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
  type RunOverride = { domain?: string; maxJobs?: string };
  const jobs = useQuery({
    queryKey: ["jobs", status, domain, jobLimit],
    queryFn: () => api.ingestionJobs(status, domain, boundedInt(jobLimit, 25, 1, 500)),
  });
  const currentPendingJobs = useQuery({
    queryKey: ["jobs", "queue-status"],
    queryFn: api.ingestionQueueStatus,
    refetchInterval: WORKER_STATUS_REFETCH_MS,
  });
  const health = useQuery({
    queryKey: ["operations-health-summary"],
    queryFn: api.operationsHealthSummary,
    refetchInterval: WORKER_STATUS_REFETCH_MS,
  });
  const background = useQuery({
    queryKey: ["ingestion-background-status"],
    queryFn: api.ingestionBackgroundStatus,
    refetchInterval: WORKER_STATUS_REFETCH_MS,
  });
  const marketFreshness = useQuery({
    queryKey: ["market-freshness-status"],
    queryFn: api.marketFreshnessStatus,
    refetchInterval: WORKER_STATUS_REFETCH_MS,
  });
  const dataReadiness = useQuery({
    queryKey: ["data-readiness-status"],
    queryFn: api.dataReadinessStatus,
    refetchInterval: WORKER_STATUS_REFETCH_MS,
  });
  const retailSentiment = useQuery({
    queryKey: ["retail-sentiment-status"],
    queryFn: () => api.retailSentimentStatus(10),
    enabled: showRetailSentiment,
  });
  const readiness = useQuery({
    queryKey: ["ingestion-readiness"],
    queryFn: api.ingestionReadiness,
    enabled: showProjectionReadiness,
  });
  const rankingReadiness = useQuery({
    queryKey: ["ranking-readiness", scheduleRankingUniverse],
    queryFn: () => api.rankingReadiness({
      universe: scheduleRankingUniverse,
      limit: boundedInt(maxAssets, 25, 1, 100),
    }),
    enabled: showRankingReadiness,
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
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
      client.invalidateQueries({ queryKey: ["retail-sentiment-status"] });
    },
  });
  const run = useMutation({
    mutationFn: (override?: RunOverride) => api.runIngestion({
      domain: override?.domain ?? runDomain,
      max_jobs: boundedInt(override?.maxJobs ?? runMaxJobs, 1, 1, 25),
    }),
    onSuccess: (result) => {
      setMessage(`Run finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
      client.invalidateQueries({ queryKey: ["retail-sentiment-status"] });
    },
  });
  const retry = useMutation({
    mutationFn: () => api.retryFailedIngestion({
      domain: domain || null,
      max_jobs: boundedInt(retryMaxJobs, 25, 1, 100),
    }),
    onSuccess: (result) => {
      setMessage(`Retry queued: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["retail-sentiment-status"] });
    },
  });
  const clearHistory = useMutation({
    mutationFn: api.clearIngestionHistory,
    onSuccess: (result) => {
      setMessage(`Cleared: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["retail-sentiment-status"] });
    },
  });
  const startBackground = useMutation({
    mutationFn: api.startIngestionBackground,
    onSuccess: () => {
      setMessage("Auto worker started.");
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
    },
  });
  const stopBackground = useMutation({
    mutationFn: api.stopIngestionBackground,
    onSuccess: () => {
      setMessage("Auto worker stopped.");
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
    },
  });
  const tickBackground = useMutation({
    mutationFn: api.tickIngestionBackground,
    onSuccess: (result) => {
      setMessage(`Auto worker cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      client.invalidateQueries({ queryKey: ["ingestion-background-status"] });
      client.invalidateQueries({ queryKey: ["ingestion-readiness"] });
      client.invalidateQueries({ queryKey: ["ranking-readiness"] });
      client.invalidateQueries({ queryKey: ["retail-sentiment-status"] });
    },
  });
  const startMarketFreshness = useMutation({
    mutationFn: api.startMarketFreshness,
    onSuccess: () => {
      setMessage("Market freshness worker started.");
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["market-freshness-status"] });
    },
  });
  const stopMarketFreshness = useMutation({
    mutationFn: api.stopMarketFreshness,
    onSuccess: () => {
      setMessage("Market freshness worker stopped.");
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["market-freshness-status"] });
    },
  });
  const tickMarketFreshness = useMutation({
    mutationFn: api.tickMarketFreshness,
    onSuccess: (result) => {
      setMessage(`Market freshness cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
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
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["data-readiness-status"] });
    },
  });
  const stopDataReadiness = useMutation({
    mutationFn: api.stopDataReadiness,
    onSuccess: () => {
      setMessage("Data readiness worker stopped.");
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
      client.invalidateQueries({ queryKey: ["data-readiness-status"] });
    },
  });
  const tickDataReadiness = useMutation({
    mutationFn: api.tickDataReadiness,
    onSuccess: (result) => {
      setMessage(`Data readiness cycle finished: ${formatActionResult(result.result)}`);
      client.invalidateQueries({ queryKey: ["operations-health-summary"] });
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
  const scheduleRetailSentiment = () => {
    setPipeline("ranking");
    setScheduleRankingFactor("retail_sentiment");
    schedule.mutate({
      pipeline: "ranking",
      rankingFactor: "retail_sentiment",
      rankingUniverse: scheduleRankingUniverse,
      missingOnly: true,
      staleOnly: true,
    });
  };
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Data health</p><h1>Operations</h1><p className="page-subtitle">Status reads are safe and do not run jobs. Manual controls remain below for bounded provider traffic and local data changes.</p></div><div className="actions"><PageLayoutButton pageId="operations" /><PageFeatureMenu pageId="operations" /><button onClick={() => { health.refetch(); jobs.refetch(); currentPendingJobs.refetch(); background.refetch(); marketFreshness.refetch(); dataReadiness.refetch(); retailSentiment.refetch(); readiness.refetch(); rankingReadiness.refetch(); }} disabled={health.isFetching || jobs.isFetching || currentPendingJobs.isFetching || background.isFetching || marketFreshness.isFetching || dataReadiness.isFetching || retailSentiment.isFetching || readiness.isFetching || rankingReadiness.isFetching}><RefreshCw size={17}/>Refresh status</button></div></div>
    <PageLayoutToolbar pageId="operations" />
    <OptionalFeaturesEmpty pageId="operations" />
    <OperationsHealthPanel health={health.data} isLoading={health.isLoading} error={health.error} selectedIncident={selectedIncident} />
    <OperationsDiagnostics queue={currentPendingJobs.data} isLoading={currentPendingJobs.isLoading} error={currentPendingJobs.error} workers={[
      { label: "Routine ingestion", status: background.data, error: background.error, isLoading: background.isLoading },
      { label: "Holding prices", status: marketFreshness.data, error: marketFreshness.error, isLoading: marketFreshness.isLoading },
      { label: "Portfolio data", status: dataReadiness.data, error: dataReadiness.error, isLoading: dataReadiness.isLoading },
    ]} />
    {showRoutineWorker ? <LayoutWidget pageId="operations" widgetId="operations.routineWorker"><IngestionBackgroundCard status={background.data} isLoading={background.isLoading} error={background.error} currentPendingCount={currentPendingJobs.data?.pending_count} isCurrentPendingLoading={currentPendingJobs.isLoading} currentPendingError={currentPendingJobs.error} onStart={() => startBackground.mutate()} onStop={() => stopBackground.mutate()} onTick={() => tickBackground.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showMarketFreshness ? <LayoutWidget pageId="operations" widgetId="operations.marketFreshness"><MarketFreshnessCard status={marketFreshness.data} isLoading={marketFreshness.isLoading} error={marketFreshness.error} onStart={() => startMarketFreshness.mutate()} onStop={() => stopMarketFreshness.mutate()} onTick={() => tickMarketFreshness.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showDataReadiness ? <LayoutWidget pageId="operations" widgetId="operations.dataReadiness"><DataReadinessCard status={dataReadiness.data} isLoading={dataReadiness.isLoading} error={dataReadiness.error} currentPendingCount={currentPendingJobs.data?.pending_count} isCurrentPendingLoading={currentPendingJobs.isLoading} currentPendingError={currentPendingJobs.error} onStart={() => startDataReadiness.mutate()} onStop={() => stopDataReadiness.mutate()} onTick={() => tickDataReadiness.mutate()} isBusy={isBusy} /></LayoutWidget> : null}
    {showRetailSentiment ? <LayoutWidget pageId="operations" widgetId="operations.retailSentiment"><RetailSentimentCard status={retailSentiment.data} isLoading={retailSentiment.isLoading} error={retailSentiment.error} onSchedule={scheduleRetailSentiment} onRun={() => run.mutate({ domain: "sentiment", maxJobs: "10" })} isBusy={isBusy} /></LayoutWidget> : null}
    {showProjectionReadiness ? <LayoutWidget pageId="operations" widgetId="operations.projectionReadiness"><IngestionReadinessCard readiness={readiness.data} isLoading={readiness.isLoading} error={readiness.error} onScheduleAsset={scheduleAsset} isBusy={isBusy} /></LayoutWidget> : null}
    {showRankingReadiness ? <LayoutWidget pageId="operations" widgetId="operations.rankingReadiness"><RankingReadinessCard readiness={rankingReadiness.data} isLoading={rankingReadiness.isLoading} error={rankingReadiness.error} onScheduleAsset={scheduleRankingAsset} isBusy={isBusy} /></LayoutWidget> : null}
    <section className="card operations-control">
      <div className="card-heading"><div><p className="eyebrow">Manual controls</p><h2>Ingestion actions</h2></div><div className="card-tools"><HelpDisclosure title="Manual ingestion actions" items={ingestionHelp} /><span>{isBusy ? "working" : "ready"}</span></div></div>
      <p className="operations-action-guidance">Schedule and retry add local work. Running jobs or starting workers can contact providers and use request quotas. Review access and limits before running a bounded batch.</p>
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
          <button className="primary" onClick={() => window.confirm("Run pending ingestion jobs with these options?") && run.mutate({})} disabled={isBusy}><RefreshCw size={17}/>Run</button>
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
          <label>Show<select value={jobLimit} onChange={(event) => setJobLimit(event.target.value)}><option value="25">25 jobs</option><option value="100">100 jobs</option><option value="250">250 jobs</option><option value="500">500 jobs</option></select></label>
          <span>{jobs.data?.length ?? 0} shown</span>
        </div>
      </div>
      <div className="filter-row">
        <label>Status<select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Any</option><option value="pending">Pending</option><option value="running">Running</option><option value="done">Done</option><option value="failed">Failed</option><option value="superseded">Superseded</option><option value="unsupported">Unsupported</option><option value="dead_letter">Dead letter</option></select></label>
        <label>Domain<select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">Any</option><option value="market">Market</option><option value="corporate">Corporate</option><option value="sentiment">Sentiment</option></select></label>
      </div>
      {jobs.error ? <ErrorPanel error={jobs.error} /> : jobs.isLoading ? <Loading compact /> : (
        <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Dataset</th><th>Type</th><th>Domain</th><th>Window</th><th>Status</th><th>Priority</th><th>Attempts</th><th>Updated</th><th>Error</th></tr></thead><tbody>{jobs.data?.map((job) => <tr key={job.job_id}><td>{job.asset_id ?? "Global"}</td><td>{job.dataset}</td><td>{job.job_type}</td><td>{job.domain}</td><td>{dateRange(job.requested_start_date, job.requested_end_date)}</td><td><span className={`pill ${job.status}`}>{job.status}</span></td><td>{job.priority}</td><td>{job.attempt_count}</td><td>{new Date(job.updated_at).toLocaleDateString()}</td><td className="job-error" title={job.error_message ?? ""}>{job.error_message ?? "-"}</td></tr>)}</tbody></table></div>
      )}
      {!jobs.isLoading && !jobs.data?.length ? <EmptyRow text="No ingestion jobs match the current filters." /> : null}
    </section>
  </div>;
}

type DiagnosticWorker = {
  label: string;
  status?: WorkerDiagnostics & { enabled: boolean; running: boolean };
  error: Error | null;
  isLoading: boolean;
};

function OperationsHealthPanel({ health, isLoading, error, selectedIncident }: {
  health?: OperationsHealthSummary;
  isLoading: boolean;
  error: Error | null;
  selectedIncident: string | null;
}) {
  const selected = health?.incidents.find((incident) => incident.code === selectedIncident);
  return <section id="operations-health" className={`card operations-health ${health?.status ?? "unavailable"}`} aria-labelledby="operations-health-heading">
    <div className="card-heading">
      <div><p className="eyebrow">Incident summary</p><h2 id="operations-health-heading">{isLoading ? "Checking system health" : error ? "System health unavailable" : health?.headline}</h2></div>
      <span className={`pill ${health?.status === "healthy" ? "done" : health?.status === "critical" ? "failed" : "pending"}`}>{health?.status ?? (isLoading ? "loading" : "unavailable")}</span>
    </div>
    {error ? <div className="operations-health-body"><p role="alert">Unified health could not be verified. The detailed read-only diagnostics below may still be available; do not assume a zero count is healthy.</p></div> : isLoading ? <Loading /> : health ? <div className="operations-health-body">
      <p className="operations-health-summary">{selected ? `Focused incident: ${selected.title}. ${selected.detail}` : health.summary}</p>
      <div className="background-status-grid">
        <Signal label="Queued work" value={formatCount(health.queue.pending_count, "job")} />
        <Signal label="Oldest backlog" value={queueAgeLabel(health.queue.oldest_backlog_age_seconds)} />
        <Signal label="Dead letters" value={formatCount(health.queue.dead_letter_count, "job")} />
        <Signal label="Workers enabled" value={`${health.workers.filter((worker) => worker.enabled).length}/${health.workers.length}`} />
        <Signal label="Affected products" value={String(health.affected_data_products.length)} />
      </div>
      {health.incidents.length ? <div className="operations-incident-list">{health.incidents.map((incident) => <article className={`${incident.severity} ${incident.code === selectedIncident ? "selected" : ""}`} key={incident.code}>
        <div><span className={`pill ${incident.severity === "critical" ? "failed" : incident.severity === "warning" ? "pending" : ""}`}>{incident.severity}</span><strong>{incident.title}</strong></div>
        <p>{incident.detail}</p>
        <p><b>Safe next step:</b> {incident.guidance}</p>
        {incident.affected_data_products.length ? <small>Affects {incident.affected_data_products.join(", ")}</small> : <small>Configuration status only; no affected product was inferred.</small>}
      </article>)}</div> : <p>No active incidents were found by the current health policy.</p>}
      <p className="muted">This section is read-only. Refreshing status does not schedule jobs, contact providers, or change stored data.</p>
    </div> : null}
  </section>;
}

export function OperationsDiagnostics({ queue, isLoading, error, workers }: {
  queue?: IngestionQueueStatus;
  isLoading: boolean;
  error: Error | null;
  workers: DiagnosticWorker[];
}) {
  const available = !error && queue;
  return <section className="card operations-diagnostics" aria-labelledby="operations-diagnostics-heading">
    <div className="card-heading"><div><p className="eyebrow">Read-only diagnostics</p><h2 id="operations-diagnostics-heading">Queue and worker status</h2></div><span>{available ? `Observed ${formatTimestamp(queue.observed_at)}` : isLoading ? "Loading" : "Unavailable"}</span></div>
    <div className="operations-diagnostics-body">
    {error || (!isLoading && !queue) ? <p role="alert">Queue status unavailable. Counts and backlog age are unknown. Check local database access, then refresh status.</p> : isLoading ? <Loading /> : queue ? <>
      <div className="background-status-grid">
        <Signal label="Pending" value={formatCount(queue.pending_count, "job")} />
        <Signal label="Running" value={formatCount(queue.running_count, "job")} />
        <Signal label="Dead letters" value={formatCount(queue.dead_letter_count, "job")} />
        <Signal label="Legacy failures" value={formatCount(queue.failed_count, "job")} />
        <Signal label="Oldest active job" value={queueAgeLabel(queue.oldest_backlog_age_seconds)} />
      </div>
      <p className="muted">Backlog age starts when the oldest pending or running job was created{queue.oldest_backlog_at ? ` (${formatTimestamp(queue.oldest_backlog_at)})` : ""}. Refresh reads local status and does not run jobs.</p>
      {queue.pending_count > 0 && workers.some((worker) => !worker.error && worker.status?.state === "disabled") ? <p role="status">Work is waiting and one or more automatic workers are disabled. Review worker state and provider access before choosing a bounded run.</p> : null}
      {queue.dead_letter_count > 0 || queue.failed_count > 0 ? <p role="status">Failed work needs review. Dead letters have stopped retrying; legacy failures remain separate. Resolve the cause before requeueing or creating replacement work.</p> : null}
      {queue.affected_data_products.length > 0 ? <p>Affected data products: {queue.affected_data_products.join(", ")}. This describes waiting or failed work, not data freshness.</p> : null}
      <QueueFailureGroups label="Dead-letter causes" groups={queue.dead_letter_groups} />
      <QueueFailureGroups label="Legacy failure causes" groups={queue.failed_groups} />
    </> : null}
    <ul>{workers.map(({ label, status, error: workerError, isLoading: workerLoading }) => {
      const failures = Object.values(status?.current_failures ?? {});
      return <li key={label}><strong>{label}: {workerLoading ? "loading" : workerStateLabel(status, workerError)}</strong>
        {workerError || (!workerLoading && !status) ? <p role="alert">Worker status unavailable. Refresh status before deciding whether to run work.</p> : failures.map((failure) => <p role="status" key={failure.phase}>{failure.phase}: {failure.safe_message} {failure.guidance} Observed {formatTimestamp(failure.occurred_at)}; {formatCount(failure.count, "failure")} in this phase.</p>)}
        {!workerError && status?.last_failure && failures.length === 0 ? <p className="muted">Previous failure: {status.last_failure.safe_message} {formatTimestamp(status.last_failure.occurred_at)}. No current failure is recorded.</p> : null}
      </li>;
    })}</ul>
    <p className="muted">Worker states and failure history describe this API session. Starting a worker, running a cycle, refreshing prices, or forcing readiness can contact providers and change local data.</p>
    </div>
  </section>;
}

function QueueFailureGroups({ label, groups }: { label: string; groups: IngestionQueueStatus["dead_letter_groups"] }) {
  return groups.length > 0 ? <details>
    <summary>{label} ({formatCount(groups.length, "group")})</summary>
    <p className="muted">Provider names are inferred from stored error signatures; unknown means no clear provider attribution. Raw error payloads are omitted.</p>
    <ul>{groups.map((group) => <li key={`${group.provider}:${group.error_category}`}>
      <strong>{group.provider}: {formatCount(group.count, "job")}</strong> — {group.safe_message} {group.guidance}
    </li>)}</ul>
  </details> : null;
}

function IngestionBackgroundCard({
  status,
  isLoading,
  error,
  currentPendingCount,
  isCurrentPendingLoading,
  currentPendingError,
  onStart,
  onStop,
  onTick,
  isBusy,
}: {
  status?: IngestionBackgroundStatus;
  isLoading: boolean;
  error: Error | null;
  currentPendingCount?: number;
  isCurrentPendingLoading: boolean;
  currentPendingError: Error | null;
  onStart: () => void;
  onStop: () => void;
  onTick: () => void;
  isBusy: boolean;
}) {
  const stateLabel = workerStateLabel(status, error);
  return <section className="card operations-background">
    <div className="card-heading">
      <div><p className="eyebrow">Background due work</p><h2>Routine ingestion worker</h2></div>
      <div className="card-tools"><HelpDisclosure title="Ingestion basics" items={ingestionHelp} /><span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Last scheduled" value={isLoading ? "Loading" : formatCount(status?.last_schedule_count, "job")} />
        <Signal label="Last completed" value={isLoading ? "Loading" : formatCount(status?.last_completed_count, "job")} />
        <Signal label="Completed since start" value={isLoading ? "Loading" : formatCount(status?.completed_since_start, "job")} />
        <Signal label="Last queue progress" value={isLoading ? "Loading" : formatTimestamp(status?.last_progress_at)} />
        <Signal label="Schedule cadence" value={status ? formatDuration(status.schedule_interval_seconds) : "Unavailable"} />
        <Signal label="Idle run cadence" value={status ? `${formatDuration(status.run_interval_seconds)} / ${status.max_run_batches_per_tick} batches` : "Unavailable"} />
        <Signal label="Productive backlog cadence" value={status ? formatDuration(status.backlog_interval_seconds) : "Unavailable"} />
        <Signal label="Current pending jobs" value={currentQueueCount(currentPendingCount, isCurrentPendingLoading, currentPendingError)} />
        <Signal label="Pending after last cycle" value={isLoading ? "Loading" : formatCount(status?.last_pending_count, "job")} />
        <div className="background-actions">
          <button className={status?.enabled ? "" : "primary"} onClick={() => window.confirm("Start the routine ingestion worker for this API session? It will schedule due work and run bounded batches in the background.") && onStart()} disabled={isBusy || isLoading || status?.enabled}>Start worker</button>
          <button onClick={() => window.confirm("Stop the routine ingestion worker? Manual controls will still work.") && onStop()} disabled={isBusy || isLoading || !status?.enabled}>Stop worker</button>
          <button onClick={() => window.confirm("Run one background worker cycle now? This schedules due routine jobs and runs a bounded batch.") && onTick()} disabled={isBusy || isLoading}><RefreshCw size={17}/>Run one cycle</button>
        </div>
        <div className="background-status-note">
          <strong>Routine ingestion is {stateLabel}.</strong>
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
  const stateLabel = workerStateLabel(status, error);
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
          <strong>Holding price maintenance is {stateLabel}.</strong>
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
  currentPendingCount,
  isCurrentPendingLoading,
  currentPendingError,
  onStart,
  onStop,
  onTick,
  isBusy,
}: {
  status?: DataReadinessWorkerStatus;
  isLoading: boolean;
  error: Error | null;
  currentPendingCount?: number;
  isCurrentPendingLoading: boolean;
  currentPendingError: Error | null;
  onStart: () => void;
  onStop: () => void;
  onTick: () => void;
  isBusy: boolean;
}) {
  const stateLabel = workerStateLabel(status, error);
  return <section className="card operations-background">
    <div className="card-heading">
      <div><p className="eyebrow">Valuation readiness</p><h2>Portfolio data worker</h2></div>
      <div className="card-tools"><span className={`pill ${status?.running ? "running" : status?.enabled ? "done" : ""}`}>{isLoading ? "loading" : stateLabel}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : (
      <div className="background-status-grid">
        <Signal label="Ready tickers" value={isLoading ? "Loading" : status?.last_ready_count == null || status.last_target_count == null ? "Unknown" : `${status.last_ready_count}/${status.last_target_count}`} />
        <Signal label="Valuations" value={isLoading ? "Loading" : formatCount(status?.last_valuation_count, "holding")} />
        <Signal label="Poll cadence" value={status ? formatDuration(status.poll_interval_seconds) : "Unavailable"} />
        <Signal label="Current pending jobs" value={currentQueueCount(currentPendingCount, isCurrentPendingLoading, currentPendingError)} />
        <Signal label="Pending after last check" value={isLoading ? "Loading" : formatCount(status?.last_pending_count, "job")} />
        <div className="background-actions">
          <button className={status?.enabled ? "" : "primary"} onClick={() => window.confirm("Start the portfolio data readiness worker for this API session? It schedules missing stock/CDR valuation inputs and calculates portfolio valuations.") && onStart()} disabled={isBusy || isLoading || status?.enabled}>Start worker</button>
          <button onClick={() => window.confirm("Stop the portfolio data readiness worker?") && onStop()} disabled={isBusy || isLoading || !status?.enabled}>Stop worker</button>
          <button onClick={() => window.confirm("Run one valuation readiness cycle now?") && onTick()} disabled={isBusy || isLoading}><RefreshCw size={17}/>Force readiness</button>
        </div>
        <div className="background-status-note">
          <strong>Portfolio data maintenance is {stateLabel}.</strong>
          <span>{status ? dataReadinessStatusDetail(status) : "Status has not loaded yet."}</span>
          {status?.last_missing?.length ? <em>{status.last_missing.slice(0, 3).join(" | ")}</em> : null}
          {status?.last_error ? <em>{status.last_error}</em> : null}
        </div>
      </div>
    )}
  </section>;
}

function currentQueueCount(count: number | undefined, isLoading: boolean, error: Error | null): string {
  if (error) return "Unavailable";
  if (isLoading || count === undefined) return "Loading";
  return formatCount(count, "job");
}

function RetailSentimentCard({
  status,
  isLoading,
  error,
  onSchedule,
  onRun,
  isBusy,
}: {
  status?: RetailSentimentStatus;
  isLoading: boolean;
  error: Error | null;
  onSchedule: () => void;
  onRun: () => void;
  isBusy: boolean;
}) {
  const totalPosts = status?.providers.reduce((sum, provider) => sum + provider.post_count, 0) ?? 0;
  return <section className="card operations-readiness">
    <div className="card-heading">
      <div><p className="eyebrow">Retail sentiment</p><h2>Social sentiment ingestion</h2></div>
      <div className="card-tools"><span>{isLoading ? "loading" : formatCount(totalPosts, "post")}</span></div>
    </div>
    {error ? <ErrorPanel error={error} /> : isLoading ? <Loading compact /> : status ? (
      <div className="retail-sentiment-grid">
        <div className="background-status-grid compact">
          {status.providers.map((provider) => (
            <div className="status-card" key={provider.provider}>
              <strong>{provider.provider === "x" ? "X" : "Reddit"}</strong>
              <span className={`pill ${provider.configured ? "done" : "failed"}`}>{provider.configured ? "configured" : "missing credentials"}</span>
              <p>{formatCount(provider.post_count, "stored post")} · latest {formatTimestamp(provider.latest_post_at)}</p>
              <p>{formatCount(provider.open_jobs, "open job")} · {formatCount(provider.failed_jobs, "failed job")}</p>
              {provider.latest_error ? <em>{provider.latest_error}</em> : null}
            </div>
          ))}
          <Signal label="Pending social jobs" value={formatCount(status.pending_jobs, "job")} />
          <Signal label="Running social jobs" value={formatCount(status.running_jobs, "job")} />
          <Signal label="Failed social jobs" value={formatCount(status.failed_jobs, "job")} />
          <div className="background-actions">
            <button onClick={() => window.confirm("Schedule missing or stale retail sentiment jobs for the selected ranking universe?") && onSchedule()} disabled={isBusy}>Schedule retail</button>
            <button className="primary" onClick={() => window.confirm("Run up to 10 pending sentiment jobs now? Live providers require configured credentials.") && onRun()} disabled={isBusy}><RefreshCw size={17}/>Run sentiment</button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Ticker</th><th>Date</th><th>Retail score</th><th>Reddit</th><th>X</th><th>Momentum</th><th>Volume</th></tr></thead>
            <tbody>{status.latest_snapshots.map((item) => <tr key={`${item.asset_id}-${item.date}`}><td>{item.ticker}</td><td>{new Date(item.date).toLocaleDateString()}</td><td>{percent(item.retail_sentiment_score)}</td><td>{item.reddit_post_count}</td><td>{item.x_post_count}</td><td>{signedNumber(item.sentiment_momentum_1d, 2)}</td><td>{item.unusual_volume_flag ? "unusual" : "normal"}</td></tr>)}</tbody>
          </table>
          {!status.latest_snapshots.length ? <EmptyRow text="No daily retail sentiment snapshots are stored yet." /> : null}
        </div>
        <div className="mini-list news-mini-list">
          {status.recent_posts.map((post) => {
            const headline = post.title || post.body || `${post.provider} post`;
            return <article key={`${post.provider}-${post.asset_id}-${post.published_at}-${headline}`}>
              <div>
                {post.url ? <a href={post.url} target="_blank" rel="noreferrer"><strong>{headline}</strong></a> : <strong>{headline}</strong>}
                <span>{[post.ticker, post.source_name, formatTimestamp(post.published_at)].join(" · ")}</span>
              </div>
              <span>{post.provider === "x" ? `likes ${post.like_count ?? 0}` : `score ${post.score ?? 0}`}</span>
              <b>{percent(post.relevance_score)}</b>
            </article>;
          })}
          {!status.recent_posts.length ? <EmptyRow text="No recent mapped social posts found. Schedule and run retail sentiment ingestion to populate this feed." /> : null}
        </div>
      </div>
    ) : <EmptyRow text="Retail sentiment status is unavailable." />}
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
