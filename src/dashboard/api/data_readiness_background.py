"""Background worker that keeps portfolio valuation inputs ready."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from dashboard.analytics.calculations import allocation_class
from dashboard.analytics import AnalyticsRepository
from dashboard.api.services import CommandApiService, PortfolioApiService
from dashboard.db.db_conn import DB
from dashboard.ingestion.ticker_universe import TickerUniverseRepository

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataReadinessConfig:
    enabled: bool = True
    poll_interval_seconds: int = 300
    max_assets_per_tick: int = 50
    max_jobs_per_batch: int = 10
    max_run_batches_per_tick: int = 10
    years: int = 10
    min_price_rows: int = 3

    @classmethod
    def from_env(cls) -> "DataReadinessConfig":
        return cls(
            enabled=_truthy_env("DATA_READINESS_WORKER_ENABLED", default=False),
            poll_interval_seconds=_int_env("DATA_READINESS_POLL_INTERVAL_SECONDS", 300),
            max_assets_per_tick=_int_env("DATA_READINESS_MAX_ASSETS_PER_TICK", 50),
            max_jobs_per_batch=_int_env("DATA_READINESS_MAX_JOBS_PER_BATCH", 10),
            max_run_batches_per_tick=_int_env("DATA_READINESS_MAX_RUN_BATCHES_PER_TICK", 10),
            years=_int_env("DATA_READINESS_YEARS", 10),
            min_price_rows=_int_env("DATA_READINESS_MIN_PRICE_ROWS", 3),
        )


@dataclass(frozen=True)
class ValuationTarget:
    portfolio_id: int
    asset_id: str
    symbol: str
    valuation_asset_id: str


class DataReadinessWorker:
    def __init__(self, db_path: Path, write_lock: Lock, config: DataReadinessConfig) -> None:
        self.db_path = Path(db_path)
        self.write_lock = write_lock
        self.config = config
        self._enabled = config.enabled
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self.last_check_at: datetime | None = None
        self.last_target_count: int | None = None
        self.last_ready_count: int | None = None
        self.last_valuation_count: int | None = None
        self.last_scheduled_count: int | None = None
        self.last_completed_count: int | None = None
        self.last_pending_count: int | None = None
        self.last_missing: list[str] = []
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self._enabled:
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="data-readiness-worker")
        self._running = True

    def enable(self) -> None:
        self._enabled = True

    async def disable(self) -> None:
        self._enabled = False
        await self.stop()

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._running = False

    async def tick(self) -> dict[str, int | list[str]]:
        try:
            result = await asyncio.to_thread(self._tick_once)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Data readiness worker failed: %s", exc)
            return {
                "targets": self.last_target_count or 0,
                "ready": self.last_ready_count or 0,
                "valuations": self.last_valuation_count or 0,
                "scheduled_jobs": 0,
                "completed_jobs": 0,
                "pending_jobs": self.last_pending_count or 0,
                "missing": self.last_missing,
            }
        self.last_check_at = _now()
        self.last_error = None
        return result

    async def _run_loop(self) -> None:
        try:
            while self._stop_event is not None and not self._stop_event.is_set():
                await self.tick()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(self.config.poll_interval_seconds),
                    )
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.exception("Data readiness worker stopped unexpectedly")
        finally:
            self._running = False

    def _tick_once(self) -> dict[str, int | list[str]]:
        with self.write_lock:
            db = DB(self.db_path)
            try:
                TickerUniverseRepository(db.conn).sync_portfolio_tickers_from_positions()
                targets = _valuation_targets(db.conn)[: self.config.max_assets_per_tick]
                scheduled = _schedule_missing_inputs(db.conn, targets, self.config)
                completed = _run_batches(db.conn, self.config)
                readiness = _strict_readiness(db.conn, targets, self.config)
                valuations = _run_portfolio_valuations(db.conn, targets)
                pending = _pending_job_count(db.conn)
            finally:
                db.conn.close()

        self.last_target_count = len(targets)
        self.last_ready_count = sum(1 for item in readiness.values() if not item)
        self.last_valuation_count = valuations
        self.last_scheduled_count = scheduled
        self.last_completed_count = completed
        self.last_pending_count = pending
        self.last_missing = [
            f"{key.split(':', maxsplit=1)[1]}: {', '.join(missing)}"
            for key, missing in sorted(readiness.items())
            if missing
        ]
        return {
            "targets": self.last_target_count,
            "ready": self.last_ready_count,
            "valuations": self.last_valuation_count,
            "scheduled_jobs": self.last_scheduled_count,
            "completed_jobs": self.last_completed_count,
            "pending_jobs": self.last_pending_count,
            "missing": self.last_missing,
        }

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "running": self.running,
            "last_check_at": self.last_check_at,
            "last_target_count": self.last_target_count,
            "last_ready_count": self.last_ready_count,
            "last_valuation_count": self.last_valuation_count,
            "last_scheduled_count": self.last_scheduled_count,
            "last_completed_count": self.last_completed_count,
            "last_pending_count": self.last_pending_count,
            "last_missing": self.last_missing,
            "last_error": self.last_error,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "max_assets_per_tick": self.config.max_assets_per_tick,
            "max_jobs_per_batch": self.config.max_jobs_per_batch,
            "max_run_batches_per_tick": self.config.max_run_batches_per_tick,
            "years": self.config.years,
            "min_price_rows": self.config.min_price_rows,
        }


def _valuation_targets(conn) -> list[ValuationTarget]:
    rows = conn.execute(
        """
        SELECT DISTINCT
            pt.portfolio_id,
            a.asset_id,
            COALESCE(a.symbol, a.asset_id) AS symbol,
            a.asset_type,
            a.asset_subtype,
            a.name,
            a.description
        FROM portfolio_ticker pt
        JOIN asset a ON a.asset_id = pt.asset_id
        WHERE pt.is_active = TRUE
          AND (
                LOWER(COALESCE(a.asset_type, '')) IN ('stock', 'adr')
                OR LOWER(COALESCE(a.asset_subtype, '')) LIKE '%cdr%'
                OR LOWER(COALESCE(a.name, '')) LIKE '%cdr%'
                OR LOWER(COALESCE(a.description, '')) LIKE '%cdr%'
          )
        ORDER BY pt.portfolio_id, a.asset_id
        """
    ).fetchall()
    repo = AnalyticsRepository(conn)
    targets: list[ValuationTarget] = []
    for portfolio_id, asset_id, symbol, asset_type, asset_subtype, name, description in rows:
        text = f"{asset_id or ''} {symbol or ''} {asset_subtype or ''} {name or ''} {description or ''}".lower()
        is_cdr = "cdr" in text or "depositary receipt" in text or "depository receipt" in text
        if not is_cdr and ("etf" in text or "fund" in text):
            continue
        asset_class = allocation_class(
            asset_id=str(asset_id),
            symbol=str(symbol or asset_id),
            asset_type=asset_type,
            asset_subtype=asset_subtype,
            name=name,
        )
        if asset_class not in {"Stock", "CDR"}:
            continue
        valuation_asset_id = repo.valuation_asset_id(asset_id)
        if valuation_asset_id != asset_id:
            _ensure_underlying_asset(conn, valuation_asset_id)
        targets.append(
            ValuationTarget(
                portfolio_id=int(portfolio_id),
                asset_id=str(asset_id),
                symbol=str(symbol or asset_id),
                valuation_asset_id=valuation_asset_id,
            )
        )
    return targets


def _ensure_underlying_asset(conn, asset_id: str) -> None:
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, asset_subtype, ccy, track)
        VALUES (?, ?, 'stock', NULL, 'USD', TRUE)
        ON CONFLICT(asset_id) DO UPDATE SET
            asset_type = COALESCE(asset.asset_type, excluded.asset_type),
            symbol = COALESCE(asset.symbol, excluded.symbol),
            track = TRUE,
            updated_at = now()
        """,
        [asset_id, asset_id],
    )


