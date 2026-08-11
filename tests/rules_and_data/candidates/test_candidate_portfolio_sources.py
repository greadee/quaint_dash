from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from dashboard.rules_and_data.candidates import (
    CandidatePortfolioSourceAdapters,
    OutsideHoldingUniverseBuilder,
)
from dashboard.rules_and_data.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    AllocationMix,
    ExposureTilt,
    InvestorProfile,
    ProfileDimension,
)
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
UPDATED_AT = datetime(2026, 8, 5, 12, 0)
SNAPSHOT_DATE = date(2026, 8, 5)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-portfolio-sources.db")
    init_db(db)
    db.conn.execute(
        "INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Primary')"
    )
    db.conn.execute(
        "INSERT INTO import_batch(batch_id, batch_type) VALUES (1, 'manual-entry')"
    )
    yield db.conn
    db.conn.close()


def _profile(
    *,
    portfolio_id: str = "1",
    concentration: str = "concentrated",
    confidence: float = 0.9,
    data_gaps: tuple[str, ...] = (),
    themes: tuple[ExposureTilt, ...] = (),
) -> InvestorProfile:
    dimension = ProfileDimension(
        code="observed",
        score=75,
        label="observed",
        confidence=confidence,
        evidence_refs=("evidence:profile",),
    )
    return InvestorProfile(
        profile_id=f"profile:{'1' * 64}",
        portfolio_id=portfolio_id,
        as_of=AS_OF,
        schema_version=INVESTOR_PROFILE_SCHEMA_VERSION,
        methodology_version=INVESTOR_PROFILE_METHODOLOGY_VERSION,
        input_snapshot_hash="2" * 64,
        inference_scope="observed_portfolio_behavior",
        suitability_status="not_assessed_missing_stated_inputs",
        archetype_labels=("concentrated",) if concentration == "concentrated" else ("balanced",),
        factor_scores=(dimension,),
        observed_risk_posture=dimension,
        concentration_profile=ProfileDimension(
            code="concentration_profile",
            score=80 if concentration == "concentrated" else 20,
            label=concentration,
            confidence=confidence,
            evidence_refs=("evidence:concentration",),
        ),
        geography_tilt=ProfileDimension(
            code="domestic_international_tilt",
            score=60,
            label="mixed",
            confidence=confidence,
            evidence_refs=("evidence:geography",),
        ),
        sector_tilts=(),
        theme_tilts=themes,
        allocation_mix=AllocationMix(
            etf_weight=0.2,
            passive_weight=0.2,
            direct_stock_weight=0.8,
            classified_weight=1.0,
            label="stock_picker",
            confidence=confidence,
            evidence_refs=("evidence:allocation",),
        ),
        confidence=confidence,
        evidence_refs=("evidence:profile",),
        data_gaps=data_gaps,
    )


def _asset(
    conn,
    asset_id: str,
    *,
    sector: str | None = None,
    industry: str | None = None,
    country: str | None = None,
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
            asset_id,
            sector,
            industry,
            country,
            UPDATED_AT,
            UPDATED_AT,
        ],
    )


def _hold(conn, asset_id: str) -> None:
    conn.execute(
        """
        INSERT INTO txn(
            portfolio_id, time_stamp, txn_type, asset_id, qty, price,
            ccy, cash_amt, batch_id
        )
        VALUES (1, ?, 'buy', ?, 1, 10, 'USD', -10, 1)
        """,
        [UPDATED_AT, asset_id],
    )


def _portfolio_snapshot(
    conn,
    *,
    sectors: dict[str, float],
    countries: dict[str, float],
) -> None:
    payload = json.dumps(
        {
            "risk_decomposition": {
                "sector_exposure": sectors,
                "country_exposure": countries,
            }
        }
    )
    conn.execute(
        """
        INSERT INTO portfolio_analytics_snapshot(
            portfolio_id, snapshot_date, position_count, state_signature,
            payload_json, refreshed_at
        )
        VALUES (1, ?, 4, 'fixture', ?, ?)
        """,
        [SNAPSHOT_DATE, payload, UPDATED_AT],
    )


