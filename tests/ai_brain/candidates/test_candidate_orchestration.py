from __future__ import annotations

import hashlib
import json
import socket
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from dashboard.ai_brain.candidates import (
    CANDIDATE_SOURCE_FAMILIES,
    CandidateInputCompatibilityError,
    CandidateRunRequest,
    CandidateRunService,
    OutsideHoldingUniverseBuilder,
    canonical_json,
)
from dashboard.ai_brain.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    AllocationMix,
    ExposureTilt,
    InvestorProfile,
    ProfileDimension,
)
from dashboard.analytics.persistence import AnalyticsStorageService
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
SNAPSHOT_DATE = date(2026, 8, 7)
UPDATED_AT = datetime(2026, 8, 7, 12)
CREATED_AT = datetime(2026, 8, 8, 13, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-orchestration.db")
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


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _profile() -> InvestorProfile:
    profile_hash = _hash("phase-5.7-profile")
    factors = tuple(
        ProfileDimension(
            code=code,
            score=score,
            label="observed",
            confidence=0.9,
            evidence_refs=(f"evidence:profile:{code}",),
        )
        for code, score in (
            ("growth", 65.0),
            ("value", 60.0),
            ("quality", 75.0),
            ("income", 45.0),
            ("speculative", 40.0),
        )
    )
    observed = ProfileDimension(
        code="observed_risk_posture",
        score=55,
        label="moderate",
        confidence=0.9,
        evidence_refs=("evidence:profile:risk",),
    )
    return InvestorProfile(
        profile_id=f"profile:{profile_hash}",
        portfolio_id="1",
        as_of=AS_OF,
        schema_version=INVESTOR_PROFILE_SCHEMA_VERSION,
        methodology_version=INVESTOR_PROFILE_METHODOLOGY_VERSION,
        input_snapshot_hash=profile_hash,
        inference_scope="observed_portfolio_behavior",
        suitability_status="not_assessed_missing_stated_inputs",
        archetype_labels=("balanced",),
        factor_scores=factors,
        observed_risk_posture=observed,
        concentration_profile=ProfileDimension(
            code="concentration_profile",
            score=85,
            label="concentrated",
            confidence=0.9,
            evidence_refs=("evidence:profile:concentration",),
        ),
        geography_tilt=ProfileDimension(
            code="domestic_international_tilt",
            score=80,
            label="domestic_tilt",
            confidence=0.9,
            evidence_refs=("evidence:profile:geography",),
        ),
        sector_tilts=(),
        theme_tilts=(
            ExposureTilt(
                dimension="theme",
                key="artificial-intelligence",
                weight=0.2,
                label="theme_tilt",
                confidence=0.9,
                evidence_refs=("evidence:profile:theme",),
            ),
        ),
        allocation_mix=AllocationMix(
            etf_weight=0.2,
            passive_weight=0.2,
            direct_stock_weight=0.8,
            classified_weight=1.0,
            label="stock_picker",
            confidence=0.9,
            evidence_refs=("evidence:profile:allocation",),
        ),
        confidence=0.9,
        evidence_refs=("evidence:profile",),
        data_gaps=(),
    )


def _request(profile: InvestorProfile | None = None) -> CandidateRunRequest:
    return CandidateRunRequest(
        portfolio_id=1,
        as_of=AS_OF,
        investor_profile=profile or _profile(),
        ranking_limit=100,
        search_terms=("alpha",),
        benchmark_index_ids=("CORE",),
        comparison_benchmark_index_id="CORE",
    )


def _asset(
    conn,
    asset_id: str,
    *,
    sector: str,
    country: str,
    industry: str = "Software",
) -> None:
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, ccy, name, sector, industry, country,
            created_at, updated_at
        )
        VALUES (?, ?, 'stock', 'USD', ?, ?, ?, ?, ?, ?)
        """,
        [
            asset_id,
            asset_id,
            f"{asset_id} Alpha Research",
            sector,
            industry,
            country,
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
        VALUES (?, ?, ?, 'standard', 'fixture', 0.9, '2026-01-01', ?, ?)
        """,
        [asset_id, sector, industry, UPDATED_AT, UPDATED_AT],
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


