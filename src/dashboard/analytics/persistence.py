"""Optional persistence for latest analytics snapshots."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from .calculations import _json_dumps, _json_ready
from .engine import AnalyticsEngine
from .models import AnalyticsRefreshResult, AssetAnalyticsReport, PortfolioAnalyticsReport
from .repository import AnalyticsRepository


class AnalyticsStorageService:
    """Optional persistence for the latest analytics snapshots.

    The service is inert unless ``enabled`` is true. That lets users calculate
    analytics ad hoc without storing records, while users who want an AI-ready
    cache can opt into daily and portfolio-change refreshes.
    """

    def __init__(
        self,
        conn: Any,
        enabled: bool = False,
        benchmark_index_id: str | None = None,
        risk_free_rate: float = 0.0,
    ) -> None:
        self.conn = conn
        self.enabled = enabled
        self.benchmark_index_id = benchmark_index_id
        self.risk_free_rate = risk_free_rate
        self.repo = AnalyticsRepository(conn)
        self.engine = AnalyticsEngine(self.repo)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.ensure_schema()
        else:
            if self.repo._table_exists("analytics_storage_config"):
                self.conn.execute(
                    """
                    INSERT INTO analytics_storage_config(config_key, config_value, updated_at)
                    VALUES ('enabled', 'false', now())
                    ON CONFLICT(config_key) DO UPDATE SET
                        config_value = excluded.config_value,
                        updated_at = now()
                    """
                )
            return

        self.conn.execute(
            """
            INSERT INTO analytics_storage_config(config_key, config_value, updated_at)
            VALUES ('enabled', 'true', now())
            ON CONFLICT(config_key) DO UPDATE SET
                config_value = excluded.config_value,
                updated_at = now()
            """
        )

    def refresh_due(
        self,
        as_of_date: date | None = None,
        asset_ids: list[str] | None = None,
        portfolio_ids: list[int] | None = None,
    ) -> AnalyticsRefreshResult:
        if not self.enabled:
            return AnalyticsRefreshResult(skipped=True, reason="analytics storage disabled")

        self.ensure_schema()
        as_of_date = as_of_date or date.today()
        asset_ids = asset_ids if asset_ids is not None else self.repo.tracked_asset_ids()
        portfolio_ids = portfolio_ids if portfolio_ids is not None else self.repo.portfolio_ids()

        assets_stored = 0
        for asset_id in asset_ids:
            if self._asset_due(asset_id, as_of_date):
                report = self.engine.asset_report(
                    asset_id,
                    benchmark_index_id=self.benchmark_index_id,
                    risk_free_rate=self.risk_free_rate,
                )
                self.store_asset_report(report, as_of_date)
                assets_stored += 1

        portfolios_stored = 0
        for portfolio_id in portfolio_ids:
            signature = self.portfolio_signature(portfolio_id)
            if self._portfolio_due(portfolio_id, as_of_date, signature):
                report = self.engine.portfolio_report(
                    portfolio_id,
                    benchmark_index_id=self.benchmark_index_id,
                    risk_free_rate=self.risk_free_rate,
                )
                self.store_portfolio_report(report, as_of_date, signature)
                portfolios_stored += 1

        return AnalyticsRefreshResult(
            assets_stored=assets_stored,
            portfolios_stored=portfolios_stored,
        )

    def store_asset_report(self, report: AssetAnalyticsReport, as_of_date: date) -> None:
        payload = _json_dumps(report)
        latest_missing = sorted(
            set(
                report.dividend_discount.missing_inputs + report.discounted_cash_flow.missing_inputs
            )
        )
        self.conn.execute(
            """
            INSERT INTO asset_analytics_snapshot (
                asset_id,
                snapshot_date,
                latest_price,
                cagr,
                sharpe_ratio,
                sortino_ratio,
                beta,
                alpha_annualized,
                dividend_discount_value,
                discounted_cash_flow_value,
                implied_dividend_growth,
                implied_dcf_growth,
                payload_json,
                missing_inputs_json,
                refreshed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(asset_id, snapshot_date) DO UPDATE SET
                latest_price = excluded.latest_price,
                cagr = excluded.cagr,
                sharpe_ratio = excluded.sharpe_ratio,
                sortino_ratio = excluded.sortino_ratio,
                beta = excluded.beta,
                alpha_annualized = excluded.alpha_annualized,
                dividend_discount_value = excluded.dividend_discount_value,
                discounted_cash_flow_value = excluded.discounted_cash_flow_value,
                implied_dividend_growth = excluded.implied_dividend_growth,
                implied_dcf_growth = excluded.implied_dcf_growth,
                payload_json = excluded.payload_json,
                missing_inputs_json = excluded.missing_inputs_json,
                refreshed_at = now()
            """,
            [
                report.asset_id,
                as_of_date,
                report.latest_price,
                report.risk.cagr,
                report.risk.sharpe_ratio,
                report.risk.sortino_ratio,
                report.relative.beta if report.relative else None,
                report.relative.alpha_annualized if report.relative else None,
                report.dividend_discount.intrinsic_value_per_share,
                report.discounted_cash_flow.intrinsic_value_per_share,
                report.dividend_discount.implied_growth_rate,
                report.discounted_cash_flow.implied_growth_rate,
                payload,
                json.dumps(latest_missing),
            ],
        )
        self._upsert_refresh_state("asset", report.asset_id, as_of_date, None)

    def store_portfolio_report(
        self,
        report: PortfolioAnalyticsReport,
        as_of_date: date,
        state_signature: str | None = None,
    ) -> None:
        signature = state_signature or self.portfolio_signature(report.portfolio_id)
        self.conn.execute(
            """
            INSERT INTO portfolio_analytics_snapshot (
                portfolio_id,
                snapshot_date,
                market_value,
                cagr,
                sharpe_ratio,
                sortino_ratio,
                beta,
                alpha_annualized,
                position_count,
                state_signature,
                payload_json,
                missing_inputs_json,
                refreshed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
            ON CONFLICT(portfolio_id, snapshot_date) DO UPDATE SET
                market_value = excluded.market_value,
                cagr = excluded.cagr,
                sharpe_ratio = excluded.sharpe_ratio,
                sortino_ratio = excluded.sortino_ratio,
                beta = excluded.beta,
                alpha_annualized = excluded.alpha_annualized,
                position_count = excluded.position_count,
                state_signature = excluded.state_signature,
                payload_json = excluded.payload_json,
                missing_inputs_json = excluded.missing_inputs_json,
                refreshed_at = now()
            """,
            [
                report.portfolio_id,
                as_of_date,
                report.market_value,
                report.risk.cagr if report.risk else None,
                report.risk.sharpe_ratio if report.risk else None,
                report.risk.sortino_ratio if report.risk else None,
                report.relative.beta if report.relative else None,
                report.relative.alpha_annualized if report.relative else None,
                len(report.positions),
                signature,
                _json_dumps(report),
                json.dumps(report.missing_inputs),
            ],
        )
        self._upsert_refresh_state("portfolio", str(report.portfolio_id), as_of_date, signature)

    def portfolio_signature(self, portfolio_id: int) -> str:
        rows = self.conn.execute(
            """
            SELECT
                p.asset_id,
                p.qty,
                p.book_cost,
                p.updated_at,
                MAX(q.date) AS latest_price_date
            FROM position p
            LEFT JOIN asset_quote_daily q
              ON q.asset_id = p.asset_id
            WHERE p.portfolio_id = ?
            GROUP BY p.asset_id, p.qty, p.book_cost, p.updated_at
            ORDER BY p.asset_id
            """,
            [portfolio_id],
        ).fetchall()
        encoded = json.dumps([_json_ready(row) for row in rows], sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def ensure_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_storage_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_analytics_snapshot (
                asset_id TEXT NOT NULL,
                snapshot_date DATE NOT NULL,
                latest_price DOUBLE,
                cagr DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                beta DOUBLE,
                alpha_annualized DOUBLE,
                dividend_discount_value DOUBLE,
                discounted_cash_flow_value DOUBLE,
                implied_dividend_growth DOUBLE,
                implied_dcf_growth DOUBLE,
                payload_json TEXT NOT NULL,
                missing_inputs_json TEXT,
                refreshed_at TIMESTAMP NOT NULL DEFAULT now(),
                PRIMARY KEY(asset_id, snapshot_date)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_analytics_snapshot (
                portfolio_id BIGINT NOT NULL,
                snapshot_date DATE NOT NULL,
                market_value DOUBLE,
                cagr DOUBLE,
                sharpe_ratio DOUBLE,
                sortino_ratio DOUBLE,
                beta DOUBLE,
                alpha_annualized DOUBLE,
                position_count INTEGER NOT NULL DEFAULT 0,
                state_signature TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                missing_inputs_json TEXT,
                refreshed_at TIMESTAMP NOT NULL DEFAULT now(),
                PRIMARY KEY(portfolio_id, snapshot_date)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_refresh_state (
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                last_snapshot_date DATE,
                last_refreshed_at TIMESTAMP,
                state_signature TEXT,
                PRIMARY KEY(subject_type, subject_id)
            )
            """
        )

    def _asset_due(self, asset_id: str, as_of_date: date) -> bool:
        row = self.conn.execute(
            """
            SELECT last_snapshot_date
            FROM analytics_refresh_state
            WHERE subject_type = 'asset'
              AND subject_id = ?
            """,
            [asset_id],
        ).fetchone()
        return row is None or row[0] is None or row[0] < as_of_date

    def _portfolio_due(self, portfolio_id: int, as_of_date: date, signature: str) -> bool:
        row = self.conn.execute(
            """
            SELECT last_snapshot_date, state_signature
            FROM analytics_refresh_state
            WHERE subject_type = 'portfolio'
              AND subject_id = ?
            """,
            [str(portfolio_id)],
        ).fetchone()
        return row is None or row[0] is None or row[0] < as_of_date or row[1] != signature

    def _upsert_refresh_state(
        self,
        subject_type: str,
        subject_id: str,
        snapshot_date: date,
        state_signature: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO analytics_refresh_state (
                subject_type,
                subject_id,
                last_snapshot_date,
                last_refreshed_at,
                state_signature
            )
            VALUES (?, ?, ?, now(), ?)
            ON CONFLICT(subject_type, subject_id) DO UPDATE SET
                last_snapshot_date = excluded.last_snapshot_date,
                last_refreshed_at = now(),
                state_signature = excluded.state_signature
            """,
            [subject_type, subject_id, snapshot_date, state_signature],
        )