def _schedule_missing_inputs(
    conn,
    targets: list[ValuationTarget],
    config: DataReadinessConfig,
) -> int:
    total = 0
    seen_assets: set[str] = set()
    for target in targets:
        asset_id = target.valuation_asset_id
        if asset_id in seen_assets:
            continue
        seen_assets.add(asset_id)
        missing = _missing_inputs(conn, asset_id, config)
        if any(item.endswith("statements") or item in {"shares_outstanding", "fundamental_metrics"} for item in missing):
            _hydrate_yfinance_summary(conn, asset_id)
            missing = _missing_inputs(conn, asset_id, config)
        if any(item.startswith("price") for item in missing) and not _has_open_job(conn, asset_id, "market", "price_daily"):
            _create_job(
                conn,
                asset_id=asset_id,
                domain="market",
                job_type="backfill",
                dataset="price_daily",
                priority=100,
                start_date=date.today() - timedelta(days=365 * config.years),
                end_date=date.today(),
            )
            total += 1
        if any(item.endswith("statements") or item in {"shares_outstanding", "fundamental_metrics"} for item in missing) and not _has_open_job(
            conn,
            asset_id,
            "corporate",
            "financial_statements",
        ):
            _create_job(
                conn,
                asset_id=asset_id,
                domain="corporate",
                job_type="backfill",
                dataset="financial_statements",
                priority=90,
                start_date=None,
                end_date=None,
            )
            total += 1
    return total


