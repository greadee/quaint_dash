"""Operational controls for the normalized financial news pipeline."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dashboard.db.db_conn import DB, init_db
from dashboard.news.api_service import NewsApiService
from dashboard.news.ingestion import NewsIngestionService
from dashboard.news.providers.fmp_provider import FmpNewsProvider
from dashboard.news.providers.mock_provider import MockNewsProvider


def _provider(provider_code: str):
    if provider_code in {"all", "mock_news"}:
        return MockNewsProvider()
    if provider_code == "fmp_news":
        return FmpNewsProvider()
    raise ValueError(
        f"Unsupported news provider '{provider_code}'. "
        "Supported providers: mock_news, fmp_news."
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _result_dict(result) -> dict[str, Any]:
    return {
        "provider_code": result.provider_code,
        "status": result.status,
        "articles_received": result.articles_received,
        "articles_inserted": result.articles_inserted,
        "articles_updated": result.articles_updated,
        "articles_rejected": result.articles_rejected,
        "asset_links_written": result.asset_links_written,
        "categories_written": result.categories_written,
        "clusters_written": result.clusters_written,
        "error_message": result.error_message,
    }


def refresh(args: argparse.Namespace) -> dict[str, Any]:
    db = DB(args.db)
    init_db(db)
    provider = _provider(args.provider)
    service = NewsIngestionService(db.conn)
    result = (
        service.ingest_subscribed(provider, limit=args.limit)
        if args.subscribed
        else service.ingest_latest(provider, limit=args.limit)
    )
    return {"operation": "news-refresh", "result": _result_dict(result)}


def backfill(args: argparse.Namespace) -> dict[str, Any]:
    db = DB(args.db)
    init_db(db)
    provider = _provider(args.provider)
    since = datetime.now(UTC) - timedelta(days=args.days)
    service = NewsIngestionService(db.conn)
    result = (
        service.ingest_subscribed(provider, since=since, limit=args.limit)
        if args.subscribed
        else service.ingest_latest(provider, since=since, limit=args.limit)
    )
    return {
        "operation": "news-backfill-run",
        "provider": provider.provider_code,
        "since": since.isoformat(),
        "historical_depth_days": args.days,
        "result": _result_dict(result),
    }


def health(args: argparse.Namespace) -> dict[str, Any]:
    db = DB(args.db)
    init_db(db)
    items = [
        item.model_dump()
        for item in NewsApiService(db.conn).provider_health(stale_after_minutes=args.stale_after_minutes)
    ]
    return {"operation": "news-health", "items": items}


def earnings(args: argparse.Namespace) -> dict[str, Any]:
    db = DB(args.db)
    init_db(db)
    result = NewsIngestionService(db.conn).ingest_earnings_events(
        lookback_days=args.lookback_days,
        lookahead_days=args.lookahead_days,
        limit=args.limit,
    )
    return {"operation": "news-earnings-sync", "result": _result_dict(result)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run financial news ingestion and diagnostics.")
    parser.add_argument("--db", default=str(Path("data/persistent_db.db")), help="DuckDB path.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    refresh_parser = subparsers.add_parser("refresh", help="Fetch latest articles for a provider.")
    refresh_parser.add_argument("provider", choices=["all", "mock_news", "fmp_news"])
    refresh_parser.add_argument("--limit", type=int, default=100)
    refresh_parser.add_argument("--subscribed", action="store_true")
    refresh_parser.set_defaults(func=refresh)

    backfill_parser = subparsers.add_parser("backfill-run", help="Run an idempotent historical fetch where supported.")
    backfill_parser.add_argument("provider", choices=["all", "mock_news", "fmp_news"])
    backfill_parser.add_argument("--days", type=int, default=7)
    backfill_parser.add_argument("--limit", type=int, default=500)
    backfill_parser.add_argument("--subscribed", action="store_true")
    backfill_parser.set_defaults(func=backfill)

    earnings_parser = subparsers.add_parser("earnings-sync", help="Normalize stored corporate-calendar earnings into news records.")
    earnings_parser.add_argument("--lookback-days", type=int, default=14)
    earnings_parser.add_argument("--lookahead-days", type=int, default=60)
    earnings_parser.add_argument("--limit", type=int, default=200)
    earnings_parser.set_defaults(func=earnings)

    health_parser = subparsers.add_parser("health", help="Print provider ingestion health.")
    health_parser.add_argument("--stale-after-minutes", type=int, default=60)
    health_parser.set_defaults(func=health)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = args.func(args)
    print(json.dumps(payload, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
