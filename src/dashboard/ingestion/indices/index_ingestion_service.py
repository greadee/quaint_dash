from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from dashboard.ingestion.indices import index_queries as iq
from dashboard.ingestion.indices.benchmark_index_universe import ALL_BENCHMARK_INDICES
from dashboard.ingestion.indices.core_index_universe import CORE_INDICES
from dashboard.ingestion.indices.index_models import IndexDailyBar, IndexSymbol
from dashboard.ingestion.indices.index_provider import IndexProvider
from dashboard.ingestion.indices.sector_industry_index_universe import NON_CORE_BENCHMARK_INDICES


class BenchmarkIndexIngestionService:
    def __init__(self, conn: Any, provider_registry: dict[str, IndexProvider]):
        self.conn = conn
        self.provider_registry = provider_registry

    def seed_core_universe(self) -> int:
        return self._seed_universe(CORE_INDICES)

    def seed_sector_industry_universe(self) -> int:
        return self._seed_universe(NON_CORE_BENCHMARK_INDICES)

    def seed_all_universes(self) -> int:
        return self._seed_universe(ALL_BENCHMARK_INDICES)

    def ingest_daily_prices(
        self,
        index_id: str,
        start_date: date,
        end_date: date,
    ) -> int:
        try:
            symbols = self._get_symbols_for_purpose(
                index_id=index_id,
                exact_purpose="price_daily",
                proxy_purpose="proxy_price",
            )

            bars = self._fetch_with_fallback(
                symbols=symbols,
                fetch_method_name="get_daily_prices",
                start_date=start_date,
                end_date=end_date,
            )

            if not bars:
                raise ValueError(f"No daily price bars returned for {index_id}")

            inserted = self._upsert_daily_bars(index_id, bars)
            latest_date = max(bar.price_date for bar in bars)

            self._mark_sync_success(index_id, "daily_price", latest_date)
            return inserted

        except Exception as exc:
            self._mark_sync_failure(index_id, "daily_price", exc)
            raise

    def ingest_intraday_prices(
        self,
        index_id: str,
        interval: str = "5min",
    ) -> int:
        try:
            symbols = self._get_symbols_for_purpose(
                index_id=index_id,
                exact_purpose="price_intraday",
                proxy_purpose="proxy_price",
            )

            bars = self._fetch_with_fallback(
                symbols=symbols,
                fetch_method_name="get_intraday_prices",
                interval=interval,
            )

            if not bars:
                raise ValueError(f"No intraday price bars returned for {index_id}")

            for bar in bars:
                self.conn.execute(
                    iq.UPSERT_INTRADAY_PRICE,
                    [
                        bar.index_id,
                        bar.interval,
                        bar.bar_start_utc,
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        bar.source,
                        bar.source_symbol,
                        bar.is_proxy,
                    ],
                )

            latest_date = max(bar.bar_start_utc.date() for bar in bars)
            self._mark_sync_success(index_id, "intraday_price", latest_date)
            return len(bars)

        except Exception as exc:
            self._mark_sync_failure(index_id, "intraday_price", exc)
            raise

    def ingest_composition(
        self,
        index_id: str,
        snapshot_date: date,
    ) -> int:
        try:
            symbols = self._get_symbols_for_purpose(
                index_id=index_id,
                exact_purpose="constituents",
                proxy_purpose="proxy_holdings",
            )

            selected_symbol: IndexSymbol | None = None
            constituents = []

            for symbol in symbols:
                provider = self.provider_registry.get(symbol.provider)
                if provider is None:
                    continue

                rows = provider.get_constituents(
                    index_id=symbol.index_id,
                    provider_symbol=symbol.provider_symbol,
                    is_proxy=symbol.is_proxy,
                )

                if rows:
                    selected_symbol = symbol
                    constituents = rows
                    break

            if selected_symbol is None or not constituents:
                raise ValueError(f"No composition data returned for {index_id}")

            source = constituents[0].source
            total_weight = self._sum_known_weights([c.weight_pct for c in constituents])

            source_type = "etf_proxy" if selected_symbol.is_proxy else "provider_api"
            data_quality = self._composition_quality(
                is_proxy=selected_symbol.is_proxy,
                total_weight_pct=total_weight,
            )

            self.conn.execute(
                iq.UPSERT_COMPOSITION_SNAPSHOT,
                [
                    index_id,
                    snapshot_date,
                    source,
                    selected_symbol.provider_symbol,
                    source_type,
                    selected_symbol.is_proxy,
                    len(constituents),
                    total_weight,
                    data_quality,
                    None,
                ],
            )

            self.conn.execute(
                iq.DELETE_CONSTITUENTS_FOR_SNAPSHOT_SOURCE,
                [index_id, snapshot_date, source],
            )

            for constituent in constituents:
                self.conn.execute(
                    iq.INSERT_CONSTITUENT,
                    [
                        constituent.index_id,
                        snapshot_date,
                        source,
                        constituent.constituent_symbol,
                        constituent.constituent_name,
                        constituent.exchange_code,
                        constituent.country_code,
                        constituent.currency,
                        constituent.sector,
                        constituent.industry,
                        constituent.weight_pct,
                        constituent.market_cap,
                        constituent.is_proxy,
                    ],
                )

            self._refresh_exposure_snapshots(
                index_id=index_id,
                snapshot_date=snapshot_date,
                source=source,
                source_type=source_type,
                is_proxy=selected_symbol.is_proxy,
                constituents=constituents,
            )

            self._mark_sync_success(index_id, "composition", snapshot_date)
            return len(constituents)

        except Exception as exc:
            self._mark_sync_failure(index_id, "composition", exc)
            raise

    def compute_daily_metrics(self, index_id: str) -> int:
        try:
            rows = self.conn.execute(iq.GET_DAILY_CLOSES, [index_id]).fetchall()

            if len(rows) < 2:
                return 0

            dates = [row[0] for row in rows]
            closes = [float(row[1]) for row in rows]

            inserted = 0

            for i, metric_date in enumerate(dates):
                if i == 0:
                    continue

                close = closes[i]

                return_1d = self._simple_return(closes, i, 1)
                return_5d = self._simple_return(closes, i, 5)
                return_21d = self._simple_return(closes, i, 21)
                return_63d = self._simple_return(closes, i, 63)
                return_126d = self._simple_return(closes, i, 126)
                return_252d = self._simple_return(closes, i, 252)
                return_ytd = self._ytd_return(dates, closes, i)

                vol_21 = self._annualized_volatility(closes, i, 21)
                vol_63 = self._annualized_volatility(closes, i, 63)
                vol_252 = self._annualized_volatility(closes, i, 252)

                sma_50 = self._average(closes, i, 50)
                sma_200 = self._average(closes, i, 200)

                window_252 = closes[max(0, i - 251) : i + 1]
                high_52w = max(window_252) if window_252 else None
                low_52w = min(window_252) if window_252 else None

                drawdown = None
                if high_52w and high_52w > 0:
                    drawdown = (close / high_52w) - 1

                self.conn.execute(
                    iq.UPSERT_DAILY_METRIC,
                    [
                        index_id,
                        metric_date,
                        return_1d,
                        return_5d,
                        return_21d,
                        return_63d,
                        return_126d,
                        return_252d,
                        return_ytd,
                        vol_21,
                        vol_63,
                        vol_252,
                        sma_50,
                        sma_200,
                        high_52w,
                        low_52w,
                        drawdown,
                    ],
                )
                inserted += 1

            self._mark_sync_success(index_id, "metrics", dates[-1])
            return inserted

        except Exception as exc:
            self._mark_sync_failure(index_id, "metrics", exc)
            raise

    def compute_relative_metrics(
        self,
        index_id: str,
        comparison_index_id: str = "SP500",
    ) -> int:
        rows = self.conn.execute(
            """
            SELECT
                a.price_date,
                a.close,
                b.close
            FROM benchmark_index_daily_price a
            JOIN benchmark_index_daily_price b
              ON a.price_date = b.price_date
            WHERE a.index_id = ?
              AND b.index_id = ?
            ORDER BY a.price_date;
            """,
            [index_id, comparison_index_id],
        ).fetchall()

        if len(rows) < 253:
            return 0

        dates = [row[0] for row in rows]
        index_closes = [float(row[1]) for row in rows]
        comparison_closes = [float(row[2]) for row in rows]

        index_returns = self._log_returns(index_closes)
        comparison_returns = self._log_returns(comparison_closes)

        inserted = 0

        for i in range(252, len(dates)):
            index_window = index_returns[i - 252 : i]
            comparison_window = comparison_returns[i - 252 : i]

            correlation = self._correlation(index_window, comparison_window)
            beta = self._beta(index_window, comparison_window)

            index_252_return = (index_closes[i] / index_closes[i - 252]) - 1
            comparison_252_return = (comparison_closes[i] / comparison_closes[i - 252]) - 1
            excess_return = index_252_return - comparison_252_return

            self.conn.execute(
                iq.UPSERT_RELATIVE_METRIC,
                [
                    index_id,
                    comparison_index_id,
                    dates[i],
                    correlation,
                    beta,
                    excess_return,
                ],
            )

            inserted += 1

        return inserted

    def ingest_core_daily_prices(self, start_date: date, end_date: date) -> int:
        return self.ingest_daily_prices_for_category("core_geo", start_date, end_date)

    def ingest_core_intraday_prices(self, interval: str = "5min") -> int:
        return self.ingest_intraday_prices_for_category("core_geo", interval)

    def compute_core_metrics(self) -> int:
        return self.compute_metrics_for_category("core_geo")

    def ingest_non_core_daily_prices(self, start_date: date, end_date: date) -> int:
        count = 0
        for category in ("sector", "industry", "theme"):
            count += self.ingest_daily_prices_for_category(category, start_date, end_date)
        return count

    def ingest_non_core_intraday_prices(self, interval: str = "5min") -> int:
        count = 0
        for category in ("sector", "industry", "theme"):
            count += self.ingest_intraday_prices_for_category(category, interval)
        return count

    def compute_non_core_metrics(self) -> int:
        count = 0
        for category in ("sector", "industry", "theme"):
            count += self.compute_metrics_for_category(category)
        return count

    def ingest_daily_prices_for_category(
        self,
        index_category: str,
        start_date: date,
        end_date: date,
    ) -> int:
        count = 0
        for index_id in self._get_index_ids_by_category(index_category):
            count += self.ingest_daily_prices(index_id, start_date, end_date)
        return count

    def ingest_intraday_prices_for_category(
        self,
        index_category: str,
        interval: str = "5min",
    ) -> int:
        count = 0
        for index_id in self._get_index_ids_by_category(index_category):
            count += self.ingest_intraday_prices(index_id, interval)
        return count

    def compute_metrics_for_category(self, index_category: str) -> int:
        count = 0
        for index_id in self._get_index_ids_by_category(index_category):
            count += self.compute_daily_metrics(index_id)
        return count

    def ingest_composition_for_category(
        self,
        index_category: str,
        snapshot_date: date,
        continue_on_error: bool = True,
    ) -> int:
        count = 0

        for index_id in self._get_index_ids_by_category(index_category):
            try:
                count += self.ingest_composition(index_id, snapshot_date)
            except ValueError:
                if not continue_on_error:
                    raise

        return count

    def ingest_non_core_composition(
        self,
        snapshot_date: date,
        continue_on_error: bool = True,
    ) -> int:
        count = 0

        for category in ("sector", "industry", "theme"):
            count += self.ingest_composition_for_category(
                index_category=category,
                snapshot_date=snapshot_date,
                continue_on_error=continue_on_error,
            )

        return count

    def _seed_universe(self, universe: list[dict[str, Any]]) -> int:
        inserted_or_updated = 0

        for item in universe:
            self.conn.execute(
                iq.UPSERT_BENCHMARK_INDEX,
                [
                    item["index_id"],
                    item["index_name"],
                    item["index_family"],
                    item["index_category"],
                    item.get("region"),
                    item.get("country_code"),
                    item["currency"],
                    item.get("is_core", False),
                    item.get("notes"),
                ],
            )

            for symbol in item.get("symbols", []):
                self.conn.execute(
                    iq.UPSERT_BENCHMARK_INDEX_SYMBOL,
                    [
                        item["index_id"],
                        symbol["provider"],
                        symbol["provider_symbol"],
                        symbol["symbol_purpose"],
                        symbol.get("is_primary", False),
                        symbol.get("is_proxy", False),
                    ],
                )

            inserted_or_updated += 1

        return inserted_or_updated

    def _get_index_ids_by_category(self, index_category: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT index_id
            FROM benchmark_index
            WHERE index_category = ?
              AND is_active = TRUE
            ORDER BY index_id;
            """,
            [index_category],
        ).fetchall()

        return [row[0] for row in rows]

    def _get_symbols_for_purpose(
        self,
        index_id: str,
        exact_purpose: str,
        proxy_purpose: str,
    ) -> list[IndexSymbol]:
        rows = self.conn.execute(
            iq.GET_ALL_SYMBOLS_FOR_PURPOSE,
            [index_id, exact_purpose, proxy_purpose],
        ).fetchall()

        symbols = [
            IndexSymbol(
                index_id=row[0],
                provider=row[1],
                provider_symbol=row[2],
                symbol_purpose=row[3],
                is_primary=bool(row[4]),
                is_proxy=bool(row[5]),
            )
            for row in rows
        ]

        if not symbols:
            raise ValueError(
                f"No benchmark_index_symbol found for {index_id}: "
                f"{exact_purpose}/{proxy_purpose}"
            )

        return symbols

    def _fetch_with_fallback(
        self,
        symbols: list[IndexSymbol],
        fetch_method_name: str,
        **kwargs,
    ) -> list[Any]:
        errors: list[str] = []

        for symbol in symbols:
            provider = self.provider_registry.get(symbol.provider)

            if provider is None:
                errors.append(f"{symbol.provider}: provider not registered")
                continue

            fetch_method = getattr(provider, fetch_method_name)

            try:
                rows = fetch_method(
                    index_id=symbol.index_id,
                    provider_symbol=symbol.provider_symbol,
                    is_proxy=symbol.is_proxy,
                    **kwargs,
                )

                if rows:
                    return rows

                errors.append(f"{symbol.provider}/{symbol.provider_symbol}: no rows")

            except Exception as exc:
                errors.append(f"{symbol.provider}/{symbol.provider_symbol}: {exc}")

        raise ValueError("All providers failed: " + " | ".join(errors))

    def _upsert_daily_bars(self, index_id: str, bars: list[IndexDailyBar]) -> int:
        bars = sorted(bars, key=lambda bar: bar.price_date)

        existing_rows = self.conn.execute(
            iq.GET_DAILY_CLOSES_TO_DATE,
            [index_id, bars[-1].price_date],
        ).fetchall()

        close_by_date = {row[0]: float(row[1]) for row in existing_rows}

        inserted = 0
        previous_close: float | None = None

        for bar in bars:
            if previous_close is None:
                previous_close = self._previous_close_from_existing(
                    close_by_date,
                    bar.price_date,
                )

            price_return_1d = None
            if previous_close is not None and previous_close > 0:
                price_return_1d = (bar.close / previous_close) - 1

            self.conn.execute(
                iq.UPSERT_DAILY_PRICE,
                [
                    bar.index_id,
                    bar.price_date,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.adj_close,
                    bar.volume,
                    previous_close,
                    price_return_1d,
                    price_return_1d,
                    bar.source,
                    bar.source_symbol,
                    bar.is_proxy,
                ],
            )

            close_by_date[bar.price_date] = bar.close
            previous_close = bar.close
            inserted += 1

        return inserted

    def _previous_close_from_existing(
        self,
        close_by_date: dict[date, float],
        current_date: date,
    ) -> float | None:
        previous_dates = [d for d in close_by_date if d < current_date]

        if not previous_dates:
            return None

        return close_by_date[max(previous_dates)]

    def _refresh_exposure_snapshots(
        self,
        index_id: str,
        snapshot_date: date,
        source: str,
        source_type: str,
        is_proxy: bool,
        constituents: list[Any],
    ) -> None:
        self.conn.execute(iq.DELETE_EXPOSURES_FOR_SNAPSHOT, [index_id, snapshot_date])

        for dimension_type, attr_name in [
            ("country", "country_code"),
            ("sector", "sector"),
            ("industry", "industry"),
            ("currency", "currency"),
        ]:
            weights: dict[str, float] = {}

            for constituent in constituents:
                value = getattr(constituent, attr_name)
                weight = constituent.weight_pct

                if value is None or weight is None:
                    continue

                weights[value] = weights.get(value, 0.0) + weight

            for value, weight in weights.items():
                self.conn.execute(
                    iq.INSERT_EXPOSURE,
                    [
                        index_id,
                        snapshot_date,
                        dimension_type,
                        value,
                        weight,
                        source,
                        source_type,
                        is_proxy,
                    ],
                )

    def _mark_sync_success(self, index_id: str, job_type: str, success_date: date) -> None:
        self.conn.execute(iq.UPSERT_SYNC_STATE_SUCCESS, [index_id, job_type, success_date])

    def _mark_sync_failure(self, index_id: str, job_type: str, exc: Exception) -> None:
        self.conn.execute(iq.UPSERT_SYNC_STATE_FAILURE, [index_id, job_type, str(exc)[:1000]])

    def _sum_known_weights(self, weights: list[float | None]) -> float | None:
        known = [weight for weight in weights if weight is not None]
        return sum(known) if known else None

    def _composition_quality(self, is_proxy: bool, total_weight_pct: float | None) -> str:
        if is_proxy:
            return "proxy"

        if total_weight_pct is None:
            return "partial"

        if 95 <= total_weight_pct <= 105:
            return "exact"

        return "partial"

    def _simple_return(self, closes: list[float], i: int, lookback: int) -> float | None:
        if i - lookback < 0:
            return None

        previous = closes[i - lookback]
        current = closes[i]

        if previous <= 0:
            return None

        return (current / previous) - 1

    def _ytd_return(self, dates: list[date], closes: list[float], i: int) -> float | None:
        current_year = dates[i].year

        start_idx = None
        for j in range(i, -1, -1):
            if dates[j].year != current_year:
                break
            start_idx = j

        if start_idx is None or start_idx == i:
            return None

        start_close = closes[start_idx]
        if start_close <= 0:
            return None

        return (closes[i] / start_close) - 1

    def _annualized_volatility(
        self,
        closes: list[float],
        i: int,
        lookback: int,
    ) -> float | None:
        if i - lookback < 0:
            return None

        window = closes[i - lookback : i + 1]
        returns = self._log_returns(window)

        if len(returns) < 2:
            return None

        return statistics.stdev(returns) * math.sqrt(252)

    def _average(self, values: list[float], i: int, lookback: int) -> float | None:
        if i - lookback + 1 < 0:
            return None

        window = values[i - lookback + 1 : i + 1]
        return sum(window) / len(window)

    def _log_returns(self, closes: list[float]) -> list[float]:
        returns = []

        for i in range(1, len(closes)):
            if closes[i - 1] <= 0 or closes[i] <= 0:
                continue

            returns.append(math.log(closes[i] / closes[i - 1]))

        return returns

    def _correlation(self, xs: list[float], ys: list[float]) -> float | None:
        if len(xs) != len(ys) or len(xs) < 2:
            return None

        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)

        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denom_x = sum((x - mean_x) ** 2 for x in xs)
        denom_y = sum((y - mean_y) ** 2 for y in ys)

        denominator = math.sqrt(denom_x * denom_y)

        if denominator == 0:
            return None

        return numerator / denominator

    def _beta(self, xs: list[float], ys: list[float]) -> float | None:
        if len(xs) != len(ys) or len(xs) < 2:
            return None

        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)

        covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        variance_y = sum((y - mean_y) ** 2 for y in ys)

        if variance_y == 0:
            return None

        return covariance / variance_y