def _portfolio_snapshot(conn) -> None:
    payload = json.dumps(
        {
            "positions": [{"asset_id": "SEED", "weight": 1.0}],
            "risk_decomposition": {
                "sector_exposure": {"Technology": 1.0},
                "country_exposure": {"CA": 1.0},
            },
        }
    )
    conn.execute(
        """
        INSERT INTO portfolio_analytics_snapshot(
            portfolio_id, snapshot_date, position_count, state_signature,
            payload_json, refreshed_at
        )
        VALUES (1, ?, 1, 'phase-5.7', ?, ?)
        """,
        [SNAPSHOT_DATE, payload, UPDATED_AT],
    )


def _benchmark(
    conn,
    index_id: str,
    *,
    category: str,
    constituents: tuple[tuple[str, float], ...],
    exposures: dict[str, dict[str, float]] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO benchmark_index(
            index_id, index_name, index_family, index_category, currency,
            created_at, updated_at
        )
        VALUES (?, ?, 'fixture', ?, 'USD', ?, ?)
        """,
        [index_id, index_id, category, UPDATED_AT, UPDATED_AT],
    )
    conn.execute(
        """
        INSERT INTO benchmark_index_composition_snapshot(
            index_id, snapshot_date, source, source_type, is_proxy,
            constituent_count, data_quality, fetched_at
        )
        VALUES (?, ?, 'fixture', 'factsheet', FALSE, ?, 'exact', ?)
        """,
        [index_id, SNAPSHOT_DATE, len(constituents), UPDATED_AT],
    )
    for symbol, weight in constituents:
        conn.execute(
            """
            INSERT INTO benchmark_index_constituent(
                index_id, snapshot_date, source, constituent_symbol,
                weight_pct, is_proxy
            )
            VALUES (?, ?, 'fixture', ?, ?, FALSE)
            """,
            [index_id, SNAPSHOT_DATE, symbol, weight],
        )
    for dimension, values in (exposures or {}).items():
        for label, weight in values.items():
            conn.execute(
                """
                INSERT INTO benchmark_index_exposure_snapshot(
                    index_id, snapshot_date, dimension_type, dimension_value,
                    weight_pct, source, source_type, is_proxy, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, 'fixture', 'factsheet', FALSE, ?)
                """,
                [index_id, SNAPSHOT_DATE, dimension, label, weight, UPDATED_AT],
            )


def _ranking(conn, asset_id: str, score: float) -> None:
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
    quote_volume: float | None,
) -> None:
    conn.execute(
        """
        INSERT INTO ticker_factor_snapshot(
            asset_id, ticker, snapshot_date, growth_score, value_score,
            quality_score, momentum_score, dividend_score, volatility_score,
            overall_factor_score, factor_labels_json, explanation,
            created_at, updated_at
        )
        VALUES (?, ?, ?, 65, 60, 80, 80, 45, 60, 70, '[]', 'fixture', ?, ?)
        """,
        [asset_id, asset_id, SNAPSHOT_DATE, UPDATED_AT, UPDATED_AT],
    )
    conn.execute(
        """
        INSERT INTO business_strength_analysis_run(
            id, asset_id, methodology_id, template_id, analysis_date,
            source_data_as_of, overall_score, classification, confidence_score,
            completeness_score, status, created_at, updated_at
        )
        VALUES (
            nextval('seq_business_strength_analysis_run_id'), ?, 1, 1, ?, ?, 80,
            'Strong', 90, 90, 'complete', ?, ?
        )
        """,
        [asset_id, SNAPSHOT_DATE, UPDATED_AT, UPDATED_AT, UPDATED_AT],
    )
    analytics = json.dumps(
        {
            "discounted_cash_flow": {"margin_of_safety": 0.5},
            "dividend_discount": {"margin_of_safety": 0.5},
            "valuation_depth": {
                "revenue_growth_yoy": 0.2,
                "eps_growth_yoy": 0.2,
                "free_cash_flow_growth_yoy": 0.2,
            },
            "risk": {"annualized_volatility": 0.25},
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
        VALUES (?, ?, ?, 0.2, 0.2, 0.2, 10, 4, ?, ?)
        """,
        [asset_id, asset_id, SNAPSHOT_DATE, UPDATED_AT, UPDATED_AT],
    )
    if quote_volume is not None:
        conn.executemany(
            """
            INSERT INTO asset_quote_daily(
                asset_id, date, open, high, low, close, adj_close, volume,
                ing_source, ing_at
            )
            VALUES (?, ?, 100, 101, 99, 100, 100, ?, 'fixture', ?)
            """,
            [
                [
                    asset_id,
                    AS_OF.date() - timedelta(days=offset),
                    quote_volume,
                    UPDATED_AT,
                ]
                for offset in range(1, 21)
            ],
        )


