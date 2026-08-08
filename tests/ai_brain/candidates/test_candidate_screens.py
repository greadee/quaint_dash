from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from dashboard.ai_brain.candidates import (
    CandidateScreenAdapters,
    OutsideHoldingUniverseBuilder,
)
from dashboard.analytics.persistence import AnalyticsStorageService
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
SNAPSHOT_DATE = date(2026, 8, 6)
UPDATED_AT = datetime(2026, 8, 6, 12, 0)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-screens.db")
    init_db(db)
    AnalyticsStorageService(db.conn).ensure_schema()
    db.conn.execute(
        "INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Primary')"
    )
    db.conn.execute(
        """
        INSERT INTO business_strength_methodology(id, version, name, description)
        VALUES (1, 'business-strength.v1', 'Fixture', 'Fixture')
        """
    )
    db.conn.execute(
        """
        INSERT INTO business_strength_template(
            id, methodology_id, template_code, name, version, configuration_json
        )
        VALUES (1, 1, 'standard', 'Standard', 1, '{}')
        """
    )
    yield db.conn
    db.conn.close()


def _asset(conn, asset_id: str) -> None:
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, ccy, name, created_at, updated_at
        )
        VALUES (?, ?, 'stock', 'USD', ?, ?, ?)
        """,
        [asset_id, asset_id, asset_id, UPDATED_AT, UPDATED_AT],
    )


def _quality(
    conn,
    asset_id: str,
    *,
    score: float,
    confidence: float = 90,
    completeness: float = 90,
) -> None:
    conn.execute(
        """
        INSERT INTO business_strength_analysis_run(
            id, asset_id, methodology_id, template_id, analysis_date,
            source_data_as_of, overall_score, classification, confidence_score,
            completeness_score, status, created_at, updated_at
        )
        VALUES (
            nextval('seq_business_strength_analysis_run_id'), ?, 1, 1, ?, ?, ?,
            'Strong', ?, ?, 'complete', ?, ?
        )
        """,
        [
            asset_id,
            SNAPSHOT_DATE,
            UPDATED_AT,
            score,
            confidence,
            completeness,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )


def _value(conn, asset_id: str, *, margin: float) -> None:
    payload = json.dumps(
        {
            "discounted_cash_flow": {"margin_of_safety": margin},
            "dividend_discount": {"margin_of_safety": margin},
        }
    )
    conn.execute(
        """
        INSERT INTO asset_analytics_snapshot(
            asset_id, snapshot_date, payload_json, missing_inputs_json, refreshed_at
        )
        VALUES (?, ?, ?, '[]', ?)
        """,
        [asset_id, SNAPSHOT_DATE, payload, UPDATED_AT],
    )


def _momentum(conn, asset_id: str, *, score: float) -> None:
    conn.execute(
        """
        INSERT INTO ticker_factor_snapshot(
            asset_id, ticker, snapshot_date, momentum_score,
            volatility_score, overall_factor_score, explanation,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 50, ?, 'fixture', ?, ?)
        """,
        [asset_id, asset_id, SNAPSHOT_DATE, score, score, UPDATED_AT, UPDATED_AT],
    )


def test_screen_thresholds_qualify_only_supported_stored_rows(conn) -> None:
    for asset_id in ("ALPHA", "BETA", "LOW"):
        _asset(conn, asset_id)
    _quality(conn, "ALPHA", score=85)
    _quality(conn, "BETA", score=75)
    _quality(conn, "LOW", score=69.99)
    _value(conn, "ALPHA", margin=0.50)
    _value(conn, "BETA", margin=0.25)
    _value(conn, "LOW", margin=-0.25)
    _momentum(conn, "ALPHA", score=90)
    _momentum(conn, "BETA", score=70)
    _momentum(conn, "LOW", score=69.99)
    adapters = CandidateScreenAdapters(conn)

    quality = adapters.quality(as_of=AS_OF)
    value = adapters.value(as_of=AS_OF)
    momentum = adapters.momentum(as_of=AS_OF)

    assert [item.source_asset_id for item in quality.nominations] == ["ALPHA", "BETA"]
    assert [item.source_asset_id for item in value.nominations] == ["ALPHA", "BETA"]
    assert [item.source_asset_id for item in momentum.nominations] == ["ALPHA", "BETA"]
    assert all(item.source_match.evidence_refs for item in quality.nominations)
    assert all(item.source_match.nomination_strength is not None for item in value.nominations)


def test_screen_distinguishes_no_qualifiers_from_missing_snapshot(conn) -> None:
    _asset(conn, "LOW")
    _quality(conn, "LOW", score=20)
    _momentum(conn, "LOW", score=20)
    adapters = CandidateScreenAdapters(conn)

    quality = adapters.quality(as_of=AS_OF)
    value = adapters.value(as_of=AS_OF)

    assert quality.watermark.coverage_state == "available"
    assert quality.limitations == ("source.quality_screen.no_qualifying_assets",)
    assert value.watermark.coverage_state == "missing"
    assert value.limitations == ("source.value_screen.snapshot_missing",)


def test_universe_merges_all_three_screen_reasons_once(conn) -> None:
    _asset(conn, "ALPHA")
    _quality(conn, "ALPHA", score=85)
    _value(conn, "ALPHA", margin=0.50)
    _momentum(conn, "ALPHA", score=90)

    pool = OutsideHoldingUniverseBuilder(conn).build(portfolio_id=1, as_of=AS_OF)

    assert len(pool.candidates) == 1
    candidate = pool.candidates[0]
    assert candidate.asset_id == "ALPHA"
    assert {match.source_family for match in candidate.source_matches} == {
        "momentum_screen",
        "quality_screen",
        "value_screen",
    }
    assert candidate.reason_codes == (
        "source.screen.momentum",
        "source.screen.quality",
        "source.screen.value",
    )
