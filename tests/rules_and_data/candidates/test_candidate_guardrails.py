from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dashboard.rules_and_data.candidates import (
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CandidateGuardrailPolicy,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidateReview,
    CandidateScore,
    CandidateScoreComponent,
    CandidateSourceMatch,
    candidate_id,
    candidate_review_id,
    candidate_review_sort_key,
    candidate_run_id,
    canonical_json,
    freshness_policy_for_domain,
)
from dashboard.rules_and_data.candidates.source_adapters import candidate_source_evidence
from dashboard.db.db_conn import DB, init_db

AS_OF = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
RUN_ID = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, "a" * 64)


@pytest.fixture
def conn(tmp_path):
    db = DB(tmp_path / "candidate-guardrails.db")
    init_db(db)
    db.conn.execute("INSERT INTO portfolio(portfolio_id, portfolio_name) VALUES (1, 'Primary')")
    yield db.conn
    db.conn.close()


def _evidence(
    asset_id: str,
    *,
    domain: str,
    age_days: int,
    suffix: str,
):
    as_of = AS_OF - timedelta(days=age_days)
    return candidate_source_evidence(
        source_domain=domain,
        source_schema_version=f"{domain}.fixture.v1",
        source_record_id=f"{suffix}:{asset_id}:{as_of.date().isoformat()}",
        as_of=as_of,
        payload={"asset_id": asset_id, "suffix": suffix, "as_of": as_of},
    )


def _score(score_type: str, value: Decimal, evidence) -> CandidateScore:
    component = CandidateScoreComponent(
        component_code=f"score.{score_type}.fixture",
        value=value,
        weight=Decimal("1"),
        contribution=value,
        reason_codes=(f"score.{score_type}.fixture",),
        evidence_refs=(evidence,),
    )
    return CandidateScore(
        score_type=score_type,
        value=value,
        components=(component,),
        evidence_refs=(evidence,),
    )


def _direction(value: Decimal, *, inverse: bool = False) -> str:
    if value >= 65:
        return "negative" if inverse else "positive"
    if value <= 35:
        return "positive" if inverse else "negative"
    return "neutral"


def _review(
    asset_id: str,
    *,
    source_domain: str = "stock-ranking",
    source_age: int = 1,
    fit: Decimal = Decimal("80"),
    diversification: Decimal = Decimal("80"),
    redundancy: Decimal = Decimal("0"),
    risk: Decimal | None = Decimal("50"),
    risk_age: int = 1,
    risk_domain: str = "asset-analytics-scoring",
    stale_positive: bool = False,
    classification_missing: bool = False,
) -> CandidateReview:
    source = _evidence(
        asset_id,
        domain=source_domain,
        age_days=source_age,
        suffix="source",
    )
    overlap = _evidence(
        asset_id,
        domain="candidate-economic-overlap",
        age_days=0,
        suffix="overlap",
    )
    risk_evidence = (
        _evidence(
            asset_id,
            domain=risk_domain,
            age_days=risk_age,
            suffix="risk",
        )
        if risk is not None
        else None
    )
    highlights = []
    if risk is not None and risk_evidence is not None:
        highlights.append(
            CandidateHighlight(
                category="risk",
                highlight_code="highlight.risk.fixture",
                normalized_value=risk,
                unit="score_0_100",
                direction=_direction(risk, inverse=True),
                as_of=risk_evidence.as_of,
                evidence_refs=(risk_evidence,),
            )
        )
    if stale_positive:
        positive_evidence = _evidence(
            asset_id,
            domain="ticker-factor",
            age_days=46,
            suffix="stale-positive",
        )
        highlights.append(
            CandidateHighlight(
                category="momentum",
                highlight_code="highlight.momentum.fixture",
                normalized_value=Decimal("80"),
                unit="score_0_100",
                direction="positive",
                as_of=positive_evidence.as_of,
                evidence_refs=(positive_evidence,),
            )
        )

    missing = ()
    if classification_missing:
        missing = (
            CandidateMissingMetric(
                metric_code="metric.diversification.geography",
                criticality="critical",
                expected_source="candidate-classification",
                reason_code="missing.diversification.geography",
                guardrail_effect="block",
            ),
            CandidateMissingMetric(
                metric_code="metric.diversification.sector",
                criticality="critical",
                expected_source="candidate-classification",
                reason_code="missing.diversification.sector",
                guardrail_effect="block",
            ),
        )
        diversification_score = CandidateScore(
            score_type="diversification",
            value=None,
            components=(),
            evidence_refs=(),
            missing_metric_code="metric.diversification.sector",
        )
    else:
        diversification_score = _score("diversification", diversification, source)

    evidence = {source.evidence_id: source, overlap.evidence_id: overlap}
    for highlight in highlights:
        for ref in highlight.evidence_refs:
            evidence[ref.evidence_id] = ref
    stable_candidate_id = candidate_id(asset_id)
    return CandidateReview(
        review_id=candidate_review_id(RUN_ID, stable_candidate_id),
        run_id=RUN_ID,
        candidate_id=stable_candidate_id,
        asset_id=asset_id,
        ticker=asset_id,
        schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        reason_codes=("source.ranking.aggregate",),
        source_matches=(
            CandidateSourceMatch(
                source_family="ranking",
                source_methodology_version="fixture-source.v1",
                reason_code="source.ranking.aggregate",
                evidence_refs=(source,),
            ),
        ),
        fit_score=_score("fit", fit, source),
        diversification_score=diversification_score,
        redundancy_score=_score("redundancy", redundancy, overlap),
        highlights=tuple(highlights),
        missing_metrics=missing,
        warnings=(),
        evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
        data_as_of=AS_OF,
        methodology_as_of=AS_OF,
        eligibility_state="eligible",
    )