def _hydrate_yfinance_summary(conn, asset_id: str) -> bool:
    try:
        import yfinance as yf

        info = yf.Ticker(asset_id).get_info()
    except Exception as exc:
        LOGGER.info("Yfinance summary unavailable for %s: %s", asset_id, exc)
        return False
    if not isinstance(info, dict) or not info:
        return False

    shares = _first_float(
        info,
        "sharesOutstanding",
        "impliedSharesOutstanding",
        "floatShares",
    )
    market_cap = _first_float(info, "marketCap")
    beta = _first_float(info, "beta")
    if shares is not None or market_cap is not None or beta is not None:
        conn.execute(
            """
            UPDATE asset
            SET
                shares_outstanding = COALESCE(?, shares_outstanding),
                mkt_cap = COALESCE(?, mkt_cap),
                market_beta = COALESCE(?, market_beta),
                updated_at = now()
            WHERE asset_id = ?
            """,
            [shares, market_cap, beta, asset_id],
        )

    today = date.today()
    year = today.year
    quarter = ((today.month - 1) // 3) + 1
    revenue = _first_float(info, "totalRevenue", "revenue")
    gross_margin = _first_float(info, "grossMargins")
    operating_margin = _first_float(info, "operatingMargins")
    book_value = _first_float(info, "bookValue")
    profit_margin = _first_signed_float(info, "profitMargins")
    net_income = _first_signed_float(info, "netIncomeToCommon", "netIncome")
    income = {
        "revenue": revenue,
        "grossProfit": revenue * gross_margin if revenue is not None and gross_margin is not None else None,
        "operatingIncome": revenue * operating_margin if revenue is not None and operating_margin is not None else None,
        "netIncome": net_income
        if net_income is not None
        else (
            revenue * profit_margin
            if revenue is not None and profit_margin is not None
            else None
        ),
        "eps": _first_float(info, "trailingEps", "epsTrailingTwelveMonths"),
        "ebitda": _first_float(info, "ebitda"),
        "weightedAverageShsOutDil": shares,
    }
    balance = {
        "totalDebt": _first_float(info, "totalDebt") or 0.0,
        "totalStockholdersEquity": book_value * shares if book_value is not None and shares else None,
        "totalAssets": _first_float(info, "totalAssets"),
        "cashAndCashEquivalents": _first_float(info, "totalCash"),
    }
    cashflow = {
        "freeCashFlow": _first_float(info, "freeCashflow", "freeCashFlow"),
        "operatingCashFlow": _first_float(info, "operatingCashflow", "operatingCashFlow"),
    }
    wrote = False
    for statement_type, payload in (
        ("income", income),
        ("balance", balance),
        ("cashflow", cashflow),
    ):
        if not any(value is not None for value in payload.values()):
            continue
        payload = _merge_statement_payload(conn, asset_id, statement_type, year, quarter, payload)
        conn.execute(
            """
            INSERT INTO financial_statement(
                asset_id,
                statement_type,
                year,
                quarter,
                period_end_date,
                report_date,
                data_json,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'computed_from_yfinance_summary')
            ON CONFLICT(asset_id, statement_type, year, quarter) DO UPDATE SET
                period_end_date = excluded.period_end_date,
                report_date = excluded.report_date,
                data_json = excluded.data_json,
                source = excluded.source,
                ingested_at_utc = now()
            """,
            [
                asset_id,
                statement_type,
                year,
                quarter,
                today,
                today,
                json.dumps({key: value for key, value in payload.items() if value is not None}),
            ],
        )
        wrote = True
    return wrote


def _merge_statement_payload(
    conn,
    asset_id: str,
    statement_type: str,
    year: int,
    quarter: int,
    payload: dict[str, float | None],
) -> dict[str, float | None]:
    row = conn.execute(
        """
        SELECT data_json
        FROM financial_statement
        WHERE asset_id = ?
          AND statement_type = ?
          AND year = ?
          AND quarter = ?
        """,
        [asset_id, statement_type, year, quarter],
    ).fetchone()
    existing: dict[str, float | None] = {}
    if row and row[0] is not None:
        try:
            parsed = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except (TypeError, ValueError):
            parsed = {}
        if isinstance(parsed, dict):
            existing = parsed
    return {
        **existing,
        **{key: value for key, value in payload.items() if value is not None},
    }


def _first_float(values: dict, *keys: str) -> float | None:
    for key in keys:
        value = values.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _first_signed_float(values: dict, *keys: str) -> float | None:
    for key in keys:
        value = values.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _run_batches(conn, config: DataReadinessConfig) -> int:
    service = CommandApiService(conn)
    completed = 0
    for _ in range(config.max_run_batches_per_tick):
        count = service.run_ingestion_jobs(domain="all", max_jobs=config.max_jobs_per_batch)
        completed += count
        if count < config.max_jobs_per_batch:
            break
    return completed


def _strict_readiness(
    conn,
    targets: list[ValuationTarget],
    config: DataReadinessConfig,
) -> dict[str, list[str]]:
    readiness: dict[str, list[str]] = {}
    for target in targets:
        readiness[f"{target.portfolio_id}:{target.asset_id}"] = _missing_inputs(conn, target.valuation_asset_id, config)
    return readiness


def _missing_inputs(conn, asset_id: str, config: DataReadinessConfig) -> list[str]:
    missing: list[str] = []
    price_row = conn.execute(
        """
        SELECT COUNT(*)
        FROM asset_quote_daily
        WHERE asset_id = ?
          AND COALESCE(adj_close, close) IS NOT NULL
        """,
        [asset_id],
    ).fetchone()
    if int(price_row[0] or 0) < config.min_price_rows:
        missing.append("price_history")

    shares_row = conn.execute(
        """
        SELECT shares_outstanding
        FROM asset
        WHERE asset_id = ?
        """,
        [asset_id],
    ).fetchone()
    shares = shares_row[0] if shares_row else None
    if shares is None or shares <= 0:
        shares = _statement_shares_outstanding(conn, asset_id)
    if shares is None or shares <= 0:
        missing.append("shares_outstanding")

    for statement_type in ("income", "balance", "cashflow"):
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM financial_statement
            WHERE asset_id = ?
              AND statement_type = ?
            """,
            [asset_id, statement_type],
        ).fetchone()
        if int(row[0] or 0) <= 0:
            missing.append(f"{statement_type}_statements")
    if "income_statements" not in missing and "balance_statements" not in missing:
        metric_missing = _required_metric_fields_missing(conn, asset_id)
        if metric_missing:
            missing.append("fundamental_metrics")
    return missing


def _required_metric_fields_missing(conn, asset_id: str) -> list[str]:
    income = _latest_statement_json(conn, asset_id, "income")
    balance = _latest_statement_json(conn, asset_id, "balance")
    cashflow = _latest_statement_json(conn, asset_id, "cashflow")
    revenue = _json_number(income, "revenue", "totalRevenue")
    gross_profit = _json_number(income, "grossProfit", "gross_profit")
    operating_income = _json_number(income, "operatingIncome", "operating_income")
    net_income = _json_number(income, "netIncome", "net_income", "netIncomeToCommon")
    total_debt = _json_number(balance, "totalDebt", "debt")
    equity = _json_number(balance, "totalStockholdersEquity", "totalEquity")
    cash = _json_number(balance, "cashAndCashEquivalents", "cashAndShortTermInvestments", "cash")
    free_cash_flow = _json_number(cashflow, "freeCashFlow", "free_cash_flow")
    missing = []
    if revenue is None or revenue <= 0:
        missing.append("revenue")
    if gross_profit is None:
        missing.append("grossProfit")
    if operating_income is None:
        missing.append("operatingIncome")
    if net_income is None:
        missing.append("netIncome")
    if total_debt is None:
        missing.append("totalDebt")
    if equity is None:
        missing.append("totalStockholdersEquity")
    if cash is None:
        missing.append("cashAndCashEquivalents")
    if free_cash_flow is None:
        missing.append("freeCashFlow")
    return missing


def _latest_statement_json(conn, asset_id: str, statement_type: str) -> dict:
    row = conn.execute(
        """
        SELECT data_json
        FROM financial_statement
        WHERE asset_id = ?
          AND statement_type = ?
        ORDER BY period_end_date DESC NULLS LAST, year DESC, quarter DESC
        LIMIT 1
        """,
        [asset_id, statement_type],
    ).fetchone()
    if row is None or row[0] is None:
        return {}
    try:
        parsed = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_number(data: dict, *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _statement_shares_outstanding(conn, asset_id: str) -> float | None:
    rows = conn.execute(
        """
        SELECT data_json
        FROM financial_statement
        WHERE asset_id = ?
          AND statement_type = 'income'
        ORDER BY year DESC, quarter DESC
        LIMIT 8
        """,
        [asset_id],
    ).fetchall()
    for row in rows:
        try:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        except (TypeError, ValueError):
            data = {}
        for key in (
            "weightedAverageShsOutDil",
            "weightedAverageShsOut",
            "weighted_average_shares_diluted",
            "weighted_average_shares",
            "sharesOutstanding",
            "shares_outstanding",
        ):
            value = data.get(key)
            if value in (None, ""):
                continue
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
    return None


def _run_portfolio_valuations(conn, targets: list[ValuationTarget]) -> int:
    if not targets:
        return 0
    service = PortfolioApiService(conn)
    portfolios = sorted({target.portfolio_id for target in targets})
    calculated = 0
    for portfolio_id in portfolios:
        fundamentals = service.fundamentals(portfolio_id)
        covered = {
            item.asset_id
            for item in fundamentals.holdings
            if item.expected_cagr is not None
            and item.pe_ratio is not None
            and item.price_to_free_cash_flow is not None
        }
        calculated += sum(1 for target in targets if target.portfolio_id == portfolio_id and target.asset_id in covered)
    return calculated


def _has_open_job(conn, asset_id: str, domain: str, dataset: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM ingestion_job
        WHERE asset_id = ?
          AND domain = ?
          AND dataset = ?
          AND status IN ('pending', 'running')
        """,
        [asset_id, domain, dataset],
    ).fetchone()
    return bool(row and row[0])


def _create_job(
    conn,
    *,
    asset_id: str,
    domain: str,
    job_type: str,
    dataset: str,
    priority: int,
    start_date: date | None,
    end_date: date | None,
) -> None:
    job_id = int(
        conn.execute("SELECT nextval('seq_ingestion_job_id')").fetchone()[0]
    )
    conn.execute(
        """
        INSERT INTO ingestion_job(
            job_id,
            asset_id,
            domain,
            job_type,
            dataset,
            status,
            priority,
            requested_start_date,
            requested_end_date,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, now(), now())
        """,
        [job_id, asset_id, domain, job_type, dataset, priority, start_date, end_date],
    )


def _pending_job_count(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM ingestion_job
        WHERE status IN ('pending', 'running')
        """
    ).fetchone()
    return int(row[0] or 0)


def _truthy_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return max(int(value), 1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ
