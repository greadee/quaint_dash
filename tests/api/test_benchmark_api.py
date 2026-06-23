from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from dashboard.api.app import create_app
from dashboard.db.db_conn import DB
from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService
from dashboard.ingestion.indices.index_models import IndexConstituent

from tests.ingestion_benchmarks.benchmark_fakes import FakeDailyPriceProvider


def _seed_benchmark(conn) -> None:
    conn.execute(
        """
        INSERT INTO benchmark_index (
            index_id,
            index_name,
            index_family,
            index_category,
            region,
            country_code,
            currency,
            is_core,
            is_active,
            notes
        )
        VALUES
            ('SP500', 'S&P 500', 'S&P', 'core_geo', 'North America', 'US', 'USD', TRUE, TRUE, 'Large cap US'),
            ('SEC_TECH', 'Information Technology Sector', 'Select Sector SPDR', 'sector', 'United States', 'US', 'USD', FALSE, TRUE, 'Technology sector'),
            ('IND_SEMICONDUCTORS', 'Semiconductors Industry', 'iShares', 'industry', 'Global', NULL, 'USD', FALSE, TRUE, 'Semiconductor industry'),
            ('TECH', 'Technology Select', 'Sector', 'sector', 'North America', 'US', 'USD', FALSE, TRUE, 'Technology')
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_symbol (
            index_id,
            provider,
            provider_symbol,
            symbol_purpose,
            is_primary,
            is_proxy
        )
        VALUES
            ('SP500', 'yfinance', '^GSPC', 'price_daily', TRUE, FALSE),
            ('SP500', 'fmp', 'SPY', 'proxy_holdings', FALSE, TRUE),
            ('IND_SEMICONDUCTORS', 'yfinance', 'SOXX', 'price_daily', TRUE, TRUE),
            ('IND_SEMICONDUCTORS', 'yfinance', 'SMH', 'price_daily', FALSE, TRUE),
            ('IND_SEMICONDUCTORS', 'fmp', 'SMH', 'proxy_holdings', FALSE, TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_daily_price (
            index_id,
            price_date,
            open,
            high,
            low,
            close,
            adj_close,
            volume,
            source,
            source_symbol,
            is_proxy
        )
        VALUES
            ('SP500', '2026-01-01', 99, 101, 98, 100, 100, 1000, 'test', '^GSPC', FALSE),
            ('SP500', '2026-01-02', 100, 103, 99, 102, 102, 1200, 'test', '^GSPC', FALSE),
            ('TECH', '2026-01-01', 49, 51, 48, 50, 50, 500, 'test', 'TECH', FALSE)
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_daily_metric (
            index_id,
            metric_date,
            return_1d,
            return_5d,
            return_21d,
            return_252d,
            volatility_252d_ann,
            sma_50,
            high_52w,
            low_52w,
            drawdown_from_52w_high
        )
        VALUES
            ('SP500', '2026-01-02', 0.02, 0.04, 0.08, 0.15, 0.18, 95, 110, 80, -0.07),
            ('TECH', '2026-01-01', 0.01, 0.02, 0.05, 0.20, 0.25, 45, 55, 40, -0.09)
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_composition_snapshot (
            index_id,
            snapshot_date,
            source,
            source_symbol,
            source_type,
            is_proxy,
            constituent_count,
            total_weight_pct,
            data_quality
        )
        VALUES ('SP500', '2026-01-02', 'test', 'SPY', 'etf_proxy', TRUE, 2, 100, 'proxy')
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_constituent (
            index_id,
            snapshot_date,
            source,
            constituent_symbol,
            constituent_name,
            exchange_code,
            country_code,
            currency,
            sector,
            industry,
            weight_pct,
            market_cap,
            is_proxy
        )
        VALUES
            ('SP500', '2026-01-02', 'test', 'MSFT', 'Microsoft', 'XNAS', 'US', 'USD', 'Technology', 'Software', 7.5, 3000, TRUE),
            ('SP500', '2026-01-02', 'test', 'AAPL', 'Apple', 'XNAS', 'US', 'USD', 'Technology', 'Hardware', 6.5, 2800, TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_exposure_snapshot (
            index_id,
            snapshot_date,
            dimension_type,
            dimension_value,
            weight_pct,
            source,
            source_type,
            is_proxy
        )
        VALUES
            ('SP500', '2026-01-02', 'sector', 'Technology', 14, 'test', 'computed_from_constituents', TRUE),
            ('SP500', '2026-01-02', 'country', 'US', 100, 'test', 'computed_from_constituents', TRUE)
        """
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_sync_state (
            index_id,
            job_type,
            last_success_at,
            last_attempt_at,
            last_success_date,
            last_error
        )
        VALUES
            ('SP500', 'daily_price', '2026-01-02 10:00:00', '2026-01-02 10:00:00', '2026-01-02', NULL),
            ('SP500', 'composition', '2026-01-02 11:00:00', '2026-01-02 11:00:00', '2026-01-02', 'proxy only')
        """
    )


def _client_with_benchmarks(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_benchmark(db.conn)
    db.conn.close()
    return TestClient(app)


def test_list_benchmarks_filters_and_latest_rollups(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        response = client.get("/api/v1/benchmarks?q=s%26p&category=core_geo&currency=USD")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["index_id"] == "SP500"
    assert payload[0]["latest_close"] == 102
    assert payload[0]["composition_quality"] == "proxy"
    assert payload[0]["last_error"] == "proxy only"


def test_list_benchmarks_searches_proxy_symbols_without_changing_canonical_index(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        smh = client.get("/api/v1/benchmarks?q=SMH")
        soxx = client.get("/api/v1/benchmarks?q=SOXX")

    assert smh.status_code == 200
    assert soxx.status_code == 200
    assert [item["index_id"] for item in smh.json()] == ["IND_SEMICONDUCTORS"]
    assert [item["index_id"] for item in soxx.json()] == ["IND_SEMICONDUCTORS"]


def test_benchmark_detail_prices_metrics_constituents_and_exposures(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        detail = client.get("/api/v1/benchmarks/SP500")
        prices = client.get("/api/v1/benchmarks/SP500/prices?limit=2")
        metrics = client.get("/api/v1/benchmarks/SP500/metrics?limit=1")
        constituents = client.get("/api/v1/benchmarks/SP500/constituents?limit=1")
        exposures = client.get("/api/v1/benchmarks/SP500/exposures?dimension_type=sector")

    assert detail.status_code == 200
    assert detail.json()["symbols"][0]["provider_symbol"] == "^GSPC"
    assert detail.json()["sync_state"]["composition"]["last_error"] == "proxy only"
    assert detail.json()["available_price_range"]["first_price_date"] == "2026-01-01"
    assert prices.json()[0]["date"] == "2026-01-01"
    assert metrics.json()[0]["return_252d"] == 0.15
    assert constituents.json()["total"] == 2
    assert constituents.json()["items"][0]["constituent_symbol"] == "MSFT"
    assert exposures.json()[0]["dimension_value"] == "Technology"


def test_benchmark_prices_preserve_proxy_metadata_and_date_filters(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        response = client.get(
            "/api/v1/benchmarks/SP500/prices?start_date=2026-01-02&end_date=2026-01-02&limit=10"
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["date"] for item in payload] == ["2026-01-02"]
    assert payload[0]["close"] == 102
    assert payload[0]["source_symbol"] == "^GSPC"
    assert payload[0]["is_proxy"] is False


def test_benchmark_missing_history_returns_empty_series_not_zeroes(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        prices = client.get("/api/v1/benchmarks/SEC_TECH/prices")
        metrics = client.get("/api/v1/benchmarks/SEC_TECH/metrics")
        detail = client.get("/api/v1/benchmarks/SEC_TECH")

    assert prices.status_code == 200
    assert metrics.status_code == 200
    assert detail.status_code == 200
    assert prices.json() == []
    assert metrics.json() == []
    assert detail.json()["latest_close"] is None
    assert detail.json()["return_252d"] is None


def test_benchmark_exposure_filter_preserves_source_and_proxy_disclosure(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        country = client.get("/api/v1/benchmarks/SP500/exposures?dimension_type=country")

    assert country.status_code == 200
    payload = country.json()
    assert len(payload) == 1
    assert payload[0]["dimension_value"] == "US"
    assert payload[0]["source_type"] == "computed_from_constituents"
    assert payload[0]["is_proxy"] is True


def test_benchmark_readiness_reports_all_display_gaps(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        response = client.get("/api/v1/benchmarks/readiness?category=core_geo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    by_key = {requirement["key"]: requirement for requirement in item["requirements"]}
    assert item["index_id"] == "SP500"
    assert item["ready"] is False
    assert by_key["daily_prices"]["ready"] is False
    assert by_key["daily_metrics"]["ready"] is True
    assert by_key["composition"]["ready"] is True
    assert by_key["constituents"]["ready"] is True
    assert by_key["exposures"]["ready"] is True


def test_missing_benchmark_returns_404(tmp_path):
    with _client_with_benchmarks(tmp_path) as client:
        response = client.get("/api/v1/benchmarks/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_default_benchmark_endpoints_use_analytics_defaults(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_benchmark(db.conn)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, country)
        VALUES ('MSFT', 'MSFT', 'stock', 'USD', 'US')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('MSFT', '2026-01-02', 400, 400, 'test')
        """
    )
    db.conn.execute(
        """
        INSERT INTO portfolio(portfolio_id, portfolio_name, base_ccy)
        VALUES (1, 'Core', 'USD')
        """
    )
    db.conn.execute(
        """
        INSERT INTO position(portfolio_id, asset_id, qty, book_cost, created_at, updated_at)
        VALUES (1, 'MSFT', 2, 600, now(), now())
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        asset_response = client.get("/api/v1/benchmarks/defaults/asset/MSFT")
        portfolio_response = client.get("/api/v1/benchmarks/defaults/portfolio/1")

    assert asset_response.status_code == 200
    assert asset_response.json()["benchmark_index_id"] == "SP500"
    assert portfolio_response.status_code == 200
    assert portfolio_response.json()["benchmark_index_id"] == "SP500"


def test_asset_search_and_benchmark_association_suggests_core_sector_and_industry(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_benchmark(db.conn)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country)
        VALUES ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 'US')
        """
    )
    db.conn.execute(
        """
        INSERT INTO asset_quote_daily(asset_id, date, close, adj_close, ing_source)
        VALUES ('NVDA', '2026-01-02', 120, 120, 'test')
        """
    )
    db.conn.close()

    with TestClient(app) as client:
        search = client.get("/api/v1/assets?q=nvd")
        associations = client.get("/api/v1/benchmarks/associations/asset/NVDA")

    assert search.status_code == 200
    assert search.json()[0]["asset_id"] == "NVDA"
    assert associations.status_code == 200
    payload = associations.json()
    assert payload["asset"]["symbol"] == "NVDA"
    by_role = {item["role"]: item["benchmark_index_id"] for item in payload["associations"]}
    assert by_role == {
        "core": "SP500",
        "sector": "SEC_TECH",
        "industry": "IND_SEMICONDUCTORS",
    }