def _asset(
    conn,
    asset_id: str,
    *,
    sector: str | None = "Technology",
    country: str | None = "US",
    updated_age: int = 1,
) -> None:
    updated_at = AS_OF - timedelta(days=updated_age)
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, symbol, asset_type, ccy, name, sector, country,
            created_at, updated_at
        )
        VALUES (?, ?, 'stock', 'USD', ?, ?, ?, ?, ?)
        """,
        [
            asset_id,
            asset_id,
            asset_id,
            sector,
            country,
            updated_at.replace(tzinfo=None),
            updated_at.replace(tzinfo=None),
        ],
    )


def _quotes(
    conn,
    asset_id: str,
    *,
    latest_age: int = 1,
    daily_notional: int = 10_000_000,
    include_volume: bool = True,
) -> None:
    close = 10
    volume = daily_notional // close if include_volume else None
    rows = []
    for offset in range(latest_age, latest_age + 20):
        quote_at = AS_OF - timedelta(days=offset)
        rows.append(
            [
                asset_id,
                quote_at.date(),
                close,
                volume,
                quote_at.replace(tzinfo=None),
            ]
        )
    conn.executemany(
        """
        INSERT INTO asset_quote_daily(
            asset_id, date, close, adj_close, volume, ing_source, ing_at
        )
        VALUES (?, ?, ?, ?, ?, 'fixture', ?)
        """,
        [
            [asset_id, day, close, close, volume, ing_at]
            for asset_id, day, close, volume, ing_at in rows
        ],
    )


def _apply(conn, review: CandidateReview) -> CandidateReview:
    return CandidateGuardrailPolicy(conn).apply(
        portfolio_id=1,
        as_of=AS_OF,
        reviews=(review,),
    )[0]


@pytest.mark.parametrize(
    ("domain", "current_days", "block_days", "material"),
    [
        ("candidate-price", 7, 14, False),
        ("candidate-liquidity", 14, 30, False),
        ("ticker-factor", 45, 120, True),
        ("asset-analytics-valuation", 120, 365, True),
        ("business-strength-scorecard", 180, 540, True),
        ("ticker-sentiment", 3, 14, False),
        ("unversioned-source", None, None, False),
    ],
)
def test_freshness_policy_is_evidence_type_specific(
    domain,
    current_days,
    block_days,
    material,
) -> None:
    policy = freshness_policy_for_domain(domain)
    assert (policy.current_days, policy.block_days, policy.material_support) == (
        current_days,
        block_days,
        material,
    )


@pytest.mark.parametrize(
    ("age", "expected_state", "eligibility", "warning"),
    [
        (45, "current", "eligible", None),
        (46, "stale", "downgraded", "guardrail.evidence.material_stale"),
        (120, "stale", "downgraded", "guardrail.evidence.material_stale"),
        (121, "stale", "blocked", "guardrail.evidence.material_expired"),
    ],
)
def test_material_freshness_boundaries(
    conn,
    age,
    expected_state,
    eligibility,
    warning,
) -> None:
    _asset(conn, "BOUNDARY")
    _quotes(conn, "BOUNDARY")
    guarded = _apply(conn, _review("BOUNDARY", source_age=age))

    source = next(ref for ref in guarded.evidence_refs if ref.source_domain == "stock-ranking")
    assert source.freshness_state == expected_state
    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in {value.warning_code for value in guarded.warnings}


@pytest.mark.parametrize(
    ("latest_age", "eligibility", "warning"),
    [
        (7, "eligible", None),
        (8, "downgraded", "guardrail.evidence.price_stale"),
        (14, "downgraded", "guardrail.evidence.price_stale"),
        (15, "blocked", "guardrail.evidence.price_expired"),
    ],
)
def test_price_freshness_boundaries(conn, latest_age, eligibility, warning) -> None:
    _asset(conn, "PRICE")
    _quotes(conn, "PRICE", latest_age=latest_age)
    guarded = _apply(conn, _review("PRICE"))

    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in {value.warning_code for value in guarded.warnings}


@pytest.mark.parametrize(
    ("updated_age", "eligibility", "warning"),
    [
        (365, "eligible", None),
        (366, "downgraded", "guardrail.evidence.identity_stale"),
        (730, "downgraded", "guardrail.evidence.identity_stale"),
        (731, "blocked", "guardrail.evidence.identity_expired"),
    ],
)
def test_identity_freshness_boundaries(conn, updated_age, eligibility, warning) -> None:
    _asset(conn, "IDENTITY", updated_age=updated_age)
    _quotes(conn, "IDENTITY")
    guarded = _apply(conn, _review("IDENTITY"))

    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in guarded.reason_codes


@pytest.mark.parametrize(
    ("risk_age", "eligibility", "warning"),
    [
        (120, "eligible", None),
        (121, "downgraded", "guardrail.evidence.risk_stale"),
        (365, "downgraded", "guardrail.evidence.risk_stale"),
        (366, "blocked", "guardrail.evidence.risk_expired"),
    ],
)
def test_critical_risk_freshness_boundaries(conn, risk_age, eligibility, warning) -> None:
    _asset(conn, "RISKAGE")
    _quotes(conn, "RISKAGE")
    guarded = _apply(conn, _review("RISKAGE", risk_age=risk_age))

    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in guarded.reason_codes


def test_unknown_critical_risk_freshness_blocks(conn) -> None:
    _asset(conn, "UNKNOWNRISK")
    _quotes(conn, "UNKNOWNRISK")

    guarded = _apply(
        conn,
        _review("UNKNOWNRISK", risk_domain="unversioned-risk-source"),
    )

    assert guarded.eligibility_state == "blocked"
    assert "metric.guardrail.risk.freshness" in {
        value.metric_code for value in guarded.missing_metrics
    }
    assert "guardrail.evidence.risk_freshness_unknown" in guarded.reason_codes


@pytest.mark.parametrize("missing", ["identity", "price", "risk"])
def test_critical_missing_evidence_blocks(conn, missing) -> None:
    if missing != "identity":
        _asset(conn, "CRITICAL")
    if missing not in {"identity", "price"}:
        _quotes(conn, "CRITICAL")
    review = _review("CRITICAL", risk=None if missing == "risk" else Decimal("50"))

    guarded = _apply(conn, review)

    assert guarded.eligibility_state == "blocked"
    assert f"metric.guardrail.{missing}" in {value.metric_code for value in guarded.missing_metrics}
    assert f"guardrail.{missing}.insufficient" in {value.warning_code for value in guarded.warnings}


def test_missing_liquidity_is_visible_and_not_zero(conn) -> None:
    _asset(conn, "NOVOLUME")
    _quotes(conn, "NOVOLUME", include_volume=False)

    guarded = _apply(conn, _review("NOVOLUME"))

    metric = next(
        value
        for value in guarded.missing_metrics
        if value.metric_code == "metric.guardrail.liquidity"
    )
    assert guarded.eligibility_state == "downgraded"
    assert metric.criticality == "noncritical"
    assert metric.guardrail_effect == "downgrade"
    assert "guardrail.liquidity.coverage_insufficient" in guarded.reason_codes


def test_sentiment_cannot_be_sole_material_support(conn) -> None:
    _asset(conn, "SENTIMENT")
    _quotes(conn, "SENTIMENT")

    guarded = _apply(
        conn,
        _review("SENTIMENT", source_domain="ticker-sentiment"),
    )

    assert guarded.eligibility_state == "blocked"
    assert "guardrail.support.sentiment_only" in guarded.reason_codes
    assert "metric.guardrail.material_support" in {
        value.metric_code for value in guarded.missing_metrics
    }


@pytest.mark.parametrize(
    ("daily_notional", "eligibility", "warning"),
    [
        (99_999, "downgraded", "guardrail.liquidity.extremely_low"),
        (100_000, "downgraded", "guardrail.liquidity.low"),
        (999_999, "downgraded", "guardrail.liquidity.low"),
        (1_000_000, "eligible", None),
    ],
)
def test_liquidity_boundaries(conn, daily_notional, eligibility, warning) -> None:
    _asset(conn, "LIQUID")
    _quotes(conn, "LIQUID", daily_notional=daily_notional)

    guarded = _apply(conn, _review("LIQUID"))

    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in guarded.reason_codes


@pytest.mark.parametrize(
    ("risk", "eligibility", "warning"),
    [
        (Decimal("69.99999999"), "eligible", None),
        (Decimal("70"), "eligible", "guardrail.risk.speculative_high"),
        (Decimal("89.99999999"), "eligible", "guardrail.risk.speculative_high"),
        (Decimal("90"), "downgraded", "guardrail.risk.speculative_extreme"),
    ],
)
def test_speculative_risk_boundaries(conn, risk, eligibility, warning) -> None:
    _asset(conn, "RISK")
    _quotes(conn, "RISK")

    guarded = _apply(conn, _review("RISK", risk=risk))

    assert guarded.eligibility_state == eligibility
    if warning is not None:
        assert warning in guarded.reason_codes


def test_unsupported_classification_blocks(conn) -> None:
    _asset(conn, "UNCLASSIFIED", sector=None, country=None)
    _quotes(conn, "UNCLASSIFIED")

    guarded = _apply(conn, _review("UNCLASSIFIED", classification_missing=True))

    assert guarded.eligibility_state == "blocked"
    assert "guardrail.classification.unsupported" in guarded.reason_codes
    assert "metric.guardrail.classification" in {
        value.metric_code for value in guarded.missing_metrics
    }


def test_undated_etf_lookthrough_downgrades_redundancy_freshness(conn) -> None:
    _asset(conn, "ETF")
    _quotes(conn, "ETF")
    conn.execute("CREATE TABLE etf_holding(asset_id TEXT, holding_symbol TEXT, weight_pct DOUBLE)")
    conn.execute("INSERT INTO etf_holding VALUES ('ETF', 'UNDERLYING', 100)")

    guarded = _apply(conn, _review("ETF"))

    overlap = next(
        ref
        for ref in guarded.redundancy_score.evidence_refs
        if ref.source_domain == "candidate-economic-overlap"
    )
    assert overlap.freshness_state == "unknown"
    assert guarded.eligibility_state == "downgraded"
    assert "guardrail.evidence.redundancy_freshness_unknown" in guarded.reason_codes


def test_stale_positive_cannot_outrank_current_contradictory_evidence(conn) -> None:
    _asset(conn, "STALE")
    _quotes(conn, "STALE")
    _asset(conn, "CURRENT")
    _quotes(conn, "CURRENT")
    stale = _apply(
        conn,
        _review(
            "STALE",
            fit=Decimal("99"),
            risk=Decimal("80"),
            stale_positive=True,
        ),
    )
    current = _apply(conn, _review("CURRENT", fit=Decimal("60")))

    ordered = tuple(sorted((stale, current), key=candidate_review_sort_key))

    assert stale.eligibility_state == "downgraded"
    assert "guardrail.evidence.current_contradiction" in stale.reason_codes
    assert [value.asset_id for value in ordered] == ["CURRENT", "STALE"]


def test_warning_codes_order_and_evidence_are_byte_stable(conn) -> None:
    _asset(conn, "STABLE")
    _quotes(conn, "STABLE", daily_notional=50_000)
    conn.execute("CREATE TABLE etf_holding(asset_id TEXT, holding_symbol TEXT, weight_pct DOUBLE)")
    conn.execute("INSERT INTO etf_holding VALUES ('STABLE', 'UNDERLYING', 100)")
    review = _review(
        "STABLE",
        diversification=Decimal("10"),
        redundancy=Decimal("60"),
        risk=Decimal("90"),
    )

    first = _apply(conn, review)
    second = _apply(conn, review)
    warning_codes = tuple(value.warning_code for value in first.warnings)
    evidence_ids = {value.evidence_id for value in first.evidence_refs}

    assert warning_codes == tuple(sorted(warning_codes))
    assert all(
        {ref.evidence_id for ref in warning.evidence_refs}.issubset(evidence_ids)
        for warning in first.warnings
    )
    assert canonical_json(first) == canonical_json(second)


def test_review_contract_rejects_evidence_free_candidate() -> None:
    review = _review("NOEVIDENCE")

    with pytest.raises(ValueError, match="stable evidence"):
        replace(review, evidence_refs=())
