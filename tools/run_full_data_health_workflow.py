"""Drive the local app toward full portfolio data health.

This workflow coordinates the existing API control plane:

- start/tick readiness, routine ingestion, and market freshness workers
- retry failed jobs and drain pending jobs
- scan API payloads for unresolved loading/null/missing-data signals
- optionally compare a bounded price sample against Yahoo Finance chart data

It is intentionally non-destructive by default. Use ``--clear-history`` only
when you deliberately want to delete ingestion jobs and sync-state evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


CRITICAL_NUMERIC_KEYS = {
    "market_value",
    "book_cost",
    "unrealized_gain",
    "unrealized_return_percent",
    "total_gain",
    "total_return_percent",
    "projected_value",
    "projected_value_low",
    "projected_value_high",
    "expected_cagr",
    "expected_volatility",
    "expected_sharpe",
    "beta",
    "pe_ratio",
    "price_to_free_cash_flow",
    "margin_of_safety",
    "latest_price",
    "price",
    "weight",
}

TEXT_FAILURE_MARKERS = (
    "unavailable",
    "missing",
    "failed",
    "no data",
    "loading dashboard data",
)


@dataclass
class Finding:
    severity: str
    source: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class ApiClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
                if not text:
                    return None
                return json.loads(text)
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {text}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"{method} {path} timed out after {self.timeout:g}s") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, payload or {})

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--web-base", default="http://localhost:5173")
    parser.add_argument("--db", default="data/persistent_db.db")
    parser.add_argument("--cycles", type=int, default=4)
    parser.add_argument("--run-batches", type=int, default=10)
    parser.add_argument("--max-jobs", type=int, default=25)
    parser.add_argument("--max-assets", type=int, default=100)
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--external-audit", action="store_true")
    parser.add_argument("--external-sample", type=int, default=12)
    parser.add_argument("--price-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--clear-history", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", help="Write the full JSON report to this path.")
    args = parser.parse_args()

    client = ApiClient(args.api_base, timeout=45)
    findings: list[Finding] = []
    actions: list[dict[str, Any]] = []

    try:
        health = client.get("/health")
    except RuntimeError as exc:
        print(f"API is not healthy: {exc}", file=sys.stderr)
        return 2
    actions.append({"action": "health", "result": health})

    if args.clear_history:
        actions.append({"action": "clear_ingestion_history", "result": client.delete("/ingestion/jobs")})

    for worker_path in (
        "/ingestion/background/start",
        "/data/readiness/start",
        "/market/freshness/start",
    ):
        actions.append({"action": worker_path, "result": client.post(worker_path)})

    for cycle in range(1, args.cycles + 1):
        cycle_actions: dict[str, Any] = {"cycle": cycle}
        cycle_actions["retry_failed"] = call_action(
            client,
            findings,
            "POST /ingestion/retry-failed",
            lambda: client.post("/ingestion/retry-failed", {"domain": None, "max_jobs": 100}),
        )
        cycle_actions["schedule_all"] = call_action(
            client,
            findings,
            "POST /ingestion/schedule",
            lambda: client.post(
                "/ingestion/schedule",
                {
                    "pipeline": "all",
                    "max_assets": args.max_assets,
                    "years": args.years,
                    "prices_only": False,
                    "missing_only": False,
                    "stale_only": True,
                },
            ),
        )
        cycle_actions["data_readiness_tick"] = call_action(
            client,
            findings,
            "POST /data/readiness/tick",
            lambda: client.post("/data/readiness/tick"),
        )
        cycle_actions["ingestion_background_tick"] = call_action(
            client,
            findings,
            "POST /ingestion/background/tick",
            lambda: client.post("/ingestion/background/tick"),
        )
        cycle_actions["market_freshness_tick"] = call_action(
            client,
            findings,
            "POST /market/freshness/tick",
            lambda: client.post("/market/freshness/tick"),
        )
        completed = 0
        for _ in range(args.run_batches):
            result = call_action(
                client,
                findings,
                "POST /ingestion/run",
                lambda: client.post("/ingestion/run", {"domain": "all", "max_jobs": args.max_jobs}),
            )
            if result.get("error"):
                break
            count = int(result.get("result", {}).get("completed_jobs", 0))
            completed += count
            if count < args.max_jobs:
                break
        cycle_actions["completed_jobs"] = completed
        actions.append(cycle_actions)
        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    report = scan_api(client, findings)
    report["streaming"] = scan_streaming_api(client, findings)
    if args.external_audit:
        report["external_price_audit"] = external_price_audit(
            report.get("aggregate_positions", []),
            sample_size=args.external_sample,
            tolerance_pct=args.price_tolerance_pct,
            findings=findings,
        )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base": args.api_base,
        "web_base": args.web_base,
        "actions": actions,
        "report": report,
        "findings": [finding.__dict__ for finding in findings],
        "ok": not any(finding.severity in {"error", "critical"} for finding in findings),
    }

    rendered = json.dumps(output, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.write("\n")
    if args.json:
        print(rendered)
    else:
        print_human(output)
    return 0 if output["ok"] else 1


def call_action(
    client: ApiClient,
    findings: list[Finding],
    label: str,
    fn,
) -> dict[str, Any]:
    try:
        return fn()
    except RuntimeError as exc:
        findings.append(Finding("critical", label, "workflow action failed", {"error": str(exc)}))
        return {"error": str(exc)}


def scan_api(client: ApiClient, findings: list[Finding]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    portfolios = safe_get(client, findings, "/portfolios", fallback=[])
    report["portfolios"] = portfolios
    aggregate_positions = safe_get(client, findings, "/portfolios/aggregate/positions", fallback=[])
    report["aggregate_positions"] = aggregate_positions

    endpoints: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", "/overview/updates", None),
        ("GET", "/portfolios", None),
        ("GET", "/portfolios/aggregate/overview", None),
        ("GET", "/portfolios/aggregate/positions", None),
        ("GET", "/ingestion/readiness", None),
        ("GET", "/ingestion/ranking-readiness?universe=tracked&limit=200", None),
        ("GET", "/ingestion/jobs?limit=500", None),
        ("GET", "/ingestion/background/status", None),
        ("GET", "/data/readiness/status", None),
        ("GET", "/market/freshness/status", None),
        ("GET", "/market/streaming/status", None),
    ]
    for portfolio in portfolios:
        portfolio_id = int(portfolio["portfolio_id"])
        endpoints.extend(
            [
                ("GET", f"/portfolios/{portfolio_id}/overview", None),
                ("GET", f"/portfolios/{portfolio_id}/positions", None),
                ("GET", f"/portfolios/{portfolio_id}/performance", None),
                ("GET", f"/portfolios/{portfolio_id}/risk", None),
                ("GET", f"/portfolios/{portfolio_id}/fundamentals", None),
                (
                    "POST",
                    f"/portfolios/{portfolio_id}/optimization/preview",
                    {"objective": "max_expected_cagr", "constraints": {}},
                ),
            ]
        )

    endpoint_results: dict[str, Any] = {}
    for method, path, payload in endpoints:
        key = f"{method} {path}"
        try:
            data = client.post(path, payload) if method == "POST" else client.get(path)
            endpoint_results[key] = summarize_payload(data)
            scan_payload(key, data, findings)
            scan_endpoint_semantics(key, data, findings)
        except RuntimeError as exc:
            endpoint_results[key] = {"error": str(exc)}
            findings.append(Finding("critical", key, "endpoint failed", {"error": str(exc)}))
    report["endpoints"] = endpoint_results
    return report


def safe_get(
    client: ApiClient,
    findings: list[Finding],
    path: str,
    fallback: Any,
) -> Any:
    try:
        return client.get(path)
    except RuntimeError as exc:
        findings.append(Finding("critical", f"GET {path}", "endpoint failed", {"error": str(exc)}))
        return fallback


def summarize_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {"type": "list", "count": len(data)}
    if isinstance(data, dict):
        summary = {"type": "object", "keys": sorted(data.keys())[:30]}
        for key in ("total", "ready_count", "status", "solver_message"):
            if key in data:
                summary[key] = data[key]
        if "items" in data and isinstance(data["items"], list):
            summary["items"] = len(data["items"])
        return summary
    return {"type": type(data).__name__}


def scan_payload(source: str, data: Any, findings: list[Finding], path: str = "$") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            next_path = f"{path}.{key}"
            if (
                key in CRITICAL_NUMERIC_KEYS
                and value is None
                and not _null_metric_is_not_applicable(data, key)
            ):
                findings.append(Finding("error", source, "critical metric is null", {"path": next_path}))
            if key == "missing_inputs" and value and not _missing_inputs_are_not_applicable(data, value):
                findings.append(Finding("error", source, "missing inputs reported", {"path": next_path, "value": value}))
            if key in {"warnings", "assumptions"} and value:
                findings.append(Finding("warning", source, f"{key} reported", {"path": next_path, "value": value}))
            if isinstance(value, str) and any(marker in value.lower() for marker in TEXT_FAILURE_MARKERS):
                findings.append(Finding("warning", source, "failure-like text reported", {"path": next_path, "value": value}))
            scan_payload(source, value, findings, next_path)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            scan_payload(source, item, findings, f"{path}[{index}]")


def _null_metric_is_not_applicable(parent: dict[str, Any], key: str) -> bool:
    allocation = str(parent.get("allocation_class") or "").lower()
    if allocation in {"etf", "money market", "fixed income", "cash"} and key in {
        "pe_ratio",
        "price_to_free_cash_flow",
        "margin_of_safety",
    }:
        return True
    return (
        key in {"price_to_free_cash_flow", "margin_of_safety"}
        and parent.get("fcf_metrics_applicable") is False
    )


def _missing_inputs_are_not_applicable(parent: dict[str, Any], values: Any) -> bool:
    if not isinstance(values, list):
        return False
    allocation = str(parent.get("allocation_class") or "").lower()
    normalized = {str(value).lower() for value in values}
    if allocation in {"etf", "money market", "fixed income", "cash"}:
        return normalized <= {"p/e", "p/fcf"}
    if parent.get("fcf_metrics_applicable") is False:
        return normalized <= {"p/fcf"}
    return False


def scan_endpoint_semantics(source: str, data: Any, findings: list[Finding]) -> None:
    if source.startswith("GET /ingestion/readiness") and isinstance(data, dict):
        total = int(data.get("total", 0))
        ready = int(data.get("ready_count", 0))
        if ready != total:
            findings.append(Finding("error", source, "not all ingestion assets are ready", {"ready": ready, "total": total}))
    if source.startswith("GET /ingestion/ranking-readiness") and isinstance(data, dict):
        total = int(data.get("total", 0))
        ready = int(data.get("ready_count", 0))
        if ready != total:
            findings.append(Finding("error", source, "not all ranking inputs are ready", {"ready": ready, "total": total}))
    if source.startswith("GET /ingestion/jobs") and isinstance(data, list):
        open_jobs = [job for job in data if job.get("status") in {"pending", "running", "failed"}]
        if open_jobs:
            findings.append(
                Finding(
                    "error",
                    source,
                    "ingestion jobs remain open or failed",
                    {"count": len(open_jobs), "sample": open_jobs[:10]},
                )
            )
    if source.startswith("POST /portfolios/") and source.endswith("/optimization/preview"):
        if isinstance(data, dict) and data.get("status") != "success":
            findings.append(Finding("error", source, "optimization preview did not succeed", {"status": data.get("status"), "message": data.get("solver_message")}))


def external_price_audit(
    positions: list[dict[str, Any]],
    *,
    sample_size: int,
    tolerance_pct: float,
    findings: list[Finding],
) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in positions
        if item.get("symbol") and item.get("latest_price") is not None
    ]
    candidates.sort(key=lambda item: float(item.get("market_value") or 0), reverse=True)
    results: list[dict[str, Any]] = []
    for item in candidates[:sample_size]:
        symbol = str(item["symbol"])
        local_price = float(item["latest_price"])
        external = fetch_yahoo_chart_price(symbol)
        result = {
            "asset_id": item.get("asset_id"),
            "symbol": symbol,
            "local_price": local_price,
            "external_price": external,
            "source": "query1.finance.yahoo.com/v8/finance/chart",
        }
        if external is not None and local_price > 0:
            delta_pct = abs(external - local_price) / local_price * 100
            result["delta_pct"] = delta_pct
            if not math.isfinite(delta_pct) or delta_pct > tolerance_pct:
                findings.append(Finding("error", "external_price_audit", "price mismatch above tolerance", result))
        else:
            findings.append(Finding("warning", "external_price_audit", "external price unavailable", result))
        results.append(result)
    return results


def scan_streaming_api(client: ApiClient, findings: list[Finding]) -> dict[str, Any]:
    streaming = safe_get(client, findings, "/market/streaming/status", fallback={})
    subscriptions = streaming.get("subscriptions", []) if isinstance(streaming, dict) else []
    missing = streaming.get("missing_current_price_symbols", []) if isinstance(streaming, dict) else []
    provider_health = streaming.get("provider_health", []) if isinstance(streaming, dict) else []

    if not subscriptions:
        findings.append(Finding("error", "streaming", "no live price subscriptions resolved"))
    if missing:
        findings.append(
            Finding(
                "error",
                "streaming",
                "subscribed tickers are missing current live-price rows",
                {"count": len(missing), "symbols": missing[:50]},
            )
        )
    if provider_health and isinstance(provider_health[0], dict):
        degraded = [row for row in provider_health if str(row.get("status")).lower() != "healthy"]
    else:
        degraded = [row for row in provider_health if str(row[1]).lower() != "healthy"]
    if degraded:
        findings.append(
            Finding(
                "error",
                "streaming",
                "live price provider health is degraded",
                {"providers": degraded},
            )
        )

    return streaming


def fetch_yahoo_chart_price(symbol: str) -> float | None:
    encoded = quote(symbol, safe="")
    query = urlencode({"range": "5d", "interval": "1d"})
    request = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return None
    quote_data = (result.get("indicators", {}).get("quote") or [None])[0] or {}
    closes = quote_data.get("close") or []
    for value in reversed(closes):
        if value is not None:
            return float(value)
    return None


def print_human(output: dict[str, Any]) -> None:
    print(f"Full data health workflow: {'PASS' if output['ok'] else 'ATTENTION REQUIRED'}")
    print(f"Generated: {output['generated_at']}")
    print(f"API: {output['api_base']}")
    print(f"Actions: {len(output['actions'])}")
    findings = output["findings"]
    if not findings:
        print("Findings: none")
        return
    print(f"Findings: {len(findings)}")
    for item in findings[:50]:
        print(f"- [{item['severity']}] {item['source']}: {item['message']}")
        if item.get("detail"):
            print(f"  {json.dumps(item['detail'], default=str)[:500]}")
    if len(findings) > 50:
        print(f"... {len(findings) - 50} more finding(s) omitted; rerun with --json for full detail.")


if __name__ == "__main__":
    raise SystemExit(main())
