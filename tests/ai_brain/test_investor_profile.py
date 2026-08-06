from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dashboard.ai_brain import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    EvidenceRef,
    InvestorProfileEngine,
    InvestorProfileInput,
    ProfileHolding,
    StatedPreferences,
    WatchlistBehavior,
)


AS_OF = datetime(2026, 8, 5, 18, 30, tzinfo=timezone.utc)


def _evidence(code: str) -> EvidenceRef:
    payload_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    return EvidenceRef(
        evidence_id=f"evidence:{payload_hash}",
        source=f"fixture.{code}",
        source_schema_version="fixture.v1",
        as_of=AS_OF,
        payload_hash=payload_hash,
    )


def _holding(
    asset_id: str,
    weight: float,
    *,
    asset_class: str = "Stock",
    sector: str | None,
    geography: str | None,
    growth: float | None,
    value: float | None,
    quality: float | None,
    income: float | None,
    speculative: float | None,
    volatility: float | None,
    sector_exposure: dict[str, float] | None = None,
    geography_exposure: dict[str, float] | None = None,
    is_etf: bool = False,
    is_passive: bool = False,
    look_through_holding_count: int | None = None,
    market_cap_band: str | None = None,
    themes: tuple[str, ...] = (),
) -> ProfileHolding:
    return ProfileHolding(
        asset_id=asset_id,
        weight=weight,
        asset_class=asset_class,
        sector=sector,
        geography=geography,
        sector_exposure=sector_exposure or {},
        geography_exposure=geography_exposure or {},
        themes=themes,
        market_cap_band=market_cap_band,
        is_etf=is_etf,
        is_passive=is_passive,
        look_through_holding_count=look_through_holding_count,
        annualized_volatility=volatility,
        growth_score=growth,
        value_score=value,
        quality_score=quality,
        income_score=income,
        speculative_score=speculative,
        evidence_refs=(_evidence(asset_id),),
    )


def _profile_input(
    portfolio_id: str,
    holdings: tuple[ProfileHolding, ...],
    *,
    volatility: float | None,
    turnover: float | None,
) -> InvestorProfileInput:
    return InvestorProfileInput(
        portfolio_id=portfolio_id,
        as_of=AS_OF,
        domestic_country="CA",
        holdings=holdings,
        portfolio_volatility=volatility,
        turnover_rate=turnover,
        evidence_refs=(_evidence(f"{portfolio_id}.portfolio"),),
    )


def _factors(profile) -> dict[str, object]:
    return {item.code: item for item in profile.factor_scores}


@pytest.fixture
def concentrated_growth_input() -> InvestorProfileInput:
    return _profile_input(
        "concentrated-growth",
        (
            _holding(
                "NVDA",
                0.65,
                sector="Technology",
                geography="US",
                growth=94,
                value=25,
                quality=84,
                income=5,
                speculative=72,
                volatility=0.48,
                market_cap_band="mega",
                themes=("artificial-intelligence",),
            ),
            _holding(
                "MSFT",
                0.20,
                sector="Technology",
                geography="US",
                growth=82,
                value=40,
                quality=92,
                income=25,
                speculative=30,
                volatility=0.28,
                market_cap_band="mega",
                themes=("artificial-intelligence",),
            ),
            _holding(
                "CASH",
                0.15,
                asset_class="Cash",
                sector=None,
                geography="CA",
                growth=None,
                value=None,
                quality=None,
                income=None,
                speculative=None,
                volatility=0.0,
            ),
        ),
        volatility=0.34,
        turnover=1.1,
    )


@pytest.fixture
def dividend_income_input() -> InvestorProfileInput:
    holdings = tuple(
        _holding(
            asset_id,
            0.25,
            sector=sector,
            geography="CA",
            growth=38,
            value=78,
            quality=76,
            income=88,
            speculative=18,
            volatility=0.14,
            market_cap_band="large",
        )
        for asset_id, sector in (
            ("BMO", "Financial Services"),
            ("ENB", "Energy"),
            ("FTS", "Utilities"),
            ("T", "Communication Services"),
        )
    )
    return _profile_input("dividend-income", holdings, volatility=0.13, turnover=0.18)


