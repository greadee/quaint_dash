import type {
  DataReadinessWorkerStatus,
  IngestionBackgroundStatus,
  MarketFreshnessStatus,
  WorkerDiagnostics,
} from "../api";
import { formatCount, formatTimestamp } from "./routeFormatters";

export function workerStateLabel(status?: Partial<WorkerDiagnostics> & { enabled: boolean; running: boolean }, error?: Error | null): string {
  if (error || !status) return "unavailable";
  return status.state ?? (status.enabled ? (status.running ? "running" : "idle") : "disabled");
}

export function queueAgeLabel(seconds: number | null): string {
  if (seconds === null) return "No active backlog";
  if (seconds < 60) return "Less than a minute";
  if (seconds < 3600) return formatCount(Math.floor(seconds / 60), "minute");
  if (seconds < 86400) return formatCount(Math.floor(seconds / 3600), "hour");
  return formatCount(Math.floor(seconds / 86400), "day");
}

export function backgroundStatusDetail(status: IngestionBackgroundStatus): string {
  const schedule = `Scheduled ${formatTimestamp(status.last_schedule_at)}`;
  const run = `ran ${formatTimestamp(status.last_run_at)}`;
  const pending = status.last_pending_count === null
    ? "pending after last cycle unknown"
    : `${status.last_pending_count} pending after last cycle`;
  const scope = `${status.max_assets_per_schedule} assets, ${status.years} years, ${
    status.prices_only ? "prices only" : "prices/dividends/splits"
  }`;
  const drain = `${status.max_run_batches_per_tick} batches, ${status.max_jobs_per_tick} jobs each, ${pending}`;
  return `${schedule}; ${run}. Drain: ${drain}; productive backlog follow-up ${formatCount(status.backlog_interval_seconds, "second")}. Scope: ${scope}.`;
}

export function marketFreshnessStatusDetail(status: MarketFreshnessStatus): string {
  const lastPoll = `Polled ${formatTimestamp(status.last_poll_at)}`;
  const coverage = `${formatCount(status.last_refreshed_count, "symbol")} refreshed from ${formatCount(
    status.last_subscription_count,
    "subscription",
  )}`;
  const scope = `${status.max_symbols_per_tick} symbols, ${status.lookback_days} day lookback${
    status.include_watchlist ? ", watchlist included" : ""
  }`;
  return `${lastPoll}. ${coverage}. Scope: ${scope}. This worker refreshes held prices directly; it does not consume ingestion-queue jobs.`;
}

export function dataReadinessStatusDetail(status: DataReadinessWorkerStatus): string {
  const lastCheck = `Checked ${formatTimestamp(status.last_check_at)}`;
  const coverage = `${formatCount(status.last_ready_count, "ready")} of ${formatCount(
    status.last_target_count,
    "target",
  )}`;
  const valuation = `${formatCount(status.last_valuation_count, "valuation")} calculated`;
  return `${lastCheck}. ${coverage}; ${valuation}. ${formatCount(status.last_pending_count, "job")} pending after last check. This worker may add missing-input jobs; routine ingestion is the primary queue drainer.`;
}