def _benchmark(
    conn,
    index_id: str,
    *,
    category: str = "core_geo",
    exposures: dict[str, dict[str, float]] | None = None,
    constituents: tuple[tuple[str, float], ...] = (),
    is_proxy: bool = False,
) -> None:
    conn.execute(
        """
        INSERT INTO benchmark_index(
            index_id, index_name, index_family, index_category, currency,
            created_at, updated_at
        )
        VALUES (?, ?, 'test', ?, 'USD', ?, ?)
        """,
        [index_id, index_id, category, UPDATED_AT, UPDATED_AT],
    )
    for dimension, values in (exposures or {}).items():
        for label, weight in values.items():
            conn.execute(
                """
                INSERT INTO benchmark_index_exposure_snapshot(
                    index_id, snapshot_date, dimension_type, dimension_value,
                    weight_pct, source, source_type, is_proxy, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, 'test', ?, ?, ?)
                """,
                [
                    index_id,
                    SNAPSHOT_DATE,
                    dimension,
                    label,
                    weight,
                    "etf_proxy" if is_proxy else "factsheet",
                    is_proxy,
                    UPDATED_AT,
                ],
            )
    if constituents:
        conn.execute(
            """
            INSERT INTO benchmark_index_composition_snapshot(
                index_id, snapshot_date, source, source_type, is_proxy,
                constituent_count, data_quality, fetched_at
            )
            VALUES (?, ?, 'test', 'etf_proxy', ?, ?, 'proxy', ?)
            """,
            [index_id, SNAPSHOT_DATE, is_proxy, len(constituents), UPDATED_AT],
        )
        for symbol, weight in constituents:
            conn.execute(
                """
                INSERT INTO benchmark_index_constituent(
                    index_id, snapshot_date, source, constituent_symbol,
                    weight_pct, is_proxy
                )
                VALUES (?, ?, 'test', ?, ?, ?)
                """,
                [index_id, SNAPSHOT_DATE, symbol, weight, is_proxy],
            )


def _classification(
    conn,
    asset_id: str,
    *,
    sector: str,
    industry: str,
    confidence: float = 0.9,
) -> None:
    conn.execute(
        """
        INSERT INTO asset_business_classification(
            asset_id, sector, industry, template_code, classification_source,
            confidence, effective_from, created_at, updated_at
        )
        VALUES (?, ?, ?, 'standard', 'fixture', ?, '2026-01-01', ?, ?)
        """,
        [asset_id, sector, industry, confidence, UPDATED_AT, UPDATED_AT],
    )


def test_concentrated_sector_and_geography_gaps_nominate_classified_assets(conn) -> None:
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 0.8, "Unknown": 0.2},
        countries={"CA": 0.9, "US": 0.1},
    )
    _benchmark(
        conn,
        "CORE",
        exposures={
            "sector": {"Technology": 30, "Healthcare": 30, "Financials": 40},
            "country": {"CA": 40, "US": 60},
        },
    )
    _asset(conn, "HEALTH", sector="Healthcare", country="US")
    _asset(conn, "BANK", sector="Financials", country="US")
    _asset(conn, "MYSTERY", sector="Unknown", country="Unknown")
    adapters = CandidatePortfolioSourceAdapters(conn)

    sector = adapters.sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="CORE",
        investor_profile=_profile(),
    )
    geography = adapters.geography_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="CORE",
        investor_profile=_profile(),
    )

    assert [item.source_asset_id for item in sector.nominations] == ["BANK", "HEALTH"]
    assert [item.source_asset_id for item in geography.nominations] == ["BANK", "HEALTH"]
    assert all(item.source_match.evidence_refs for item in sector.nominations)
    assert {item.source_match.reason_code for item in sector.nominations} == {
        "source.sector_gap.underweight"
    }


