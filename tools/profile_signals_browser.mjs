import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const webRequire = createRequire(pathToFileURL(path.join(repoRoot, "web", "package.json")));
const { chromium } = webRequire("@playwright/test");

const args = parseArgs(process.argv.slice(2));
const outputPath = path.resolve(repoRoot, args.output);

const report = {
  url: args.url,
  apiBase: args.apiBase,
  repeats: args.repeats,
  startedAt: new Date().toISOString(),
  api: [],
  browser: [],
};

for (let index = 0; index < args.repeats; index += 1) {
  report.api.push(await measureFetch(`${args.apiBase}/api/v1/signals${args.query ? `?${args.query}` : ""}`));
}

const browser = await chromium.launch();
try {
  for (let index = 0; index < args.repeats; index += 1) {
    report.browser.push(await measureBrowser(browser, args.url, index + 1));
  }
} finally {
  await browser.close();
}

report.summary = summarize(report);
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2), "utf8");
printSummary(report);
console.log(`\nWrote JSON report: ${outputPath}`);

async function measureFetch(url) {
  const started = performance.now();
  const response = await fetch(url, { headers: { "Cache-Control": "no-cache" } });
  const text = await response.text();
  const elapsedMs = performance.now() - started;
  let itemCount = null;
  let total = null;
  try {
    const parsed = JSON.parse(text);
    itemCount = Array.isArray(parsed.items) ? parsed.items.length : null;
    total = typeof parsed.total === "number" ? parsed.total : null;
  } catch {
    // Keep the timing even if the API returned an error page.
  }
  return {
    url,
    status: response.status,
    totalMs: round(elapsedMs),
    bytes: Buffer.byteLength(text),
    itemCount,
    total,
  };
}

async function measureBrowser(browser, url, iteration) {
  const context = await browser.newContext({ viewport: { width: args.width, height: args.height } });
  const page = await context.newPage();
  const requests = new Map();
  const finished = [];
  const failures = [];
  const consoleErrors = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    requests.set(request, performance.now());
  });
  page.on("requestfinished", async (request) => {
    const started = requests.get(request);
    if (started === undefined) return;
    const response = await request.response();
    finished.push({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
      status: response?.status() ?? null,
      totalMs: round(performance.now() - started),
    });
  });
  page.on("requestfailed", (request) => {
    const started = requests.get(request);
    failures.push({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
      error: request.failure()?.errorText ?? "unknown",
      totalMs: started === undefined ? null : round(performance.now() - started),
    });
  });

  const started = performance.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Signals", exact: true }).waitFor({ state: "visible" });
  const headingVisibleMs = performance.now() - started;
  await page
    .locator("text=/matching signals|No active signals|No signals match/")
    .first()
    .waitFor({ state: "visible", timeout: args.dataReadyTimeout })
    .catch(() => undefined);
  const dataReadyMs = performance.now() - started;
  await page.waitForLoadState("networkidle", { timeout: args.networkIdleTimeout }).catch(() => undefined);
  const totalMs = performance.now() - started;
  const pending = [...requests.entries()]
    .filter(([request]) => !finished.some((item) => item.url === request.url()) && !failures.some((item) => item.url === request.url()))
    .map(([request, requestStarted]) => ({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
      pendingMs: round(performance.now() - requestStarted),
    }));
  const metrics = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0]?.toJSON?.() ?? null;
    const paints = Object.fromEntries(performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]));
    const resources = performance.getEntriesByType("resource").map((entry) => ({
      name: entry.name,
      initiatorType: entry.initiatorType,
      duration: entry.duration,
      transferSize: entry.transferSize,
      decodedBodySize: entry.decodedBodySize,
    }));
    return {
      navigation: nav,
      paints,
      resources,
      dom: {
        nodes: document.getElementsByTagName("*").length,
        height: document.documentElement.scrollHeight,
        width: document.documentElement.scrollWidth,
      },
    };
  });
  await context.close();

  return {
    iteration,
    totalMs: round(totalMs),
    headingVisibleMs: round(headingVisibleMs),
    dataReadyMs: round(dataReadyMs),
    consoleErrors,
    requestFailures: failures,
    pendingRequests: pending,
    requests: finished.sort((left, right) => right.totalMs - left.totalMs),
    metrics,
  };
}

function summarize(data) {
  const api = data.api.map((item) => item.totalMs);
  const browser = data.browser.map((item) => item.totalMs);
  const heading = data.browser.map((item) => item.headingVisibleMs);
  const dataReady = data.browser.map((item) => item.dataReadyMs);
  const slowRequests = data.browser
    .flatMap((item) => [
      ...item.requests,
      ...item.pendingRequests.map((request) => ({ ...request, totalMs: request.pendingMs, status: "pending" })),
    ])
    .filter((item) => item.url.includes("/api/") || item.resourceType === "script")
    .sort((left, right) => right.totalMs - left.totalMs)
    .slice(0, 12);
  return {
    apiAvgMs: avg(api),
    browserAvgMs: avg(browser),
    headingVisibleAvgMs: avg(heading),
    dataReadyAvgMs: avg(dataReady),
    slowRequests,
  };
}

function printSummary(data) {
  console.log("Signals browser profile");
  console.log(`  url: ${data.url}`);
  console.log(`  direct API avg: ${data.summary.apiAvgMs} ms`);
  console.log(`  heading visible avg: ${data.summary.headingVisibleAvgMs} ms`);
  console.log(`  signal data ready avg: ${data.summary.dataReadyAvgMs} ms`);
  console.log(`  browser network-idle avg: ${data.summary.browserAvgMs} ms`);
  console.log("");
  console.log("Slowest browser requests:");
  for (const request of data.summary.slowRequests) {
    console.log(`  ${request.totalMs} ms ${request.status ?? "failed"} ${request.resourceType} ${request.url}`);
  }
  const errors = data.browser.flatMap((item) => item.consoleErrors);
  if (errors.length) {
    console.log("");
    console.log("Console errors:");
    for (const error of errors) console.log(`  ${error}`);
  }
}

function parseArgs(argv) {
  const parsed = {
    url: "http://127.0.0.1:5173/signals",
    apiBase: "http://127.0.0.1:8000",
    query: "limit=25&sort=priority",
    output: "tmp/signals-browser-profile.json",
    repeats: 3,
    width: 1440,
    height: 1000,
    networkIdleTimeout: 10_000,
    dataReadyTimeout: 120_000,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key.startsWith("--")) continue;
    index += 1;
    const name = key.slice(2);
    if (["repeats", "width", "height", "networkIdleTimeout", "dataReadyTimeout"].includes(name)) {
      parsed[name] = Number(value);
    } else if (Object.prototype.hasOwnProperty.call(parsed, name)) {
      parsed[name] = value;
    } else {
      throw new Error(`Unknown argument: ${key}`);
    }
  }
  return parsed;
}

function avg(values) {
  if (!values.length) return null;
  return round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function round(value) {
  return Math.round(value * 100) / 100;
}