def _peer_group(conn) -> None:
    conn.execute(
        """
        INSERT INTO business_strength_peer_group(
            id, name, template_code, definition_json, created_at, updated_at
        )
        VALUES (1, 'Software peers', 'standard', '{"kind":"software"}', ?, ?)
        """,
        [UPDATED_AT, UPDATED_AT],
    )
    for asset_id in ("SEED", "ALPHA"):
        conn.execute(
            """
            INSERT INTO business_strength_peer_member(
                peer_group_id, asset_id, effective_from
            )
            VALUES (1, ?, '2026-01-01')
            """,
            [asset_id],
        )


def _seed_full_fixture(conn) -> None:
    _asset(conn, "SEED", sector="Technology", country="CA")
    _asset(conn, "ALPHA", sector="Healthcare", country="US")
    _asset(conn, "LOWLIQ", sector="Healthcare", country="US")
    _asset(conn, "NOPRICE", sector="Healthcare", country="US")
    _hold(conn, "SEED")
    _portfolio_snapshot(conn)
    _benchmark(
        conn,
        "CORE",
        category="core_geo",
        constituents=(("ALPHA", 5),),
        exposures={
            "sector": {"Technology": 40, "Healthcare": 60},
            "country": {"CA": 40, "US": 60},
        },
    )
    _benchmark(
        conn,
        "THEME_AI",
        category="theme",
        constituents=(("ALPHA", 5),),
    )
    _peer_group(conn)
    for asset_id, score, quote_volume in (
        ("ALPHA", 95, 100_000),
        ("LOWLIQ", 85, 5_000),
        ("NOPRICE", 75, None),
    ):
        _ranking(conn, asset_id, score)
        _candidate_metrics(conn, asset_id, quote_volume=quote_volume)
    conn.execute(
        """
        INSERT INTO watchlist_ticker(
            asset_id, is_active, source, created_at, updated_at
        )
        VALUES ('ALPHA', TRUE, 'manual', ?, ?)
        """,
        [UPDATED_AT, UPDATED_AT],
    )


def _service(conn) -> CandidateRunService:
    return CandidateRunService(conn, clock=lambda: CREATED_AT)


def test_end_to_end_run_exercises_every_source_and_eligibility_state(conn) -> None:
    _seed_full_fixture(conn)

    run = _service(conn).execute(_request(), request_id="phase-5.7-e2e")

    source_families = {
        match.source_family
        for review in run.candidate_reviews
        for match in review.source_matches
    }
    assert source_families == CANDIDATE_SOURCE_FAMILIES
    assert {review.eligibility_state for review in run.candidate_reviews} == {
        "blocked",
        "downgraded",
        "eligible",
    }
    assert run.run_status == "partial"
    assert run.eligible_count >= 1
    assert run.downgraded_count >= 1
    assert run.blocked_count >= 1
    assert "asset_quote_daily" in run.missing_dependencies
    assert run.methodology_version.startswith("candidate-engine.deterministic.")
    assert len(run.source_watermarks) == len(CANDIDATE_SOURCE_FAMILIES)
    assert run.output_hash_is_valid