def test_balanced_portfolio_does_not_receive_artificial_gap_candidates(conn) -> None:
    balanced = {
        "Technology": 0.25,
        "Healthcare": 0.25,
        "Financials": 0.25,
        "Industrials": 0.25,
    }
    _portfolio_snapshot(conn, sectors=balanced, countries={"CA": 0.5, "US": 0.5})
    _benchmark(
        conn,
        "BALANCED",
        exposures={
            "sector": {key: value * 100 for key, value in balanced.items()},
            "country": {"CA": 50, "US": 50},
        },
    )
    _asset(conn, "HEALTH", sector="Healthcare", country="US")

    result = CandidatePortfolioSourceAdapters(conn).sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="BALANCED",
        investor_profile=_profile(concentration="diversified"),
    )

    assert result.nominations == ()
    assert result.blocked_nominations == ()
    assert result.limitations == ("source.sector_gap.no_material_gap",)


def test_unknown_and_incomplete_classifications_do_not_become_positive_gaps(conn) -> None:
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 0.2, "Unknown": 0.8},
        countries={"CA": 1.0},
    )
    _benchmark(
        conn,
        "INCOMPLETE",
        exposures={"sector": {"Unknown": 100}},
    )
    _asset(conn, "MYSTERY", sector="Unknown")

    result = CandidatePortfolioSourceAdapters(conn).sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="INCOMPLETE",
        investor_profile=_profile(),
    )

    assert result.nominations == ()
    assert "source.gap.portfolio_classification_incomplete" in result.limitations
    assert "source.gap.benchmark_classification_incomplete" in result.limitations


def test_profile_coverage_conflict_blocks_gap_reason_with_evidence(conn) -> None:
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 1.0},
        countries={"CA": 1.0},
    )
    _benchmark(
        conn,
        "CORE",
        exposures={"sector": {"Technology": 40, "Healthcare": 60}},
    )
    _asset(conn, "HEALTH", sector="Healthcare")

    result = CandidatePortfolioSourceAdapters(conn).sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="CORE",
        investor_profile=_profile(data_gaps=("missing.sector.classification",)),
    )

    assert result.nominations == ()
    assert len(result.blocked_nominations) == 1
    blocked = result.blocked_nominations[0]
    assert blocked.reason_code == "guardrail.profile.sector_coverage_conflict"
    assert blocked.source_match.reason_code == "source.sector_gap.underweight"
    assert len(blocked.source_match.evidence_refs) == 3


def test_profile_portfolio_mismatch_blocks_gap_source(conn) -> None:
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 1.0},
        countries={"CA": 1.0},
    )
    _benchmark(
        conn,
        "CORE",
        exposures={"sector": {"Technology": 40, "Healthcare": 60}},
    )
    _asset(conn, "HEALTH", sector="Healthcare")

    result = CandidatePortfolioSourceAdapters(conn).sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="CORE",
        investor_profile=_profile(portfolio_id="2"),
    )

    assert result.nominations == ()
    assert [item.reason_code for item in result.blocked_nominations] == [
        "guardrail.profile.portfolio_conflict"
    ]


def test_invalid_exposure_totals_fail_closed(conn) -> None:
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 1.0},
        countries={"CA": 1.0},
    )
    _benchmark(
        conn,
        "OVERWEIGHT",
        exposures={"sector": {"Technology": 80, "Healthcare": 70}},
    )
    _asset(conn, "HEALTH", sector="Healthcare")

    result = CandidatePortfolioSourceAdapters(conn).sector_gaps(
        portfolio_id=1,
        as_of=AS_OF,
        benchmark_index_id="OVERWEIGHT",
        investor_profile=_profile(),
    )

    assert result.nominations == ()
    assert "source.gap.benchmark_total_invalid" in result.limitations


