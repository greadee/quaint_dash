import pytest

from dashboard.db.db_conn import DB, init_db
from dashboard.services.business_strength import BusinessStrengthAnalyzer, BusinessStrengthTemplateRegistry
from dashboard.services.business_strength.normalization import absolute_score, percentile


def seed_business_strength_fixture(conn):
    conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry, mkt_cap, shares_outstanding)
        VALUES
            ('NVDA', 'NVDA', 'stock', 'USD', 'NVIDIA Corp', 'Technology', 'Semiconductors', 2500, 250),
            ('AMD', 'AMD', 'stock', 'USD', 'Advanced Micro Devices', 'Technology', 'Semiconductors', 500, 160),
            ('TSM', 'TSM', 'stock', 'USD', 'Taiwan Semiconductor', 'Technology', 'Semiconductors', 700, 520);
        """
    )
    for asset_id, revenue, gross, operating, net_income, shares, cash, debt, equity, total_assets, fcf, sbc, buybacks in [
        ("NVDA", 1000, 700, 360, 300, 250, 400, 100, 900, 1300, 330, 30, -90),
        ("AMD", 650, 330, 80, 65, 160, 90, 60, 360, 620, 85, 20, -10),
        ("TSM", 900, 480, 300, 260, 520, 180, 120, 700, 1200, 170, 5, -20),
    ]:
        conn.execute(
            """
            INSERT INTO financial_statement(asset_id, statement_type, year, quarter, period_end_date, data_json, source)
            VALUES
                (?, 'income', 2025, 4, '2025-12-31', ?, 'test'),
                (?, 'income', 2024, 4, '2024-12-31', ?, 'test'),
                (?, 'income', 2023, 4, '2023-12-31', ?, 'test'),
                (?, 'income', 2022, 4, '2022-12-31', ?, 'test'),
                (?, 'balance', 2025, 4, '2025-12-31', ?, 'test'),
                (?, 'cashflow', 2025, 4, '2025-12-31', ?, 'test')
            """,
            [
                asset_id,
                f'{{"revenue":{revenue},"grossProfit":{gross},"operatingIncome":{operating},"netIncome":{net_income},"ebitda":{operating + 80},"weightedAverageShsOutDil":{shares},"researchAndDevelopmentExpenses":100,"customerConcentration":30}}',
                asset_id,
                f'{{"revenue":{revenue * 0.8},"grossProfit":{gross * 0.75},"operatingIncome":{operating * 0.7},"netIncome":{net_income * 0.7},"weightedAverageShsOutDil":{shares * 0.98}}}',
                asset_id,
                f'{{"revenue":{revenue * 0.65},"grossProfit":{gross * 0.6},"operatingIncome":{operating * 0.55},"netIncome":{net_income * 0.5},"weightedAverageShsOutDil":{shares * 0.97}}}',
                asset_id,
                f'{{"revenue":{revenue * 0.5},"grossProfit":{gross * 0.45},"operatingIncome":{operating * 0.4},"netIncome":{net_income * 0.35},"weightedAverageShsOutDil":{shares * 0.96}}}',
                asset_id,
                f'{{"cashAndCashEquivalents":{cash},"totalDebt":{debt},"totalStockholdersEquity":{equity},"totalAssets":{total_assets},"totalCurrentAssets":500,"totalCurrentLiabilities":200,"inventory":120}}',
                asset_id,
                f'{{"freeCashFlow":{fcf},"stockBasedCompensation":{sbc},"commonStockRepurchased":{buybacks}}}',
            ],
        )


def test_normalization_directionality_and_percentiles():
    assert absolute_score(0.25, 0.0, 0.5, "higher_is_better") == pytest.approx(50)
    assert absolute_score(0.25, 0.0, 0.5, "lower_is_better") == pytest.approx(50)
    assert percentile(3, [1, 2, 3, 4], "higher_is_better") == pytest.approx(75)
    assert percentile(3, [1, 2, 3, 4], "lower_is_better") == pytest.approx(25)


def test_template_registry_classifies_required_portfolio_examples():
    registry = BusinessStrengthTemplateRegistry()
    expected = {
        "NVDA": "semiconductor_designer",
        "TSM": "semiconductor_foundry",
        "ASML": "semiconductor_equipment",
        "MU": "memory_semiconductor",
        "ANET": "networking_hardware",
        "V": "payments_network",
        "JPM": "bank",
        "FFH": "insurance",
        "SPGI": "exchange_financial_data",
        "BN": "diversified_holding_company",
        "BN.TO": "diversified_holding_company",
        "KKR": "alternative_asset_manager",
        "ISRG": "medical_device",
        "WCN": "waste_management",
        "WCN.TO": "waste_management",
        "FTS": "utility",
        "ENB": "midstream",
        "AMZN": "marketplace",
    }
    for symbol, template_code in expected.items():
        template, source, confidence = registry.classify(symbol, None, None, None)
        assert template.template_code == template_code
        assert source == "verified_ticker_classification"
        assert confidence >= 0.9


def test_business_strength_run_persists_auditable_scorecard(tmp_path):
    db = DB(str(tmp_path / "business_strength.db"))
    init_db(db)
    seed_business_strength_fixture(db.conn)

    scorecard = BusinessStrengthAnalyzer(db.conn).run("NVDA")

    assert scorecard.template_code == "semiconductor_designer"
    assert scorecard.overall_score == pytest.approx(70.52, abs=0.1)
    assert scorecard.classification == "Strong"
    assert scorecard.confidence_score > 70
    assert scorecard.completeness_score > 70
    assert scorecard.analysis_run_id is not None
    assert sum(category.category_weight for category in scorecard.category_scores) == pytest.approx(1)
    recomputed = sum(
        (category.adjusted_score or 0) * category.category_weight
        for category in scorecard.category_scores
        if category.adjusted_score is not None
    )
    assert scorecard.overall_score == pytest.approx(recomputed, abs=0.05)
    metric_count = db.conn.execute(
        "SELECT COUNT(*) FROM business_strength_metric_result WHERE analysis_run_id = ?",
        [scorecard.analysis_run_id],
    ).fetchone()[0]
    assert metric_count >= 18


def test_business_strength_missing_data_reduces_confidence(tmp_path):
    db = DB(str(tmp_path / "missing_business_strength.db"))
    init_db(db)
    db.conn.execute(
        """
        INSERT INTO asset(asset_id, symbol, asset_type, ccy, name, sector, industry)
        VALUES ('EMPTY', 'EMPTY', 'stock', 'USD', 'Empty Co', 'Technology', 'Software')
        """
    )

    scorecard = BusinessStrengthAnalyzer(db.conn).run("EMPTY")

    assert scorecard.overall_score is None
    assert scorecard.status == "insufficient_data"
    assert scorecard.confidence_score < 50
    assert "Three-year revenue CAGR" in scorecard.missing_critical_metrics