def test_benchmark_association_suggests_expanded_industry_universe(tmp_path):
    db_path = tmp_path / "api.db"
    app = create_app(db_path)
    db = DB(db_path)
    _seed_benchmark(db.conn)
    db.conn.executemany(
        """
        INSERT INTO benchmark_index (
            index_id, index_name, index_family, index_category, region,
            country_code, currency, is_core, is_active, notes
        )
        VALUES (?, ?, ?, 'industry', 'United States', 'US', 'USD', FALSE, TRUE, ?)
        """,
        [
            ("IND_INTERNET", "Internet Industry", "First Trust", "Internet industry"),
            ("IND_BANKS", "Banks Industry", "SPDR", "Bank industry"),
            ("IND_PHARMACEUTICALS", "Pharmaceuticals Industry", "iShares", "Pharmaceuticals industry"),
        ],
    )
    db.conn.executemany(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, country)
        VALUES (?, ?, 'stock', 'USD', ?, ?, ?, 'US')
        """,
        [
            ("GOOG", "GOOG", "Alphabet Inc.", "Communication Services", "Internet Content & Information"),
            ("JPM", "JPM", "JPMorgan Chase & Co.", "Financial Services", "Banks - Diversified"),
            ("LLY", "LLY", "Eli Lilly and Company", "Healthcare", "Medical - Pharmaceuticals"),
        ],
    )
    db.conn.close()

    with TestClient(app) as client:
        responses = {
            symbol: client.get(f"/api/v1/benchmarks/associations/asset/{symbol}")
            for symbol in ("GOOG", "JPM", "LLY")
        }

    assert {symbol: response.status_code for symbol, response in responses.items()} == {
        "GOOG": 200,
        "JPM": 200,
        "LLY": 200,
    }
    assert {
        symbol: {
            item["role"]: item["benchmark_index_id"]
            for item in response.json()["associations"]
        }["industry"]
        for symbol, response in responses.items()
    } == {
        "GOOG": "IND_INTERNET",
        "JPM": "IND_BANKS",
        "LLY": "IND_PHARMACEUTICALS",
    }


def test_seed_and_refresh_use_index_service_paths(tmp_path, monkeypatch):
    calls: list[tuple[str, object]] = []

    class FakeService:
        def seed_core_universe(self):
            calls.append(("seed", "core"))
            return 3

        def seed_sector_industry_universe(self):
            return 0

        def seed_all_universes(self):
            return 0

        def compute_daily_metrics(self, index_id):
            calls.append(("metrics", index_id))
            return 5

    def fake_service(_conn):
        return FakeService()

    monkeypatch.setattr("dashboard.api.services.create_index_ingestion_service", fake_service)

    with _client_with_benchmarks(tmp_path) as client:
        seed_response = client.post("/api/v1/benchmarks/seed", json={"scope": "core"})
        refresh_response = client.post(
            "/api/v1/benchmarks/SP500/refresh",
            json={"job_type": "metrics"},
        )

    assert seed_response.status_code == 200
    assert seed_response.json()["result"]["seeded_count"] == 3
    assert refresh_response.status_code == 200
    assert refresh_response.json()["result"]["row_count"] == 5
    assert calls == [("seed", "core"), ("metrics", "SP500")]


def test_bulk_refresh_uses_scheduler_path(tmp_path, monkeypatch):
    @dataclass
    class FakeResult:
        job_type: str
        target_count: int
        row_count: int

    class FakeScheduler:
        service = object()

        def run_core_daily_refresh(self, lookback_days=10):
            return FakeResult(
                job_type=f"core_daily_{lookback_days}",
                target_count=2,
                row_count=9,
            )

    monkeypatch.setattr(
        "dashboard.api.services.create_index_scheduler",
        lambda _conn: FakeScheduler(),
    )

    with _client_with_benchmarks(tmp_path) as client:
        response = client.post(
            "/api/v1/benchmarks/refresh",
            json={"category": "core_geo", "job_type": "daily_price", "lookback_days": 7},
        )

    assert response.status_code == 200
    assert response.json()["result"]["job_type"] == "core_daily_7"
    assert response.json()["result"]["target_count"] == 2


def test_harden_selected_benchmark_populates_display_readiness(tmp_path, monkeypatch):
    class DisplayReadyProvider(FakeDailyPriceProvider):
        def __init__(self):
            super().__init__(closes=[100 + index for index in range(253)])

        def get_constituents(self, index_id, provider_symbol, is_proxy):
            return [
                IndexConstituent(
                    index_id=index_id,
                    constituent_symbol="MSFT",
                    constituent_name="Microsoft",
                    exchange_code="XNAS",
                    country_code="US",
                    currency="USD",
                    sector="Technology",
                    industry="Software",
                    weight_pct=60.0,
                    market_cap=3000,
                    source="fake",
                    is_proxy=is_proxy,
                ),
                IndexConstituent(
                    index_id=index_id,
                    constituent_symbol="NVDA",
                    constituent_name="NVIDIA",
                    exchange_code="XNAS",
                    country_code="US",
                    currency="USD",
                    sector="Technology",
                    industry="Semiconductors",
                    weight_pct=40.0,
                    market_cap=2500,
                    source="fake",
                    is_proxy=is_proxy,
                ),
            ]

    def fake_service(conn):
        provider = DisplayReadyProvider()
        return BenchmarkIndexIngestionService(conn, {"fmp": provider, "yfinance": provider})

    monkeypatch.setattr("dashboard.api.services.create_index_ingestion_service", fake_service)

    app = create_app(tmp_path / "api.db")
    with TestClient(app) as client:
        result = client.post(
            "/api/v1/benchmarks/SP500/harden",
            json={"lookback_days": 253, "include_composition": True},
        )
        readiness = client.get("/api/v1/benchmarks/SP500/readiness")

    assert result.status_code == 200
    assert result.json()["result"]["daily_price_rows"] == 253
    assert result.json()["result"]["metric_rows"] > 0
    assert result.json()["result"]["composition_rows"] == 2
    assert result.json()["result"]["ready"] is True
    assert readiness.json()["ready_count"] == 1
    assert readiness.json()["items"][0]["missing"] == []


def test_bulk_harden_uses_category_and_reports_missing_count(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []

    class FakeService:
        def seed_all_universes(self):
            calls.append(("seed", "all"))
            return 2

        def ingest_daily_prices(self, index_id, start, end):
            calls.append(("prices", index_id))
            return 2

        def compute_daily_metrics(self, index_id):
            calls.append(("metrics", index_id))
            return 1

        def ingest_composition(self, index_id, snapshot_date):
            calls.append(("composition", index_id))
            return 1

        def compute_relative_metrics(self, index_id, comparison_index_id):
            calls.append(("relative", index_id))
            return 0

    monkeypatch.setattr("dashboard.api.services.create_index_ingestion_service", lambda _conn: FakeService())

    with _client_with_benchmarks(tmp_path) as client:
        response = client.post(
            "/api/v1/benchmarks/harden",
            json={"category": "industry", "lookback_days": 253},
        )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["category"] == "industry"
    assert payload["target_count"] == 1
    assert ("prices", "IND_SEMICONDUCTORS") in calls
    assert ("composition", "IND_SEMICONDUCTORS") in calls
