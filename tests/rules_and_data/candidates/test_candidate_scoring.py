from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from dashboard.rules_and_data.candidates import (
    CANDIDATE_METHODOLOGY_VERSION,
    CandidateScoringEngine,
    CandidateSourceAdapters,
    OutsideHoldingUniverseBuilder,
    candidate_run_id,
    canonical_json,
    diversification_effect_score,
    growth_score_from_rate,
    speculative_score_from_volatility,
    value_score_from_margin,
)
from dashboard.rules_and_data.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    AllocationMix,
    InvestorProfile,
    ProfileDimension,
)
from dashboard.analytics.persistence import AnalyticsStorageService
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
SNAPSHOT_DATE = date(2026, 8, 6)
UPDATED_AT = datetime(2026, 8, 6, 12, 0)
RUN_ID = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, "a" * 64)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-scoring.db")
    init_db(db)
    AnalyticsStorageService(db.conn).ensure_schema()
    db.conn.execute(
        "INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Primary')"
    )
    db.conn.execute(
        "INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'fixture')"
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


def _asset(
    conn,
    asset_id: str,
    *,
    sector: str = "Healthcare",
    country: str = "US",
    asset_type: str = "stock",
) -> None:
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, ccy, name, sector, country,
            created_at, updated_at
        )
        VALUES (?, ?, ?, 'USD', ?, ?, ?, ?, ?)
        """,
        [
            asset_id,
            asset_id,
            asset_type,
            asset_id,
            sector,
            country,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )
    conn.executemany(
        """
        INSERT INTO asset_quote_daily(
            asset_id, date, open, high, low, close, adj_close, volume,
            ing_source, ing_at
        )
        VALUES (?, ?, 100, 101, 99, 100, 100, 100000, 'fixture', ?)
        """,
        [
            [asset_id, AS_OF.date() - timedelta(days=offset), UPDATED_AT]
            for offset in range(1, 21)
        ],
    )


def _hold(conn, asset_id: str) -> None:
    conn.execute(
        """
        INSERT INTO txn(
            portfolio_id, time_stamp, txn_type, asset_id, qty, price,
            ccy, cash_amt, batch_id
        )
        VALUES (1, ?, 'buy', ?, 1, 100, 'USD', -100, 1)
        """,
        [UPDATED_AT, asset_id],
    )


def _portfolio_snapshot(
    conn,
    held_asset_id: str,
    *,
    sectors: dict[str, float] | None = None,
    countries: dict[str, float] | None = None,
) -> None:
    payload = json.dumps(
        {
            "positions": [{"asset_id": held_asset_id, "weight": 1.0}],
            "risk_decomposition": {
                "sector_exposure": sectors or {"Technology": 1.0},
                "country_exposure": countries or {"CA": 1.0},
            },
        }
    )
    conn.execute(
        """
        INSERT INTO portfolio_analytics_snapshot(
            portfolio_id, snapshot_date, position_count, state_signature,
            payload_json, refreshed_at
        )
        VALUES (1, ?, 1, 'fixture', ?, ?)
        """,
        [SNAPSHOT_DATE, payload, UPDATED_AT],
    )


def _ranking(conn, asset_id: str, *, score: float = 80) -> None:
    conn.execute(
        """
        INSERT INTO stock_ranking_snapshot(
            asset_id, factor, snapshot_date, universe, score, action,
            confidence, data_status, latest_data_date, created_at, updated_at
        )
        VALUES (?, 'aggregate', ?, 'all', ?, 'watch', 0.9, 'complete', ?, ?, ?)
        """,
        [asset_id, SNAPSHOT_DATE, score, SNAPSHOT_DATE, UPDATED_AT, UPDATED_AT],
    )


def _candidate_metrics(
    conn,
    asset_id: str,
    *,
    growth: float,
    value: float,
    quality: float,
    income: float,
    speculative: float,
    sentiment: float = 0.2,
) -> None:
    volatility_factor = 100 - speculative
    conn.execute(
        """
        INSERT INTO ticker_factor_snapshot(
            asset_id, ticker, snapshot_date, growth_score, value_score,
            quality_score, momentum_score, dividend_score, volatility_score,
            overall_factor_score, factor_labels_json, explanation,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 75, ?, ?, 70, '[]', 'fixture', ?, ?)
        """,
        [
            asset_id,
            asset_id,
            SNAPSHOT_DATE,
            growth,
            value,
            quality,
            income,
            volatility_factor,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )
    conn.execute(
        """
        INSERT INTO business_strength_analysis_run(
            id, asset_id, methodology_id, template_id, analysis_date,
            source_data_as_of, overall_score, classification, confidence_score,
            completeness_score, status, created_at, updated_at
        )
        VALUES (
            nextval('seq_business_strength_analysis_run_id'), ?, 1, 1, ?, ?, ?,
            'Strong', 90, 90, 'complete', ?, ?
        )
        """,
        [
            asset_id,
            SNAPSHOT_DATE,
            UPDATED_AT,
            quality,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )
    analytics = json.dumps(
        {
            "discounted_cash_flow": {"margin_of_safety": 0.50},
            "dividend_discount": {"margin_of_safety": 0.50},
            "valuation_depth": {
                "revenue_growth_yoy": 0.20,
                "eps_growth_yoy": 0.20,
                "free_cash_flow_growth_yoy": 0.20,
            },
            "risk": {"annualized_volatility": 0.10 + speculative / 200},
        }
    )
    conn.execute(
        """
        INSERT INTO asset_analytics_snapshot(
            asset_id, snapshot_date, payload_json, missing_inputs_json, refreshed_at
        )
        VALUES (?, ?, ?, '[]', ?)
        """,
        [asset_id, SNAPSHOT_DATE, analytics, UPDATED_AT],
    )
    conn.execute(
        """
        INSERT INTO ticker_sentiment_daily(
            asset_id, ticker, date, blended_sentiment_score,
            retail_sentiment_score, news_sentiment_score,
            reddit_post_count, article_count, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 10, 4, ?, ?)
        """,
        [
            asset_id,
            asset_id,
            SNAPSHOT_DATE,
            sentiment,
            sentiment,
            sentiment,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )
    conn.execute(
        """
        INSERT INTO asset_business_classification(
            asset_id, sector, industry, template_code, classification_source,
            confidence, effective_from, created_at, updated_at
        )
        SELECT asset_id, sector, 'Fixture', 'standard', 'fixture',
               0.9, DATE '2026-01-01', ?, ?
        FROM asset
        WHERE asset_id = ?
        """,
        [UPDATED_AT, UPDATED_AT, asset_id],
    )


def _profile(
    profile_name: str,
    scores: tuple[float | None, float | None, float | None, float | None, float | None],
    *,
    portfolio_id: str = "1",
    confidence: float = 0.9,
) -> InvestorProfile:
    codes = ("growth", "value", "quality", "income", "speculative")
    factors = tuple(
        ProfileDimension(
            code=code,
            score=score,
            label="observed" if score is not None else "unknown",
            confidence=confidence if score is not None else 0.0,
            evidence_refs=(f"evidence:{profile_name}:{code}",) if score is not None else (),
            data_gaps=() if score is not None else (f"missing.factor.{code}",),
        )
        for code, score in zip(codes, scores, strict=True)
    )
    observed = ProfileDimension(
        code="observed_risk_posture",
        score=60 if confidence >= 0.35 else None,
        label="moderate" if confidence >= 0.35 else "unknown",
        confidence=confidence,
        evidence_refs=(f"evidence:{profile_name}:risk",) if confidence >= 0.35 else (),
    )
    return InvestorProfile(
        profile_id=f"profile:{profile_name}:{'1' * 48}",
        portfolio_id=portfolio_id,
        as_of=AS_OF,
        schema_version=INVESTOR_PROFILE_SCHEMA_VERSION,
        methodology_version=INVESTOR_PROFILE_METHODOLOGY_VERSION,
        input_snapshot_hash=(profile_name.encode().hex() + ("0" * 64))[:64],
        inference_scope="observed_portfolio_behavior",
        suitability_status="not_assessed_missing_stated_inputs",
        archetype_labels=(
            ("insufficient_data",) if confidence < 0.35 else (profile_name,)
        ),
        factor_scores=factors,
        observed_risk_posture=observed,
        concentration_profile=ProfileDimension(
            code="concentration_profile",
            score=80,
            label="concentrated" if profile_name == "concentrated_growth" else "diversified",
            confidence=confidence,
            evidence_refs=(f"evidence:{profile_name}:concentration",),
        ),
        geography_tilt=ProfileDimension(
            code="domestic_international_tilt",
            score=50,
            label="mixed",
            confidence=confidence,
            evidence_refs=(f"evidence:{profile_name}:geography",),
        ),
        sector_tilts=(),
        theme_tilts=(),
        allocation_mix=AllocationMix(
            etf_weight=0.5,
            passive_weight=0.5,
            direct_stock_weight=0.5,
            classified_weight=1.0,
            label="mixed",
            confidence=confidence,
            evidence_refs=(f"evidence:{profile_name}:allocation",),
        ),
        confidence=confidence,
        evidence_refs=(f"evidence:{profile_name}",),
        data_gaps=(),
    )


def _pool(conn, *asset_scores: tuple[str, float]):
    for asset_id, score in asset_scores:
        _ranking(conn, asset_id, score=score)
    ranking = CandidateSourceAdapters(conn).top_ranked(as_of=AS_OF, limit=100)
    return OutsideHoldingUniverseBuilder(conn).build_from_sources(
        portfolio_id=1,
        as_of=AS_OF,
        source_results=(ranking,),
    )


def _base_fixture(conn):
    _asset(conn, "HELD", sector="Technology", country="CA")
    _asset(conn, "GROWTH", sector="Healthcare", country="US")
    _asset(conn, "INCOME", sector="Utilities", country="US")
    _hold(conn, "HELD")
    _portfolio_snapshot(conn, "HELD")
    _candidate_metrics(
        conn,
        "GROWTH",
        growth=90,
        value=40,
        quality=80,
        income=20,
        speculative=80,
    )
    _candidate_metrics(
        conn,
        "INCOME",
        growth=40,
        value=85,
        quality=80,
        income=90,
        speculative=20,
    )
    return _pool(conn, ("GROWTH", 99), ("INCOME", 70))


@pytest.mark.parametrize(
    ("name", "scores", "expected_first", "expected_fit"),
    [
        ("concentrated_growth", (90, 40, 80, 20, 80), "GROWTH", 87.0),
        ("dividend_income", (40, 85, 80, 90, 20), "INCOME", 87.0),
        ("broad_etf", (55, 55, 70, 50, 20), "INCOME", 71.8),
        ("speculative_small_cap", (90, 40, 80, 20, 80), "GROWTH", 87.0),
        ("balanced", (60, 60, 60, 60, 50), "INCOME", 67.6),
    ],
)
def test_golden_profile_fixtures_have_exact_stable_order(
    conn,
    name,
    scores,
    expected_first,
    expected_fit,
) -> None:
    pool = _base_fixture(conn)
    result = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile(name, scores),
        run_id=RUN_ID,
    )

    assert [review.asset_id for review in result.ordered_reviews][0] == expected_first
    assert float(result.ordered_reviews[0].fit_score.value) == pytest.approx(expected_fit)
    assert result.ordered_reviews[0].diversification_score.value == 100
    assert result.ordered_reviews[0].redundancy_score.value == 0
    assert {highlight.category for highlight in result.ordered_reviews[0].highlights} == {
        "momentum",
        "quality",
        "risk",
        "sentiment",
        "valuation",
    }


def test_insufficient_profile_blocks_every_raw_ranking(conn) -> None:
    pool = _base_fixture(conn)
    profile = _profile("insufficient", (None, None, None, None, None), confidence=0.2)

    result = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=profile,
        run_id=RUN_ID,
    )

    assert all(review.eligibility_state == "blocked" for review in result.ordered_reviews)
    assert all(review.fit_score.value is None for review in result.ordered_reviews)
    assert all(review.warnings[0].blocking for review in result.ordered_reviews)


def test_repeated_and_permuted_inputs_are_byte_equivalent(conn) -> None:
    pool = _base_fixture(conn)
    permuted = replace(
        pool,
        candidates=tuple(
            replace(
                item,
                source_matches=tuple(reversed(item.source_matches)),
                evidence_refs=tuple(reversed(item.evidence_refs)),
            )
            for item in reversed(pool.candidates)
        ),
    )
    profile = _profile("balanced", (60, 60, 60, 60, 50))
    engine = CandidateScoringEngine(conn)

    first = engine.score(pool=pool, investor_profile=profile, run_id=RUN_ID)
    second = engine.score(pool=permuted, investor_profile=profile, run_id=RUN_ID)

    assert canonical_json(first) == canonical_json(second)
    assert first.output_hash == second.output_hash


def test_exact_score_ties_resolve_by_canonical_asset_id(conn) -> None:
    _asset(conn, "HELD", sector="Technology", country="CA")
    _asset(conn, "ZED")
    _asset(conn, "ALPHA")
    _hold(conn, "HELD")
    _portfolio_snapshot(conn, "HELD")
    for asset_id in ("ZED", "ALPHA"):
        _candidate_metrics(
            conn,
            asset_id,
            growth=60,
            value=60,
            quality=60,
            income=60,
            speculative=50,
        )
    pool = _pool(conn, ("ZED", 80), ("ALPHA", 80))

    result = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile("balanced", (60, 60, 60, 60, 50)),
        run_id=RUN_ID,
    )

    assert [review.asset_id for review in result.ordered_reviews] == ["ALPHA", "ZED"]


def test_high_raw_ranking_cannot_bypass_material_redundancy(conn) -> None:
    _asset(conn, "HELD_ETF", sector="Broad Market", country="US", asset_type="etf")
    _asset(conn, "REDUNDANT")
    _asset(conn, "CLEAN")
    _asset(conn, "OTHER")
    _hold(conn, "HELD_ETF")
    _portfolio_snapshot(conn, "HELD_ETF")
    conn.execute(
        """
        CREATE TABLE etf_holding(
            asset_id TEXT, holding_symbol TEXT, weight_pct DOUBLE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO etf_holding VALUES
            ('HELD_ETF', 'REDUNDANT', 60),
            ('HELD_ETF', 'OTHER', 40)
        """
    )
    for asset_id in ("REDUNDANT", "CLEAN"):
        _candidate_metrics(
            conn,
            asset_id,
            growth=60,
            value=60,
            quality=60,
            income=60,
            speculative=50,
        )
    pool = _pool(conn, ("REDUNDANT", 100), ("CLEAN", 60))

    result = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile("balanced", (60, 60, 60, 60, 50)),
        run_id=RUN_ID,
    )

    assert [review.asset_id for review in result.ordered_reviews] == ["CLEAN", "REDUNDANT"]
    redundant = result.ordered_reviews[1]
    assert redundant.redundancy_score.value == 60
    assert redundant.eligibility_state == "downgraded"


def test_missing_critical_metrics_block_instead_of_becoming_zero(conn) -> None:
    _asset(conn, "HELD", sector="Technology", country="CA")
    _asset(conn, "MISSING")
    _hold(conn, "HELD")
    _portfolio_snapshot(conn, "HELD")
    conn.execute(
        """
        INSERT INTO asset_business_classification(
            asset_id, sector, industry, template_code, classification_source,
            confidence, effective_from, created_at, updated_at
        )
        VALUES ('MISSING', 'Healthcare', 'Fixture', 'standard', 'fixture',
                0.9, DATE '2026-01-01', ?, ?)
        """,
        [UPDATED_AT, UPDATED_AT],
    )
    pool = _pool(conn, ("MISSING", 100))

    review = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile("balanced", (60, 60, 60, 60, 50)),
        run_id=RUN_ID,
    ).ordered_reviews[0]

    assert review.eligibility_state == "blocked"
    assert review.fit_score.value is None
    assert "metric.fit.factor_alignment" in {
        metric.metric_code for metric in review.missing_metrics
    }
    assert not review.highlights


def test_profile_portfolio_conflict_blocks_high_raw_ranking(conn) -> None:
    pool = _base_fixture(conn)

    reviews = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile(
            "balanced",
            (60, 60, 60, 60, 50),
            portfolio_id="2",
        ),
        run_id=RUN_ID,
    ).ordered_reviews

    assert all(review.eligibility_state == "blocked" for review in reviews)
    assert all(
        "guardrail.profile.portfolio_conflict" in review.reason_codes
        for review in reviews
    )


def test_absent_sentiment_is_surfaced_without_zero_highlight(conn) -> None:
    _asset(conn, "HELD", sector="Technology", country="CA")
    _asset(conn, "QUIET")
    _hold(conn, "HELD")
    _portfolio_snapshot(conn, "HELD")
    _candidate_metrics(
        conn,
        "QUIET",
        growth=60,
        value=60,
        quality=60,
        income=60,
        speculative=50,
    )
    conn.execute("DELETE FROM ticker_sentiment_daily WHERE asset_id = 'QUIET'")
    pool = _pool(conn, ("QUIET", 90))

    review = CandidateScoringEngine(conn).score(
        pool=pool,
        investor_profile=_profile("balanced", (60, 60, 60, 60, 50)),
        run_id=RUN_ID,
    ).ordered_reviews[0]

    assert review.eligibility_state == "eligible"
    assert "sentiment" not in {highlight.category for highlight in review.highlights}
    sentiment_missing = next(
        metric
        for metric in review.missing_metrics
        if metric.metric_code == "metric.highlight.sentiment"
    )
    assert sentiment_missing.criticality == "noncritical"
    assert sentiment_missing.guardrail_effect == "none"


@pytest.mark.parametrize(
    ("function", "low_input", "high_input"),
    [
        (value_score_from_margin, -0.25, 0.50),
        (growth_score_from_rate, -0.10, 0.30),
        (speculative_score_from_volatility, 0.10, 0.60),
    ],
)
def test_normalization_boundaries_are_bounded(function, low_input, high_input) -> None:
    assert function(low_input) == 0
    assert function(high_input) == 100


def test_diversification_effect_boundary_rewards_new_dimension_only() -> None:
    assert diversification_effect_score({"Technology": 1.0}, "Healthcare") == 100
    assert diversification_effect_score({"Technology": 1.0}, "Technology") == 0