def test_peer_and_industry_associations_are_effective_dated_and_deterministic(conn) -> None:
    for asset_id in ("SEED", "ZED", "ALPHA"):
        _asset(conn, asset_id, sector="Technology", industry="Software")
        _classification(
            conn,
            asset_id,
            sector="Technology",
            industry="Software",
            confidence=0.8 if asset_id == "ZED" else 0.9,
        )
    conn.execute(
        """
        INSERT INTO business_strength_peer_group(
            id, name, template_code, definition_json, created_at, updated_at
        )
        VALUES (1, 'Software peers', 'standard', '{"kind":"software"}', ?, ?)
        """,
        [UPDATED_AT, UPDATED_AT],
    )
    for asset_id in ("ZED", "SEED", "ALPHA"):
        conn.execute(
            """
            INSERT INTO business_strength_peer_member(
                peer_group_id, asset_id, effective_from
            )
            VALUES (1, ?, '2026-01-01')
            """,
            [asset_id],
        )
    adapters = CandidatePortfolioSourceAdapters(conn)

    peer = adapters.peer_associations(as_of=AS_OF, seed_asset_ids=("SEED",))
    industry = adapters.industry_associations(
        as_of=AS_OF,
        seed_asset_ids=("SEED",),
    )

    assert [item.source_asset_id for item in peer.nominations] == ["ALPHA", "ZED"]
    assert [item.source_asset_id for item in industry.nominations] == ["ALPHA", "ZED"]
    assert all(item.source_match.evidence_refs for item in peer.nominations)
    assert all(item.source_match.evidence_refs for item in industry.nominations)


def test_profile_theme_requires_versioned_profile_and_benchmark_evidence(conn) -> None:
    _benchmark(
        conn,
        "THEME_AI",
        category="theme",
        constituents=(("ZED", 4), ("ALPHA", 6)),
        is_proxy=True,
    )
    profile = _profile(
        themes=(
            ExposureTilt(
                dimension="theme",
                key="artificial-intelligence",
                weight=0.2,
                label="theme_tilt",
                confidence=0.9,
                evidence_refs=("evidence:theme",),
            ),
        )
    )

    result = CandidatePortfolioSourceAdapters(conn).profile_themes(
        as_of=AS_OF,
        investor_profile=profile,
    )

    assert [item.source_asset_id for item in result.nominations] == ["ALPHA", "ZED"]
    assert {item.source_match.reason_code for item in result.nominations} == {
        "source.theme.profile_consistent"
    }
    assert all(len(item.source_match.evidence_refs) == 2 for item in result.nominations)
    assert "source.theme.proxy_composition" in result.limitations


def test_pool_merges_gap_and_association_sources_and_excludes_held_seed(conn) -> None:
    _asset(conn, "SEED", sector="Technology", industry="Software", country="CA")
    _asset(conn, "CANDIDATE", sector="Healthcare", industry="Software", country="US")
    _hold(conn, "SEED")
    _classification(conn, "SEED", sector="Technology", industry="Software")
    _classification(conn, "CANDIDATE", sector="Healthcare", industry="Software")
    _portfolio_snapshot(
        conn,
        sectors={"Technology": 1.0},
        countries={"CA": 1.0},
    )
    _benchmark(
        conn,
        "CORE",
        exposures={
            "sector": {"Technology": 40, "Healthcare": 60},
            "country": {"CA": 40, "US": 60},
        },
    )

    result = OutsideHoldingUniverseBuilder(conn).build(
        portfolio_id=1,
        as_of=AS_OF,
        comparison_benchmark_index_id="CORE",
        investor_profile=_profile(),
    )

    candidate = next(item for item in result.candidates if item.asset_id == "CANDIDATE")
    assert {match.source_family for match in candidate.source_matches} == {
        "geography_gap",
        "industry",
        "sector_gap",
    }
    assert all(item.asset_id != "SEED" for item in result.candidates)
