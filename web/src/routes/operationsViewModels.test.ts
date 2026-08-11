import { describe, expect, it } from "vitest";
import {
  backgroundStatusDetail,
  dataReadinessStatusDetail,
  marketFreshnessStatusDetail,
} from "./operationsViewModels";

describe("operationsViewModels", () => {
  it("formats routine ingestion worker status details", () => {
    const detail = backgroundStatusDetail({
      enabled: true,
      running: false,
      last_schedule_at: null,
      last_schedule_count: 3,
      last_run_at: null,
      last_completed_count: 2,
      last_pending_count: 4,
      last_error: null,
      schedule_interval_seconds: 3600,
      run_interval_seconds: 300,
      max_jobs_per_tick: 5,
      max_run_batches_per_tick: 2,
      max_assets_per_schedule: 25,
      years: 10,
      prices_only: false,
    });

    expect(detail).toBe(
      "Scheduled never; ran never. Drain: 2 batches, 5 jobs each, 4 pending after last cycle. Scope: 25 assets, 10 years, prices/dividends/splits.",
    );
  });

  it("formats market freshness status details", () => {
    const detail = marketFreshnessStatusDetail({
      enabled: true,
      running: false,
      last_poll_at: null,
      last_refreshed_count: 7,
      last_subscription_count: 9,
      last_error: null,
      poll_interval_seconds: 60,
      lookback_days: 1,
      max_symbols_per_tick: 10,
      include_watchlist: true,
    });

    expect(detail).toBe(
      "Polled never. 7 symbols refreshed from 9 subscriptions. Scope: 10 symbols, 1 day lookback, watchlist included.",
    );
  });

  it("formats data readiness worker status details", () => {
    const detail = dataReadinessStatusDetail({
      enabled: true,
      running: false,
      last_check_at: null,
      last_target_count: 12,
      last_ready_count: 8,
      last_valuation_count: 6,
      last_scheduled_count: 2,
      last_completed_count: 1,
      last_pending_count: 3,
      last_missing: ["prices"],
      last_error: null,
      poll_interval_seconds: 120,
      max_assets_per_tick: 10,
      max_jobs_per_batch: 5,
      max_run_batches_per_tick: 2,
      years: 10,
      min_price_rows: 120,
    });

    expect(detail).toBe(
      "Checked never. 8 readys of 12 targets; 6 valuations calculated. 3 jobs pending after last check.",
    );
  });
});
