import { createRequire } from "node:module";

const requireFromCwd = createRequire(`${process.cwd()}/package.json`);
const { chromium } = requireFromCwd("@playwright/test");

const webBase = process.argv.find((arg) => arg.startsWith("--web-base="))?.split("=")[1] ?? "http://localhost:5173";
const apiBase = process.argv.find((arg) => arg.startsWith("--api-base="))?.split("=")[1] ?? "http://127.0.0.1:8000/api/v1";
const waitMs = Number(process.argv.find((arg) => arg.startsWith("--wait-ms="))?.split("=")[1] ?? "2500");
const settleMs = Number(process.argv.find((arg) => arg.startsWith("--settle-ms="))?.split("=")[1] ?? "10000");

const failureMarkers = [
  "Unavailable",
  "Loading dashboard data",
  "no data",
  "failed jobs",
  "missing",
  "Unable to",
];

async function apiJson(path, init = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${path} returned HTTP ${response.status}`);
  }
  return response.json();
}

function routePath(path) {
  return `${webBase.replace(/\/$/, "")}${path}`;
}

async function main() {
  const health = await apiJson("/health");
  const portfolios = await apiJson("/portfolios");
  const routes = [
    "/",
    "/portfolios",
    "/portfolios?tab=aggregate",
    "/portfolios?tab=portfolios",
    "/portfolios?tab=fundamentals",
    "/signals",
    "/benchmarks",
    "/brokers",
    "/operations",
    "/settings",
  ];
  for (const portfolio of portfolios) {
    const id = portfolio.portfolio_id;
    routes.push(
      `/portfolios/${id}?tab=overview`,
      `/portfolios/${id}?tab=holdings`,
      `/portfolios/${id}?tab=performance`,
      `/portfolios/${id}?tab=risk`,
      `/portfolios/${id}?tab=optimization`,
      `/portfolios/${id}?tab=fundamentals`,
      `/portfolios/${id}?tab=activity`,
    );
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
  const findings = [];
  const routeResults = [];
  const consoleErrors = [];
  const failedRequests = [];

  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleErrors.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({ url: request.url(), failure: request.failure()?.errorText });
  });

  for (const route of routes) {
    consoleErrors.length = 0;
    failedRequests.length = 0;
    const response = await page.goto(routePath(route), { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(waitMs);
    const deadline = Date.now() + settleMs;
    while (Date.now() < deadline) {
      const currentText = await page.locator("body").innerText();
      if (!currentText.includes("Loading dashboard data")) {
        break;
      }
      await page.waitForTimeout(500);
    }
    const text = await page.locator("body").innerText();
    const markers = failureMarkers.filter((marker) => text.toLowerCase().includes(marker.toLowerCase()));
    const realFailedRequests = failedRequests.filter((request) => request.failure !== "net::ERR_ABORTED");
    const result = {
      route,
      status: response?.status(),
      title: await page.title(),
      markers,
      consoleErrors: [...consoleErrors],
      failedRequests: realFailedRequests,
      textStart: text.slice(0, 500),
    };
    routeResults.push(result);
    if (!response || response.status() >= 400) {
      findings.push({ severity: "critical", route, message: "route failed", detail: { status: response?.status() } });
    }
    for (const marker of markers) {
      findings.push({ severity: marker === "Loading dashboard data" ? "error" : "warning", route, message: `marker found: ${marker}` });
    }
    for (const request of realFailedRequests) {
      findings.push({ severity: "critical", route, message: "request failed", detail: request });
    }
    for (const error of consoleErrors) {
      findings.push({ severity: "error", route, message: "console issue", detail: error });
    }
  }

  await browser.close();
  const output = {
    generatedAt: new Date().toISOString(),
    health,
    routeCount: routes.length,
    ok: !findings.some((finding) => ["critical", "error"].includes(finding.severity)),
    findings,
    routeResults,
  };
  console.log(JSON.stringify(output, null, 2));
  process.exitCode = output.ok ? 0 : 1;
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: String(error), stack: error.stack }, null, 2));
  process.exitCode = 2;
});