@pytest.fixture
def broad_etf_input() -> InvestorProfileInput:
    return _profile_input(
        "broad-etf",
        (
            _holding(
                "VTI",
                0.45,
                asset_class="ETF",
                sector="Broad Market",
                geography="US",
                sector_exposure={"Technology": 0.30, "Other": 0.70},
                geography_exposure={"US": 0.98, "CA": 0.02},
                growth=58,
                value=55,
                quality=70,
                income=45,
                speculative=16,
                volatility=0.16,
                is_etf=True,
                is_passive=True,
                look_through_holding_count=3500,
            ),
            _holding(
                "VXUS",
                0.35,
                asset_class="ETF",
                sector="Broad Market",
                geography="INTL",
                sector_exposure={"Technology": 0.15, "Other": 0.85},
                geography_exposure={"CA": 0.08, "INTL": 0.92},
                growth=52,
                value=62,
                quality=64,
                income=55,
                speculative=18,
                volatility=0.17,
                is_etf=True,
                is_passive=True,
                look_through_holding_count=7000,
            ),
            _holding(
                "BND",
                0.20,
                asset_class="ETF",
                sector="Fixed Income",
                geography="US",
                sector_exposure={"Fixed Income": 1.0},
                geography_exposure={"US": 1.0},
                growth=40,
                value=55,
                quality=72,
                income=60,
                speculative=8,
                volatility=0.06,
                is_etf=True,
                is_passive=True,
                look_through_holding_count=10000,
            ),
        ),
        volatility=0.11,
        turnover=0.10,
    )


@pytest.fixture
def speculative_small_cap_input() -> InvestorProfileInput:
    holdings = tuple(
        _holding(
            asset_id,
            0.25,
            sector=sector,
            geography="US",
            growth=82,
            value=30,
            quality=38,
            income=2,
            speculative=92,
            volatility=0.58,
            market_cap_band="small",
            themes=(theme,),
        )
        for asset_id, sector, theme in (
            ("SPEC1", "Technology", "quantum"),
            ("SPEC2", "Healthcare", "biotech"),
            ("SPEC3", "Industrials", "space"),
            ("SPEC4", "Energy", "clean-energy"),
        )
    )
    return _profile_input("speculative-small-cap", holdings, volatility=0.52, turnover=2.2)


@pytest.fixture
def balanced_input() -> InvestorProfileInput:
    holdings = tuple(
        _holding(
            asset_id,
            0.25,
            asset_class=asset_class,
            sector=sector,
            geography=geography,
            growth=growth,
            value=value,
            quality=quality,
            income=income,
            speculative=25,
            volatility=volatility,
            is_etf=is_etf,
            is_passive=is_etf,
            look_through_holding_count=500 if is_etf else None,
        )
        for (
            asset_id,
            asset_class,
            sector,
            geography,
            growth,
            value,
            quality,
            income,
            volatility,
            is_etf,
        ) in (
            ("CAEQ", "Stock", "Financial Services", "CA", 55, 62, 68, 55, 0.18, False),
            ("USEQ", "Stock", "Technology", "US", 65, 50, 70, 40, 0.22, False),
            ("INTL", "ETF", "Broad Market", "INTL", 55, 65, 62, 50, 0.17, True),
            ("BOND", "ETF", "Fixed Income", "CA", 42, 58, 72, 62, 0.06, True),
        )
    )
    return _profile_input("balanced", holdings, volatility=0.17, turnover=0.40)


@pytest.fixture
def insufficient_data_input() -> InvestorProfileInput:
    holding = ProfileHolding(
        asset_id="UNKNOWN",
        weight=1.0,
        evidence_refs=(_evidence("UNKNOWN"),),
    )
    return _profile_input("insufficient", (holding,), volatility=None, turnover=None)


def test_concentrated_growth_portfolio(concentrated_growth_input: InvestorProfileInput) -> None:
    profile = InvestorProfileEngine().infer(concentrated_growth_input)
    factors = _factors(profile)

    assert "growth_oriented" in profile.archetype_labels
    assert "concentrated" in profile.archetype_labels
    assert factors["growth"].score >= 85
    assert profile.observed_risk_posture.label == "aggressive"
    assert profile.concentration_profile.label == "concentrated"
    assert profile.geography_tilt.label == "international"
    assert profile.sector_tilts[0].key == "Technology"
    assert profile.theme_tilts[0].key == "artificial-intelligence"


def test_dividend_income_portfolio(dividend_income_input: InvestorProfileInput) -> None:
    profile = InvestorProfileEngine().infer(dividend_income_input)
    factors = _factors(profile)

    assert {"income_focused", "value_oriented"} <= set(profile.archetype_labels)
    assert factors["income"].score >= 85
    assert factors["value"].score >= 75
    assert profile.observed_risk_posture.label in {"conservative", "moderate"}
    assert profile.geography_tilt.label == "domestic"


def test_broad_etf_heavy_portfolio(broad_etf_input: InvestorProfileInput) -> None:
    profile = InvestorProfileEngine().infer(broad_etf_input)

    assert "passive_allocator" in profile.archetype_labels
    assert profile.allocation_mix.passive_weight == pytest.approx(1.0)
    assert profile.concentration_profile.label == "diversified"
    assert profile.observed_risk_posture.label in {"conservative", "moderate"}


def test_speculative_small_cap_portfolio(
    speculative_small_cap_input: InvestorProfileInput,
) -> None:
    profile = InvestorProfileEngine().infer(speculative_small_cap_input)
    factors = _factors(profile)

    assert "speculative" in profile.archetype_labels
    assert "growth_oriented" in profile.archetype_labels
    assert factors["speculative"].score >= 90
    assert profile.observed_risk_posture.label == "aggressive"


