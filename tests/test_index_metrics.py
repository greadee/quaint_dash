from dashboard.ingestion.indices.index_ingestion_service import BenchmarkIndexIngestionService

from tests.fixture_index import insert_daily_price_rows


def test_daily_metrics_compute_rolling_returns_and_volatility(conn):
    insert_daily_price_rows(conn, index_id="SP500", start_close=100.0, days=260)

    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    inserted = service.compute_daily_metrics("SP500")

    row = conn.execute(
        """
        SELECT
            return_21d,
            volatility_21d_ann,
            sma_50,
            sma_200,
            high_52w,
            low_52w,
            drawdown_from_52w_high
        FROM benchmark_index_daily_metric
        WHERE index_id = 'SP500'
        ORDER BY metric_date DESC
        LIMIT 1;
        """
    ).fetchone()

    assert inserted > 0
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[3] is not None
    assert row[4] is not None
    assert row[5] is not None
    assert row[6] == 0.0


def test_relative_metrics_compute_beta_and_correlation(conn):
    insert_daily_price_rows(conn, index_id="SP500", start_close=100.0, days=270)
    insert_daily_price_rows(conn, index_id="NDX100", start_close=200.0, days=270)

    service = BenchmarkIndexIngestionService(conn, provider_registry={})

    inserted = service.compute_relative_metrics(
        index_id="NDX100",
        comparison_index_id="SP500",
    )

    row = conn.execute(
        """
        SELECT correlation_252d, beta_252d, excess_return_252d
        FROM benchmark_index_relative_metric
        WHERE index_id = 'NDX100'
          AND comparison_index_id = 'SP500'
        ORDER BY metric_date DESC
        LIMIT 1;
        """
    ).fetchone()

    assert inserted > 0
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert row[0] > 0.90