from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf

from dashboard.db.db_conn import DB, init_db
from dashboard.ingestion.indices.benchmark_financial_metrics import (
    BenchmarkFinancialMetricService,
    SECTOR_BENCHMARK_PEERS,
)
from dashboard.ingestion.indices.index_service_factory import create_index_ingestion_service
from dashboard.ingestion.price_history.db import queries as price_queries
from dashboard.ingestion.price_history.provider_yahoo import YahooPriceProvider


DB_PATH = Path("data/persistent_db.db")
SOURCE = "computed_from_yfinance_summary"
SOURCE_TYPE = "sector_constituent_provider_median"
PRICE_LOOKBACK_DAYS = 45


METRIC_KEYS = {
    "eps_median": ("trailingEps", "epsTrailingTwelveMonths"),
    "non_gaap_eps_median": ("normalizedEPS", "nonGaapEPS", "epsNonGaap"),
    "forward_eps_median": ("forwardEps",),
    "pe_median": ("trailingPE",),
    "forward_pe_median": ("forwardPE",),
    "peg_median": ("pegRatio", "trailingPegRatio"),
    "price_to_sales_median": ("priceToSalesTrailing12Months",),
    "ev_to_ebitda_median": ("enterpriseToEbitda",),
    "gross_margin_median": ("grossMargins",),
    "operating_margin_median": ("operatingMargins",),
    "net_margin_median": ("profitMargins",),
    "revenue_growth_median": ("revenueGrowth",),
    "eps_growth_median": ("earningsGrowth",),
}


def main() -> None:
    db = DB(str(DB_PATH))
    init_db(db)
    create_index_ingestion_service(db.conn).seed_sector_industry_universe()

    service = BenchmarkFinancialMetricService(db.conn)
    price_provider = YahooPriceProvider()
    today = date.today()
    total = 0

    for index_id in _sector_index_ids(db.conn):
        sector_label = SECTOR_BENCHMARK_PEERS.get(index_id, (None,))[0]
        constituents = _latest_constituents(db.conn, index_id)
        if not constituents:
            print((index_id, "no constituents"))
            continue

        metric_rows: list[dict[str, float | None]] = []
        for constituent in constituents:
            symbol = str(constituent["symbol"]).upper()
            _upsert_asset_from_constituent(db.conn, constituent, sector_label)
            _refresh_recent_prices(db.conn, price_provider, symbol, today)
            summary = _fetch_yfinance_summary(symbol)
            if _has_any_metric(summary):
                metric_rows.append(summary)

        metrics = {
            metric_name: _median([row.get(metric_name) for row in metric_rows])
            for metric_name in METRIC_KEYS
        }
        service.store_sector_provider_summary(
            index_id=index_id,
            metric_date=today,
            peer_count=len(constituents),
            covered_peer_count=len(metric_rows),
            metrics=metrics,
            source=SOURCE,
            source_type=SOURCE_TYPE,
            notes=(
                "Median from latest sector ETF proxy constituents using yfinance summary fields. "
                "Non-GAAP EPS remains null when the provider does not expose a non-GAAP field."
            ),
        )
        total += 1
        print((index_id, len(constituents), len(metric_rows), metrics["pe_median"], metrics["peg_median"]))

    print(f"hydrated sector benchmark financial metric snapshots: {total}")


def _sector_index_ids(conn) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE index_category = 'sector'
              AND is_active
            ORDER BY index_id;
            """
        ).fetchall()
    ]


def _latest_constituents(conn, index_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.constituent_symbol,
            c.constituent_name,
            c.exchange_code,
            c.country_code,
            c.currency,
            c.industry,
            c.market_cap,
            c.weight_pct
        FROM benchmark_index_constituent c
        WHERE c.index_id = ?
          AND c.snapshot_date = (
              SELECT MAX(snapshot_date)
              FROM benchmark_index_constituent
              WHERE index_id = c.index_id
          )
        ORDER BY c.weight_pct DESC NULLS LAST, c.constituent_symbol
        LIMIT 50;
        """,
        [index_id],
    ).fetchall()
    return [
        {
            "symbol": row[0],
            "name": row[1],
            "exchange_code": row[2],
            "country_code": row[3],
            "currency": row[4],
            "industry": row[5],
            "market_cap": row[6],
            "weight_pct": row[7],
        }
        for row in rows
    ]


def _upsert_asset_from_constituent(conn, constituent: dict[str, Any], sector: str | None) -> None:
    symbol = str(constituent["symbol"]).upper()
    conn.execute(
        """
        INSERT INTO asset (
            asset_id,
            symbol,
            exchange_code,
            asset_type,
            ccy,
            name,
            sector,
            industry,
            country,
            mkt_cap,
            track
        )
        VALUES (?, ?, ?, 'stock', ?, ?, ?, ?, ?, ?, TRUE)
        ON CONFLICT (asset_id) DO UPDATE SET
            symbol = COALESCE(asset.symbol, excluded.symbol),
            exchange_code = COALESCE(asset.exchange_code, excluded.exchange_code),
            asset_type = COALESCE(asset.asset_type, excluded.asset_type),
            ccy = COALESCE(asset.ccy, excluded.ccy),
            name = COALESCE(asset.name, excluded.name),
            sector = COALESCE(asset.sector, excluded.sector),
            industry = COALESCE(asset.industry, excluded.industry),
            country = COALESCE(asset.country, excluded.country),
            mkt_cap = COALESCE(asset.mkt_cap, excluded.mkt_cap),
            updated_at = now();
        """,
        [
            symbol,
            symbol,
            constituent.get("exchange_code"),
            constituent.get("currency") or "USD",
            constituent.get("name"),
            sector,
            constituent.get("industry"),
            constituent.get("country_code"),
            constituent.get("market_cap"),
        ],
    )


def _refresh_recent_prices(conn, provider: YahooPriceProvider, symbol: str, today: date) -> None:
    existing = conn.execute(
        "SELECT MAX(date) FROM asset_quote_daily WHERE asset_id = ?",
        [symbol],
    ).fetchone()
    if existing and existing[0] and existing[0] >= today - timedelta(days=7):
        return
    rows = provider.fetch_price_daily(symbol, today - timedelta(days=PRICE_LOOKBACK_DAYS), today)
    for row in rows:
        conn.execute(
            price_queries.UPSERT_PRICE_DAILY,
            [
                row.asset_id,
                row.price_date,
                row.open_price,
                row.high_price,
                row.low_price,
                row.close_price,
                row.adj_close_price,
                row.volume,
                row.source,
            ],
        )


def _fetch_yfinance_summary(symbol: str) -> dict[str, float | None]:
    try:
        info = yf.Ticker(symbol).get_info()
    except Exception as exc:
        print((symbol, "summary_error", str(exc)[:160]))
        return {metric_name: None for metric_name in METRIC_KEYS}

    return {
        metric_name: _first_number(info, *provider_keys)
        for metric_name, provider_keys in METRIC_KEYS.items()
    }


def _has_any_metric(metrics: dict[str, float | None]) -> bool:
    return any(value is not None for value in metrics.values())


def _first_number(values: dict[str, Any], *keys: str) -> float | None:
    lower_values = {str(key).lower(): value for key, value in values.items()}
    for key in keys:
        value = values.get(key)
        if value is None:
            value = lower_values.get(key.lower())
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _median(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return float(__import__("statistics").median(present)) if present else None


if __name__ == "__main__":
    main()