def test_identical_inputs_replay_exactly_and_changed_evidence_creates_a_run(conn) -> None:
    _seed_full_fixture(conn)
    service = _service(conn)
    request = _request()

    first = service.execute(request, request_id="original")
    replay = service.execute(request, request_id="retry")

    assert replay == first
    assert canonical_json(replay) == canonical_json(first)
    assert conn.execute("SELECT COUNT(*) FROM candidate_run").fetchone()[0] == 1

    conn.execute(
        """
        UPDATE stock_ranking_snapshot
        SET score = 96
        WHERE asset_id = 'ALPHA'
          AND factor = 'aggregate'
          AND snapshot_date = ?
          AND universe = 'all'
        """,
        [SNAPSHOT_DATE],
    )
    changed = service.execute(request, request_id="changed-evidence")

    assert changed.run_id != first.run_id
    assert changed.input_snapshot_hash != first.input_snapshot_hash
    assert conn.execute("SELECT COUNT(*) FROM candidate_run").fetchone()[0] == 2


def test_source_schema_incompatibility_fails_before_scoring_or_persistence(conn) -> None:
    _seed_full_fixture(conn)
    request = _request()
    pool = OutsideHoldingUniverseBuilder(conn).build(
        portfolio_id=request.portfolio_id,
        as_of=request.as_of,
        ranking_factor=request.ranking_factor,
        ranking_universe=request.ranking_universe,
        ranking_limit=request.ranking_limit,
        search_terms=request.search_terms,
        benchmark_index_ids=request.benchmark_index_ids,
        comparison_benchmark_index_id=request.comparison_benchmark_index_id,
        investor_profile=request.investor_profile,
    )
    incompatible = replace(
        pool,
        source_watermarks=(
            replace(pool.source_watermarks[0], source_schema_version="unsupported.v9"),
            *pool.source_watermarks[1:],
        ),
    )

    class FrozenBuilder:
        def build(self, **_kwargs):
            return incompatible

    class NeverScore:
        called = False

        def score(self, **_kwargs):
            self.called = True
            raise AssertionError("scoring must not run for incompatible inputs")

    scorer = NeverScore()
    service = CandidateRunService(
        conn,
        universe_builder=FrozenBuilder(),
        scoring_engine=scorer,
        clock=lambda: CREATED_AT,
    )

    with pytest.raises(CandidateInputCompatibilityError) as error:
        service.execute(request)

    assert error.value.failure.reason_code == "candidate.input.version_incompatible"
    assert error.value.failure.expected is not None
    assert error.value.failure.actual == "unsupported.v9"
    assert scorer.called is False
    assert conn.execute("SELECT COUNT(*) FROM candidate_run").fetchone()[0] == 0


def test_orchestration_does_not_invoke_network_provider_clients(conn, monkeypatch) -> None:
    _seed_full_fixture(conn)

    def reject_network(*_args, **_kwargs):
        raise AssertionError("candidate orchestration attempted a provider call")

    monkeypatch.setattr(socket.socket, "connect", reject_network)

    run = _service(conn).execute(_request())

    assert run.candidate_reviews


class _CountingConnection:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.query_count = 0

    def execute(self, *args, **kwargs):
        self.query_count += 1
        return self.conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def test_representative_all_universe_run_stays_within_measured_budgets(conn) -> None:
    _seed_full_fixture(conn)
    counted = _CountingConnection(conn)

    run = CandidateRunService(counted, clock=lambda: CREATED_AT).execute(_request())

    assert counted.query_count <= 300
    assert run.runtime_ms is not None
    assert run.runtime_ms < 5_000
