"""Audit held tickers for comparison/fundamental metric hydration.

This tool intentionally reads through the API service layer so the report
matches what Compare receives. Use --schedule-missing to enqueue the existing
ingestion pipelines for incomplete company-level assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dashboard.api.services import CommandApiService, ComparisonApiService, PortfolioApiService
from dashboard.analytics.calculations import allocation_class
from dashboard.db.db_conn import DB, init_db


@dataclass(frozen=True)
class HydrationAuditRow:
    input_ticker: str
    asset_id: str
    canonical_ticker: str
    underlying_security_ticker: str | None
    exchange: str | None
    currency: str
    security_type: str | None
    provider: str
    latest_successful_ingestion_time: str | None
    expected_metrics: list[str]
    present_metrics: list[str]
    missing_metrics: list[str]
    invalid_metrics: list[str]
    stale_metrics: list[str]
    ui_locations_affected: list[str]
    resolution_status: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="data/persistent_db.db")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--schedule-missing", action="store_true")
    parser.add_argument("--run-batches", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    db = DB(args.db_path)
    init_db(db)
    comparison = ComparisonApiService(db.conn)
    portfolio = PortfolioApiService(db.conn)
    command = CommandApiService(db.conn)

    rows: list[HydrationAuditRow] = []
    scheduled = 0
    for position in portfolio.list_positions(None):
        profile = comparison.asset_profile(position.asset_id)
        operating_company = _is_operating_company(position, profile)
        expected = list(comparison.REQUIRED_OPERATING_COMPANY_METRICS) if operating_company else []
        present = [
            key
            for key in expected
            if _profile_metric(profile, key) is not None
        ]
        missing = list(profile.missing_fundamental_metrics) if operating_company else []
        stale = (
            _stale_metric_keys(db.conn, profile.fundamental_asset_id or profile.asset_id)
            if operating_company
            else []
        )
        invalid = _invalid_metric_keys(profile)
        affected = []
        if missing or invalid or stale:
            affected = ["Ticker View -> Fundamentals", "Compare"]
        row = HydrationAuditRow(
            input_ticker=position.symbol,
            asset_id=position.asset_id,
            canonical_ticker=profile.symbol,
            underlying_security_ticker=profile.fundamental_asset_id,
            exchange=profile.exchange_code,
            currency=profile.currency,
            security_type=profile.asset_type,
            provider=_latest_provider(db.conn, profile.fundamental_asset_id or profile.asset_id),
            latest_successful_ingestion_time=_latest_success(db.conn, profile.fundamental_asset_id or profile.asset_id),
            expected_metrics=expected,
            present_metrics=present,
            missing_metrics=missing,
            invalid_metrics=invalid,
            stale_metrics=stale,
            ui_locations_affected=affected,
            resolution_status=_resolution_status(missing, invalid, stale, profile.fundamental_status),
        )
        rows.append(row)
        if args.schedule_missing and row.resolution_status != "complete":
            scheduled += command.schedule_ingestion_jobs(
                pipeline="all",
                asset_id=profile.fundamental_asset_id or profile.asset_id,
                max_assets=1,
                years=10,
            )

    completed = 0
    for _ in range(max(args.run_batches, 0)):
        count = command.run_ingestion_jobs(domain="all", max_jobs=args.batch_size)
        completed += count
        if count < args.batch_size:
            break

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(Path(args.db_path)),
        "held_ticker_count": len(rows),
        "complete_count": sum(1 for row in rows if row.resolution_status == "complete"),
        "scheduled_jobs": scheduled,
        "completed_jobs": completed,
        "items": [asdict(row) for row in rows],
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=_json_default))
    else:
        for row in rows:
            missing = ", ".join(row.missing_metrics) or "none"
            print(f"{row.input_ticker}: {row.resolution_status}; missing={missing}")
        print(
            f"{payload['complete_count']}/{payload['held_ticker_count']} held ticker(s) complete; "
            f"scheduled={scheduled}; completed={completed}"
        )
    return 0 if payload["complete_count"] == payload["held_ticker_count"] else 1


def _profile_metric(profile, key: str) -> Any:
    if key == "market_beta":
        return profile.market_beta
    return getattr(profile.fundamentals, key, None)


def _is_operating_company(position, profile) -> bool:
    allocation = allocation_class(
        asset_id=position.asset_id,
        symbol=position.symbol,
        name=getattr(profile, "name", None),
        asset_type=getattr(profile, "asset_type", None),
        asset_subtype=None,
        sector=getattr(profile, "sector", None),
        industry=getattr(profile, "industry", None),
    )
    return allocation in {"Stock", "CDR"}


def _invalid_metric_keys(profile) -> list[str]:
    invalid: list[str] = []
    for key in ("gross_margin", "operating_margin", "net_margin", "free_cash_flow_yield", "roic"):
        value = getattr(profile.fundamentals, key, None)
        if value is not None and not -10 <= value <= 10:
            invalid.append(key)
    return invalid


def _stale_metric_keys(conn, asset_id: str) -> list[str]:
    row = conn.execute(
        """
        SELECT MAX(period_end_date)
        FROM financial_statement
        WHERE asset_id = ?
        """,
        [asset_id],
    ).fetchone()
    latest = row[0] if row else None
    if latest is None:
        return ["financial_statement_period"]
    if isinstance(latest, datetime):
        latest = latest.date()
    if isinstance(latest, date) and (date.today() - latest).days > 550:
        return ["financial_statement_period"]
    return []


def _latest_provider(conn, asset_id: str) -> str:
    row = conn.execute(
        """
        SELECT source
        FROM financial_statement
        WHERE asset_id = ?
        ORDER BY ingested_at_utc DESC
        LIMIT 1
        """,
        [asset_id],
    ).fetchone()
    return str(row[0]) if row and row[0] else "unknown"


def _latest_success(conn, asset_id: str) -> str | None:
    statement = conn.execute(
        """
        SELECT MAX(ingested_at_utc)
        FROM financial_statement
        WHERE asset_id = ?
        """,
        [asset_id],
    ).fetchone()
    if statement and statement[0] is not None:
        return str(statement[0])
    state = conn.execute(
        """
        SELECT MAX(last_succeeded_at)
        FROM fundamental_sync_state
        WHERE asset_id = ?
        """,
        [asset_id],
    ).fetchone()
    return str(state[0]) if state and state[0] is not None else None


def _resolution_status(
    missing: list[str],
    invalid: list[str],
    stale: list[str],
    fallback: str,
) -> str:
    if invalid:
        return "failed"
    if missing:
        return "partial"
    if stale:
        return "stale"
    return "complete" if fallback == "complete" else fallback


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
