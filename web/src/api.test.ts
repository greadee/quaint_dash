import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ ok: true })));
  });

  it("builds benchmark list query parameters", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    } as Response);

    await api.benchmarks({
      q: "SMH",
      category: "industry",
      currency: "USD",
      is_core: false,
      is_active: true,
      limit: 50,
      offset: 10,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/benchmarks?q=SMH&category=industry&currency=USD&is_core=false&is_active=true&limit=50&offset=10",
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }),
    );
  });

  it("builds benchmark history and detail calls", async () => {
    await api.benchmark("SP500");
    await api.benchmarkPrices("SP500", { start_date: "2026-01-01", end_date: "2026-06-19", limit: 10 });
    await api.benchmarkMetrics("SP500", 20);
    await api.benchmarkConstituents("SP500", { limit: 5, offset: 5, snapshot_date: "2026-01-02", source: "test", sort: "symbol" });
    await api.benchmarkExposures("SP500", { snapshot_date: "2026-01-02", dimension_type: "sector" });

    expect(fetch).toHaveBeenNthCalledWith(1, "/api/v1/benchmarks/SP500", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/v1/benchmarks/SP500/prices?limit=10&start_date=2026-01-01&end_date=2026-06-19", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(3, "/api/v1/benchmarks/SP500/metrics?limit=20", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(4, "/api/v1/benchmarks/SP500/constituents?limit=5&offset=5&snapshot_date=2026-01-02&source=test&sort=symbol", expect.any(Object));
    expect(fetch).toHaveBeenNthCalledWith(5, "/api/v1/benchmarks/SP500/exposures?snapshot_date=2026-01-02&dimension_type=sector", expect.any(Object));
  });

  it("posts benchmark actions with JSON bodies", async () => {
    await api.seedBenchmarks({ scope: "all" });
    await api.refreshBenchmark("SP500", { job_type: "daily_price", lookback_days: 10 });
    await api.refreshBenchmarks({ category: "all", job_type: "metrics" });
    await api.hardenBenchmark("SP500", { lookback_days: 730 });
    await api.hardenBenchmarks({ category: "non_core", lookback_days: 730 });

    expect(fetch).toHaveBeenNthCalledWith(1, "/api/v1/benchmarks/seed", expect.objectContaining({ method: "POST", body: JSON.stringify({ scope: "all" }) }));
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/v1/benchmarks/SP500/refresh", expect.objectContaining({ method: "POST", body: JSON.stringify({ job_type: "daily_price", lookback_days: 10 }) }));
    expect(fetch).toHaveBeenNthCalledWith(3, "/api/v1/benchmarks/refresh", expect.objectContaining({ method: "POST", body: JSON.stringify({ category: "all", job_type: "metrics" }) }));
    expect(fetch).toHaveBeenNthCalledWith(4, "/api/v1/benchmarks/SP500/harden", expect.objectContaining({ method: "POST", body: JSON.stringify({ lookback_days: 730 }) }));
    expect(fetch).toHaveBeenNthCalledWith(5, "/api/v1/benchmarks/harden", expect.objectContaining({ method: "POST", body: JSON.stringify({ category: "non_core", lookback_days: 730 }) }));
  });

  it("throws stable API error messages", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ error: { message: "Benchmark not found" } }),
    } as Response);

    await expect(api.benchmark("NOPE")).rejects.toThrow("Benchmark not found");
  });
});
