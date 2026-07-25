"""Profile the backend signals service against a local DuckDB database."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import duckdb  # noqa: E402

from dashboard.api.services import PortfolioApiService  # noqa: E402


DEFAULT_DB_PATH = ROOT / "data" / "persistent_db.db"
PROFILED_METHODS = [
    "signals_summary",
    "signal_detail",
    "refresh_signal_snapshots",
    "_stored_signal_rows",
    "_current_signal_rows",
    "_stock_ranking_universe",
    "_ensure_stock_ranking_inputs",
    "_portfolio_impacts_by_asset",
    "_signal_user_states",
    "_stock_ranking_item",
    "_signal_from_ranking",
    "_signal_efficacy",
    "_with_signal_efficacy_batch",
    "_persist_signal_evaluation",
]


@dataclass
class Timing:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, elapsed_ms: float) -> None:
        self.count += 1
        self.total_ms += elapsed_ms
        self.max_ms = max(self.max_ms, elapsed_ms)


class ProfilingConnection:
    def __init__(self, conn) -> None:
        self._conn = conn
        self.timings: dict[str, Timing] = defaultdict(Timing)

    def execute(self, sql: str, parameters: list[Any] | tuple[Any, ...] | None = None):
        started = perf_counter()
        try:
            if parameters is None:
                return self._conn.execute(sql)
            return self._conn.execute(sql, parameters)
        finally:
            self.timings[_sql_label(sql)].add((perf_counter() - started) * 1000)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


class MethodProfiler:
    def __init__(self, service: PortfolioApiService) -> None:
        self.timings: dict[str, Timing] = defaultdict(Timing)
        self._restore: list[tuple[str, Any]] = []
        for name in PROFILED_METHODS:
            original = getattr(service, name, None)
            if original is None:
                continue
            self._restore.append((name, original))
            setattr(service, name, self._wrap(name, original))

    def _wrap(self, name: str, original):
        def profiled(*args, **kwargs):
            started = perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.timings[name].add((perf_counter() - started) * 1000)

        return profiled


def main() -> None:
    args = parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    output = Path(args.output).resolve() if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))
    profiled_conn = ProfilingConnection(conn)
    service = PortfolioApiService(profiled_conn)
    profiler = MethodProfiler(service)
    filters = _filters_from_query(args.query)

    iterations = []
    for index in range(args.warmups + args.repeats):
        started = perf_counter()
        result = service.signals_summary(**filters)
        detail_id = result.items[0].signal_id if args.include_detail and result.items else None
        if detail_id:
            service.signal_detail(detail_id)
        elapsed_ms = (perf_counter() - started) * 1000
        if index >= args.warmups:
            iterations.append(
                {
                    "iteration": index - args.warmups + 1,
                    "total_ms": round(elapsed_ms, 2),
                    "items": len(result.items),
                    "total_matching": result.total,
                    "detail_profiled": detail_id,
                }
            )

    conn.close()
    report = {
        "db_path": str(db_path),
        "query": args.query,
        "warmups": args.warmups,
        "repeats": args.repeats,
        "iterations": iterations,
        "average_total_ms": round(sum(item["total_ms"] for item in iterations) / len(iterations), 2)
        if iterations
        else None,
        "methods": _timing_rows(profiler.timings),
        "sql": _timing_rows(profiled_conn.timings),
    }

    print(_summary(report))
    if output:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote JSON report: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile backend latency for /api/v1/signals.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="DuckDB file to profile.")
    parser.add_argument("--query", default="limit=25&sort=priority", help="Signals query string to replay.")
    parser.add_argument("--repeats", type=int, default=3, help="Measured repetitions.")
    parser.add_argument("--warmups", type=int, default=1, help="Warmup repetitions excluded from the report.")
    parser.add_argument("--include-detail", action="store_true", help="Also profile the first signal detail call.")
    parser.add_argument("--output", default="tmp/signals-backend-profile.json", help="Optional JSON report path.")
    return parser.parse_args()


def _filters_from_query(query: str) -> dict[str, Any]:
    values = {key: item[-1] for key, item in parse_qs(query, keep_blank_values=False).items()}
    return {
        "q": values.get("q"),
        "portfolio_id": _int_or_none(values.get("portfolio_id")),
        "owned": values.get("owned"),
        "category": values.get("category"),
        "direction": values.get("direction"),
        "status": values.get("status"),
        "min_strength": _float_or_none(values.get("min_strength")),
        "min_confidence": _float_or_none(values.get("min_confidence")),
        "min_priority": _float_or_none(values.get("min_priority")),
        "sector": values.get("sector"),
        "industry": values.get("industry"),
        "freshness": values.get("freshness"),
        "completeness": values.get("completeness"),
        "triggered_after": _date_or_none(values.get("triggered_after")),
        "triggered_before": _date_or_none(values.get("triggered_before")),
        "include_retail_sentiment": values.get(
            "include_retail_sentiment",
            "false",
        ).lower()
        == "true",
        "sort": values.get("sort", "priority"),
        "limit": int(values.get("limit", "25")),
        "offset": int(values.get("offset", "0")),
    }


def _timing_rows(timings: dict[str, Timing]) -> list[dict[str, Any]]:
    rows = []
    for label, timing in timings.items():
        rows.append(
            {
                "label": label,
                "count": timing.count,
                "total_ms": round(timing.total_ms, 2),
                "avg_ms": round(timing.total_ms / timing.count, 2) if timing.count else 0.0,
                "max_ms": round(timing.max_ms, 2),
            }
        )
    return sorted(rows, key=lambda item: item["total_ms"], reverse=True)


def _summary(report: dict[str, Any]) -> str:
    lines = [
        "Signals backend profile",
        f"  db: {report['db_path']}",
        f"  query: {report['query']}",
        f"  average: {report['average_total_ms']} ms across {report['repeats']} runs",
        "",
        "Slowest service methods:",
    ]
    lines.extend(_format_rows(report["methods"][:12]))
    lines.append("")
    lines.append("Slowest SQL statements:")
    lines.extend(_format_rows(report["sql"][:12]))
    return "\n".join(lines)


def _format_rows(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["  none"]
    return [
        f"  {row['label']}: total={row['total_ms']} ms avg={row['avg_ms']} ms count={row['count']} max={row['max_ms']} ms"
        for row in rows
    ]


def _sql_label(sql: str) -> str:
    compact = " ".join(sql.strip().split())
    return compact[:160]


def _int_or_none(value: str | None) -> int | None:
    return int(value) if value else None


def _float_or_none(value: str | None) -> float | None:
    return float(value) if value else None


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


if __name__ == "__main__":
    main()
