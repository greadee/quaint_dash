import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const webRequire = createRequire(pathToFileURL(path.join(repoRoot, "web", "package.json")));
const { chromium } = webRequire("@playwright/test");

const settings = {
  url: "http://127.0.0.1:5173/benchmarks",
  output: "tmp/benchmarks-browser-profile.json",
  latencyMs: 250,
  routeReadyBudgetMs: 1_000,
  initialBenchmarkRequestBudget: 1,
  initialPageApiRequestBudget: 2,
  summaryPayloadBudgetBytes: 300_000,
};

for (let index = 2; index < process.argv.length; index += 2) {
  const name = process.argv[index]?.replace(/^--/, "");
  const value = process.argv[index + 1];
  if (!(name in settings) || value === undefined) throw new Error(`Unknown or incomplete argument: ${process.argv[index]}`);
  settings[name] = name === "url" || name === "output" ? value : Number(value);
}

const browser = await chromium.launch();
let report;
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const requests = [];

  await page.route("**/api/v1/benchmarks?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/benchmarks") {
      await new Promise((resolve) => setTimeout(resolve, settings.latencyMs));
    }
    await route.continue();
  });
  page.on("response", async (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/v1/")) return;
    requests.push({ method: response.request().method(), path: `${url.pathname}${url.search}`, status: response.status() });
  });

  const summaryResponseReady = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/benchmarks");
  const started = performance.now();
  await page.goto(settings.url, { waitUntil: "domcontentloaded" });
  const summaryResponse = await summaryResponseReady;
  const summaryBytes = (await summaryResponse.body()).byteLength;
  await page.locator(".benchmark-explorer .benchmark-table-wrap, .benchmark-explorer .benchmark-empty").first().waitFor({ state: "visible", timeout: settings.routeReadyBudgetMs });
  const routeReadyMs = performance.now() - started;
  await page.waitForTimeout(100);

  const benchmarkRequests = requests.filter((item) => item.path.startsWith("/api/v1/benchmarks"));
  const detailRequests = benchmarkRequests.filter((item) => /^\/api\/v1\/benchmarks\/[^?]/.test(item.path));
  const checks = {
    routeReady: routeReadyMs <= settings.routeReadyBudgetMs,
    initialBenchmarkRequests: benchmarkRequests.length <= settings.initialBenchmarkRequestBudget,
    initialPageApiRequests: requests.length <= settings.initialPageApiRequestBudget,
    summaryPayload: summaryBytes > 0 && summaryBytes <= settings.summaryPayloadBudgetBytes,
    noEagerDetails: detailRequests.length === 0,
    successfulApiRequests: requests.every((item) => item.status >= 200 && item.status < 300),
  };
  report = {
    measuredAt: new Date().toISOString(),
    settings,
    measurements: {
      routeReadyMs: Math.round(routeReadyMs * 100) / 100,
      summaryPayloadBytes: summaryBytes,
      initialApiRequestCount: requests.length,
      initialBenchmarkRequestCount: benchmarkRequests.length,
    },
    requests,
    checks,
    passed: Object.values(checks).every(Boolean),
  };
  await context.close();
} finally {
  await browser.close();
}

const outputPath = path.resolve(repoRoot, settings.output);
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;
