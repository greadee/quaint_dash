#!/usr/bin/env node

import { performance } from "node:perf_hooks";

const baseUrl = (process.env.QUAINT_DASH_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const repeatCount = Number.parseInt(process.env.QUAINT_DASH_PERF_REPEATS ?? "2", 10);

const endpoints = [
  ["health", "/api/v1/health"],
  ["overview", "/api/v1/overview/updates"],
  ["portfolios", "/api/v1/portfolios"],
  ["portfolio aggregate", "/api/v1/portfolios/aggregate/overview"],
  ["aggregate positions", "/api/v1/portfolios/aggregate/positions"],
  ["portfolio detail", "/api/v1/portfolios/3"],
  ["portfolio positions", "/api/v1/portfolios/3/positions"],
  ["portfolio performance", "/api/v1/portfolios/3/performance?range=1Y"],
  ["portfolio risk", "/api/v1/portfolios/3/risk?lookback=1Y&risk_free_rate=0"],
  ["portfolio fundamentals", "/api/v1/portfolios/3/fundamentals?horizon_years=5"],
  ["portfolio transactions", "/api/v1/portfolios/3/transactions?limit=25&offset=0"],
  ["portfolio news", "/api/v1/portfolios/3/news?limit=5&offset=0&sort=relevance"],
  ["holding signals", "/api/v1/holdings/signals?timeframe=1m&portfolio_id=3"],
  ["assets", "/api/v1/assets?limit=25"],
  ["asset detail", "/api/v1/assets/AAPL"],
  ["asset prices", "/api/v1/assets/AAPL/prices?limit=5000&range=1Y"],
  ["asset analytics", "/api/v1/assets/AAPL/analytics"],
  ["asset business strength", "/api/v1/assets/AAPL/business-strength"],
  ["asset news", "/api/v1/assets/AAPL/news?limit=10&offset=0&sort=recency"],
  ["asset holdings", "/api/v1/assets/AAPL/holdings"],
  ["asset activity", "/api/v1/assets/AAPL/activity?limit=20&offset=0"],
  ["news feed", "/api/v1/news"],
  ["news providers", "/api/v1/news/providers"],
  ["news categories", "/api/v1/news/categories"],
  ["retail sentiment", "/api/v1/retail-sentiment?limit=30"],
  [
    "stock rankings",
    "/api/v1/rankings/stocks?factor=aggregate&universe=tracked&direction=buy&timeframe=monthly&include_retail_sentiment=false&limit=25&offset=0",
  ],
  ["signals", "/api/v1/signals"],
  [
    "signal detail",
    "/api/v1/signals/ranking.institutional_buying.monthly.META.TO",
  ],
  ["comparison", "/api/v1/comparison/workspace?symbols=AAPL%2CMSFT&period=1Y"],
  ["asset benchmark associations", "/api/v1/benchmarks/associations/asset/AAPL"],
  ["benchmarks", "/api/v1/benchmarks?is_active=true&limit=500"],
  ["benchmark detail", "/api/v1/benchmarks/SP500"],
  ["benchmark prices", "/api/v1/benchmarks/SP500/prices?limit=1400"],
  ["benchmark metrics", "/api/v1/benchmarks/SP500/metrics?limit=365"],
  ["benchmark constituents", "/api/v1/benchmarks/SP500/constituents?limit=100&offset=0"],
  ["benchmark exposures", "/api/v1/benchmarks/SP500/exposures"],
  ["broker status", "/api/v1/brokers/status"],
  ["broker connections", "/api/v1/brokers/connections"],
  ["broker accounts", "/api/v1/brokers/accounts"],
  ["broker import preview", "/api/v1/brokers/import-preview?item_limit=25"],
  ["broker reconciliation", "/api/v1/brokers/reconciliation"],
  ["broker sync history", "/api/v1/brokers/sync-history"],
  ["ingestion jobs", "/api/v1/ingestion/jobs?limit=100"],
  ["ingestion background", "/api/v1/ingestion/background/status"],
  ["market freshness", "/api/v1/market/freshness/status"],
  ["data readiness worker", "/api/v1/data/readiness/status"],
  ["retail sentiment status", "/api/v1/ingestion/retail-sentiment/status?limit=10"],
  ["ingestion readiness", "/api/v1/ingestion/readiness"],
  ["ranking readiness", "/api/v1/ingestion/ranking-readiness?universe=tracked&limit=50"],
  ["streaming status", "/api/v1/market/streaming/status"],
];

async function measure(name, path, iteration) {
  const started = performance.now();
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(120_000),
    });
    const body = await response.arrayBuffer();
    return {
      name,
      path,
      iteration,
      status: response.status,
      duration_ms: round(performance.now() - started),
      payload_bytes: body.byteLength,
      content_encoding: response.headers.get("content-encoding"),
      cache_control: response.headers.get("cache-control"),
      etag: response.headers.get("etag"),
    };
  } catch (error) {
    return {
      name,
      path,
      iteration,
      status: "error",
      duration_ms: round(performance.now() - started),
      payload_bytes: 0,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function runSequential() {
  const results = [];
  for (const [name, path] of endpoints) {
    for (let iteration = 1; iteration <= repeatCount; iteration += 1) {
      results.push(await measure(name, path, iteration));
    }
  }
  return results;
}

async function runHealthBurst() {
  const started = performance.now();
  return Promise.all(
    Array.from({ length: 8 }, async (_, index) => {
      const result = await measure(`health burst ${index + 1}`, `/api/v1/health?burst=${index + 1}`, 1);
      return { ...result, completed_from_start_ms: round(performance.now() - started) };
    }),
  );
}

function summarize(results) {
  const grouped = new Map();
  for (const result of results) {
    const current = grouped.get(result.name) ?? [];
    current.push(result);
    grouped.set(result.name, current);
  }
  return Array.from(grouped, ([name, rows]) => ({
    name,
    path: rows[0].path,
    status: rows.map((row) => row.status).join(","),
    cold_ms: rows[0].duration_ms,
    repeat_ms: rows.at(-1).duration_ms,
    payload_bytes: Math.max(...rows.map((row) => row.payload_bytes)),
    cache_control: rows[0].cache_control ?? null,
    etag: rows[0].etag ?? null,
  }));
}

function round(value) {
  return Math.round(value * 10) / 10;
}

const sequential = await runSequential();
const healthBurst = await runHealthBurst();
const report = {
  generated_at: new Date().toISOString(),
  base_url: baseUrl,
  repeat_count: repeatCount,
  summary: summarize(sequential),
  sequential,
  health_burst: healthBurst,
};

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