def test_balanced_portfolio(balanced_input: InvestorProfileInput) -> None:
    profile = InvestorProfileEngine().infer(balanced_input)

    assert "balanced" in profile.archetype_labels
    assert profile.observed_risk_posture.label == "moderate"
    assert profile.concentration_profile.label != "concentrated"
    assert profile.sector_tilts == ()


def test_insufficient_data_portfolio_preserves_unknowns(
    insufficient_data_input: InvestorProfileInput,
) -> None:
    profile = InvestorProfileEngine().infer(insufficient_data_input)
    factors = _factors(profile)

    assert profile.archetype_labels == ("insufficient_data",)
    assert profile.confidence < 0.35
    assert profile.observed_risk_posture.label == "unknown"
    assert all(dimension.score is None for dimension in factors.values())
    assert "missing.factor.growth" in profile.data_gaps
    assert "missing.geography.classification" in profile.data_gaps
    assert "missing.asset_class.classification" in profile.data_gaps


def test_profile_is_deterministic_across_input_order(
    concentrated_growth_input: InvestorProfileInput,
) -> None:
    reversed_input = replace(
        concentrated_growth_input,
        holdings=tuple(
            replace(
                holding,
                themes=tuple(reversed(holding.themes)),
                evidence_refs=tuple(reversed(holding.evidence_refs)),
            )
            for holding in reversed(concentrated_growth_input.holdings)
        ),
        evidence_refs=tuple(reversed(concentrated_growth_input.evidence_refs)),
    )

    first = InvestorProfileEngine().infer(concentrated_growth_input)
    second = InvestorProfileEngine().infer(reversed_input)

    assert first.profile_id == second.profile_id
    assert first.input_snapshot_hash == second.input_snapshot_hash
    assert first == second


def test_profile_versions_evidence_and_suitability_boundary(
    balanced_input: InvestorProfileInput,
) -> None:
    stated = StatedPreferences(
        risk_tolerance="moderate",
        time_horizon_years=15,
        liquidity_need="low",
        objectives=("growth", "income"),
        evidence_refs=(_evidence("stated-preferences"),),
    )
    behavior = WatchlistBehavior(
        direct_stock_ratio=0.60,
        speculative_ratio=0.10,
        theme_weights={"quality": 0.4},
        evidence_refs=(_evidence("watchlist-behavior"),),
    )
    profile = InvestorProfileEngine().infer(
        replace(balanced_input, stated_preferences=stated, watchlist_behavior=behavior)
    )
    baseline = InvestorProfileEngine().infer(balanced_input)

    assert profile.schema_version == INVESTOR_PROFILE_SCHEMA_VERSION
    assert profile.methodology_version == INVESTOR_PROFILE_METHODOLOGY_VERSION
    assert profile.inference_scope == "observed_portfolio_behavior"
    assert profile.suitability_status == "stated_inputs_present_not_assessed"
    assert _evidence("stated-preferences").evidence_id in profile.evidence_refs
    assert _evidence("watchlist-behavior").evidence_id in profile.evidence_refs
    assert "optional.watchlist.behavior" not in profile.data_gaps
    assert "suitability.stated_inputs_missing" not in profile.data_gaps
    assert _factors(profile)["speculative"].score != _factors(baseline)["speculative"].score


def test_stale_evidence_reduces_confidence_and_is_surfaced(
    balanced_input: InvestorProfileInput,
) -> None:
    first = balanced_input.holdings[0]
    stale_ref = replace(first.evidence_refs[0], status="stale")
    stale_input = replace(
        balanced_input,
        holdings=(replace(first, evidence_refs=(stale_ref,)), *balanced_input.holdings[1:]),
    )

    current_profile = InvestorProfileEngine().infer(balanced_input)
    stale_profile = InvestorProfileEngine().infer(stale_input)

    assert stale_profile.confidence < current_profile.confidence
    assert "evidence.stale" in stale_profile.data_gaps


def test_profile_rejects_future_dated_evidence(
    balanced_input: InvestorProfileInput,
) -> None:
    future_ref = replace(
        balanced_input.evidence_refs[0],
        as_of=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="newer than profile"):
        replace(balanced_input, evidence_refs=(future_ref,))


def test_profile_input_rejects_invalid_weights_and_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        InvestorProfileInput(
            portfolio_id="bad-time",
            as_of=datetime(2026, 8, 5),
            domestic_country="CA",
            holdings=(),
        )

    with pytest.raises(ValueError, match="cannot exceed"):
        InvestorProfileInput(
            portfolio_id="bad-weights",
            as_of=AS_OF,
            domestic_country="CA",
            holdings=(
                ProfileHolding(asset_id="A", weight=0.6, evidence_refs=(_evidence("A"),)),
                ProfileHolding(asset_id="B", weight=0.5, evidence_refs=(_evidence("B"),)),
            ),
        )
