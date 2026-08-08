"""Deterministic candidate freshness, sufficiency, and guardrail policy."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any

from dashboard.ai_brain.candidates.models import (
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CandidateEvidenceRef,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidateReview,
    CandidateScore,
    CandidateScoreComponent,
    CandidateSourceMatch,
    CandidateWarning,
)
from dashboard.ai_brain.candidates.source_adapters import candidate_source_evidence

CANDIDATE_GUARDRAIL_POLICY_VERSION = "candidate-guardrails.v1"
CANDIDATE_IDENTITY_SCHEMA_VERSION = "candidate-identity.v1"
CANDIDATE_PRICE_SCHEMA_VERSION = "candidate-price-snapshot.v1"
CANDIDATE_LIQUIDITY_SCHEMA_VERSION = "candidate-liquidity-snapshot.v1"
GUARDRAIL_METHODOLOGY_AS_OF = datetime(2026, 8, 8, tzinfo=timezone.utc)

LIQUIDITY_OBSERVATION_COUNT = 20
MIN_LIQUIDITY_OBSERVATIONS = 10
EXTREME_LOW_MEDIAN_DAILY_NOTIONAL = Decimal("100000")
DOWNGRADE_MEDIAN_DAILY_NOTIONAL = Decimal("1000000")
HIGH_SPECULATIVE_RISK_SCORE = Decimal("70")
EXTREME_SPECULATIVE_RISK_SCORE = Decimal("90")
LOW_DIVERSIFICATION_SCORE = Decimal("20")


@dataclass(frozen=True)
class EvidenceFreshnessPolicy:
    evidence_type: str
    current_days: int | None
    block_days: int | None
    material_support: bool = False

    def __post_init__(self) -> None:
        if not self.evidence_type:
            raise ValueError("evidence_type is required")
        if (self.current_days is None) != (self.block_days is None):
            raise ValueError("freshness thresholds must both be set or both be unknown")
        if self.current_days is not None and (
            self.current_days < 0 or self.block_days < self.current_days
        ):
            raise ValueError("freshness thresholds must be nonnegative and ordered")


_PRICE_POLICY = EvidenceFreshnessPolicy("market_price", 7, 14)
_LIQUIDITY_POLICY = EvidenceFreshnessPolicy("market_liquidity", 14, 30)
_FACTOR_POLICY = EvidenceFreshnessPolicy("factor_or_ranking", 45, 120, True)
_VALUATION_POLICY = EvidenceFreshnessPolicy("valuation_or_risk", 120, 365, True)
_FUNDAMENTAL_POLICY = EvidenceFreshnessPolicy("fundamental_quality", 180, 540, True)
_PORTFOLIO_POLICY = EvidenceFreshnessPolicy("portfolio_state", 30, 90, True)
_BENCHMARK_POLICY = EvidenceFreshnessPolicy("benchmark_composition", 90, 365, True)
_CLASSIFICATION_POLICY = EvidenceFreshnessPolicy("classification", 365, 1095, True)
_ASSOCIATION_POLICY = EvidenceFreshnessPolicy("association", 365, 730, True)
_IDENTITY_POLICY = EvidenceFreshnessPolicy("identity", 365, 730)
_PROFILE_POLICY = EvidenceFreshnessPolicy("investor_profile", 30, 90)
_SENTIMENT_POLICY = EvidenceFreshnessPolicy("sentiment", 3, 14)
_CATALOG_POLICY = EvidenceFreshnessPolicy("catalog_or_watchlist", 180, 365)
_DERIVED_POLICY = EvidenceFreshnessPolicy("derived_score", 30, 90)
_UNKNOWN_POLICY = EvidenceFreshnessPolicy("unknown", None, None)

_POLICY_BY_DOMAIN = {
    "asset-analytics-scoring": _VALUATION_POLICY,
    "asset-analytics-valuation": _VALUATION_POLICY,
    "asset-business-classification": _CLASSIFICATION_POLICY,
    "asset-catalog-search": _CATALOG_POLICY,
    "asset-classification": _CLASSIFICATION_POLICY,
    "benchmark-composition": _BENCHMARK_POLICY,
    "business-strength-peer-groups": _ASSOCIATION_POLICY,
    "business-strength-scorecard": _FUNDAMENTAL_POLICY,
    "candidate-asset-classification": _CLASSIFICATION_POLICY,
    "candidate-economic-overlap": _DERIVED_POLICY,
    "candidate-identity": _IDENTITY_POLICY,
    "candidate-liquidity": _LIQUIDITY_POLICY,
    "candidate-price": _PRICE_POLICY,
    "investor-profile": _PROFILE_POLICY,
    "portfolio-analytics-scoring": _PORTFOLIO_POLICY,
    "portfolio-geography-gap": _PORTFOLIO_POLICY,
    "portfolio-sector-gap": _PORTFOLIO_POLICY,
    "profile-theme-benchmark": _BENCHMARK_POLICY,
    "stock-ranking": _FACTOR_POLICY,
    "ticker-factor": _FACTOR_POLICY,
    "ticker-sentiment": _SENTIMENT_POLICY,
    "watchlist": _CATALOG_POLICY,
}


@dataclass(frozen=True)
class _IdentitySnapshot:
    evidence: CandidateEvidenceRef
    sector: str | None
    country: str | None


@dataclass(frozen=True)
class _MarketSnapshot:
    price_evidence: CandidateEvidenceRef | None
    liquidity_evidence: CandidateEvidenceRef | None
    median_daily_notional: Decimal | None
    liquidity_observations: int


class CandidateGuardrailPolicy:
    """Apply monotonic guardrails to scored candidate reviews."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def apply(
        self,
        *,
        portfolio_id: int,
        as_of: datetime,
        reviews: tuple[CandidateReview, ...],
    ) -> tuple[CandidateReview, ...]:
        normalized_as_of = _normalize_as_of(as_of)
        portfolio_assets = self._portfolio_asset_ids(portfolio_id, normalized_as_of)
        return tuple(
            self._apply_review(
                review=review,
                as_of=normalized_as_of,
                portfolio_assets=portfolio_assets,
            )
            for review in reviews
        )

    def _apply_review(
        self,
        *,
        review: CandidateReview,
        as_of: datetime,
        portfolio_assets: tuple[str, ...],
    ) -> CandidateReview:
        identity = self._identity_snapshot(review.asset_id, as_of)
        market = self._market_snapshot(review.asset_id, as_of)
        added_evidence = tuple(
            ref
            for ref in (
                identity.evidence if identity is not None else None,
                market.price_evidence,
                market.liquidity_evidence,
            )
            if ref is not None
        )
        review = replace(
            review,
            evidence_refs=_merge_evidence(review.evidence_refs, added_evidence),
            methodology_version=CANDIDATE_METHODOLOGY_VERSION,
            reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
            methodology_as_of=GUARDRAIL_METHODOLOGY_AS_OF,
        )
        uses_undated_lookthrough = self._uses_undated_lookthrough(
            review.asset_id,
            portfolio_assets,
        )
        review = _freshen_review(
            review,
            as_of=as_of,
            uses_undated_lookthrough=uses_undated_lookthrough,
        )
        canonical_evidence = {ref.evidence_id: ref for ref in review.evidence_refs}
        if identity is not None:
            identity = replace(
                identity,
                evidence=canonical_evidence[identity.evidence.evidence_id],
            )
        market = replace(
            market,
            price_evidence=(
                canonical_evidence[market.price_evidence.evidence_id]
                if market.price_evidence is not None
                else None
            ),
            liquidity_evidence=(
                canonical_evidence[market.liquidity_evidence.evidence_id]
                if market.liquidity_evidence is not None
                else None
            ),
        )

        warning_by_code = {warning.warning_code: warning for warning in review.warnings}
        missing_by_code = {metric.metric_code: metric for metric in review.missing_metrics}
        eligibility = review.eligibility_state

        def add_warning(
            code: str,
            *,
            severity: str,
            effect: str,
            evidence: tuple[CandidateEvidenceRef, ...],
        ) -> None:
            nonlocal eligibility
            refs = evidence or review.evidence_refs
            warning_by_code.setdefault(
                code,
                CandidateWarning(
                    warning_code=code,
                    severity=severity,
                    blocking=effect == "block",
                    evidence_refs=_merge_evidence(refs),
                ),
            )
            eligibility = _worse_eligibility(eligibility, effect)

        def add_missing(
            code: str,
            *,
            criticality: str,
            expected_source: str,
            reason_code: str,
            effect: str,
        ) -> None:
            missing_by_code.setdefault(
                code,
                CandidateMissingMetric(
                    metric_code=code,
                    criticality=criticality,
                    expected_source=expected_source,
                    reason_code=reason_code,
                    guardrail_effect=effect,
                ),
            )

        source_evidence = _merge_evidence(
            tuple(ref for match in review.source_matches for ref in match.evidence_refs)
        )
        material_evidence = tuple(
            ref
            for ref in source_evidence
            if freshness_policy_for_domain(ref.source_domain).material_support
        )
        sentiment_evidence = tuple(
            ref for ref in source_evidence if ref.source_domain == "ticker-sentiment"
        )
        if not material_evidence:
            sentiment_only = bool(sentiment_evidence)
            warning_code = (
                "guardrail.support.sentiment_only"
                if sentiment_only
                else "guardrail.support.material_evidence_missing"
            )
            reason_code = (
                "missing.guardrail.material_support.sentiment_only"
                if sentiment_only
                else "missing.guardrail.material_support"
            )
            add_missing(
                "metric.guardrail.material_support",
                criticality="critical",
                expected_source="candidate-material-source",
                reason_code=reason_code,
                effect="block",
            )
            add_warning(
                warning_code,
                severity="critical",
                effect="block",
                evidence=sentiment_evidence or source_evidence,
            )
        else:
            current_material = tuple(
                ref for ref in material_evidence if ref.freshness_state == "current"
            )
            stale_material = tuple(
                ref for ref in material_evidence if ref.freshness_state == "stale"
            )
            unknown_material = tuple(
                ref for ref in material_evidence if ref.freshness_state == "unknown"
            )
            expired_material = tuple(ref for ref in stale_material if _is_expired(ref, as_of))
            if expired_material and len(expired_material) == len(material_evidence):
                add_warning(
                    "guardrail.evidence.material_expired",
                    severity="critical",
                    effect="block",
                    evidence=expired_material,
                )
            elif expired_material:
                add_warning(
                    "guardrail.evidence.material_expired",
                    severity="warning",
                    effect="downgrade",
                    evidence=expired_material,
                )
            elif stale_material and not current_material:
                add_warning(
                    "guardrail.evidence.material_stale",
                    severity="warning",
                    effect="downgrade",
                    evidence=stale_material,
                )
            elif stale_material:
                add_warning(
                    "guardrail.evidence.material_stale",
                    severity="info",
                    effect="none",
                    evidence=stale_material,
                )
            if unknown_material and not current_material:
                add_warning(
                    "guardrail.evidence.material_freshness_unknown",
                    severity="warning",
                    effect="downgrade",
                    evidence=unknown_material,
                )

        if identity is None:
            add_missing(
                "metric.guardrail.identity",
                criticality="critical",
                expected_source="asset-or-stock-catalog",
                reason_code="missing.guardrail.identity",
                effect="block",
            )
            add_warning(
                "guardrail.identity.insufficient",
                severity="critical",
                effect="block",
                evidence=source_evidence,
            )
        else:
            eligibility = self._apply_critical_freshness(
                evidence=(identity.evidence,),
                label="identity",
                as_of=as_of,
                eligibility=eligibility,
                add_warning=add_warning,
                add_missing=add_missing,
            )
            missing_codes = set(missing_by_code)
            unsupported_sector = (
                identity.sector is None and "metric.diversification.sector" in missing_codes
            )
            unsupported_geography = (
                identity.country is None and "metric.diversification.geography" in missing_codes
            )
            if unsupported_sector or unsupported_geography:
                add_warning(
                    "guardrail.classification.unsupported",
                    severity="critical",
                    effect="block",
                    evidence=(identity.evidence,),
                )
                add_missing(
                    "metric.guardrail.classification",
                    criticality="critical",
                    expected_source="asset-business-classification",
                    reason_code="missing.guardrail.classification",
                    effect="block",
                )

        if market.price_evidence is None:
            add_missing(
                "metric.guardrail.price",
                criticality="critical",
                expected_source="asset_quote_daily",
                reason_code="missing.guardrail.price",
                effect="block",
            )
            add_warning(
                "guardrail.price.insufficient",
                severity="critical",
                effect="block",
                evidence=(identity.evidence,) if identity is not None else source_evidence,
            )
        else:
            eligibility = self._apply_critical_freshness(
                evidence=(market.price_evidence,),
                label="price",
                as_of=as_of,
                eligibility=eligibility,
                add_warning=add_warning,
                add_missing=add_missing,
            )

        risk_highlights = tuple(value for value in review.highlights if value.category == "risk")
        risk_evidence = _merge_evidence(
            tuple(ref for value in risk_highlights for ref in value.evidence_refs)
        )
        if not risk_evidence:
            add_missing(
                "metric.guardrail.risk",
                criticality="critical",
                expected_source="candidate-risk-snapshot",
                reason_code="missing.guardrail.risk",
                effect="block",
            )
            add_warning(
                "guardrail.risk.insufficient",
                severity="critical",
                effect="block",
                evidence=source_evidence,
            )
        else:
            eligibility = self._apply_critical_freshness(
                evidence=risk_evidence,
                label="risk",
                as_of=as_of,
                eligibility=eligibility,
                add_warning=add_warning,
                add_missing=add_missing,
            )

        if market.median_daily_notional is None:
            add_missing(
                "metric.guardrail.liquidity",
                criticality="noncritical",
                expected_source="asset_quote_daily.volume",
                reason_code="missing.guardrail.liquidity",
                effect="downgrade",
            )
            add_warning(
                "guardrail.liquidity.coverage_insufficient",
                severity="warning",
                effect="downgrade",
                evidence=(market.liquidity_evidence or market.price_evidence,)
                if market.liquidity_evidence or market.price_evidence
                else source_evidence,
            )
        elif market.median_daily_notional < EXTREME_LOW_MEDIAN_DAILY_NOTIONAL:
            add_warning(
                "guardrail.liquidity.extremely_low",
                severity="warning",
                effect="downgrade",
                evidence=(market.liquidity_evidence,),
            )
        elif market.median_daily_notional < DOWNGRADE_MEDIAN_DAILY_NOTIONAL:
            add_warning(
                "guardrail.liquidity.low",
                severity="warning",
                effect="downgrade",
                evidence=(market.liquidity_evidence,),
            )

        risk_value = risk_highlights[0].normalized_value if risk_highlights else None
        if risk_value is not None and risk_value >= EXTREME_SPECULATIVE_RISK_SCORE:
            add_warning(
                "guardrail.risk.speculative_extreme",
                severity="warning",
                effect="downgrade",
                evidence=risk_evidence,
            )
        elif risk_value is not None and risk_value >= HIGH_SPECULATIVE_RISK_SCORE:
            add_warning(
                "guardrail.risk.speculative_high",
                severity="warning",
                effect="none",
                evidence=risk_evidence,
            )

        if (
            review.diversification_score.value is not None
            and review.diversification_score.value <= LOW_DIVERSIFICATION_SCORE
        ):
            add_warning(
                "guardrail.concentration.limited_diversification",
                severity="info",
                effect="none",
                evidence=review.diversification_score.evidence_refs,
            )
        if review.redundancy_score.value is not None and review.redundancy_score.value >= 50:
            add_warning(
                "guardrail.redundancy.material_overlap",
                severity="warning",
                effect="downgrade",
                evidence=review.redundancy_score.evidence_refs,
            )
        unknown_overlap = tuple(
            ref for ref in review.redundancy_score.evidence_refs if ref.freshness_state == "unknown"
        )
        if unknown_overlap:
            add_warning(
                "guardrail.evidence.redundancy_freshness_unknown",
                severity="warning",
                effect="downgrade",
                evidence=unknown_overlap,
            )

        stale_positive = tuple(
            value
            for value in review.highlights
            if value.direction == "positive"
            and any(ref.freshness_state == "stale" for ref in value.evidence_refs)
        )
        current_negative = tuple(
            value
            for value in review.highlights
            if value.direction == "negative"
            and any(ref.freshness_state == "current" for ref in value.evidence_refs)
        )
        if stale_positive and current_negative:
            add_warning(
                "guardrail.evidence.current_contradiction",
                severity="warning",
                effect="downgrade",
                evidence=_highlight_evidence((*stale_positive, *current_negative)),
            )
        current_positive = tuple(
            value
            for value in review.highlights
            if value.direction == "positive"
            and any(ref.freshness_state == "current" for ref in value.evidence_refs)
        )
        if current_positive and current_negative:
            add_warning(
                "guardrail.evidence.mixed_current",
                severity="info",
                effect="none",
                evidence=_highlight_evidence((*current_positive, *current_negative)),
            )

        warnings = tuple(warning_by_code[key] for key in sorted(warning_by_code))
        missing = tuple(missing_by_code[key] for key in sorted(missing_by_code))
        evidence = _merge_evidence(
            review.evidence_refs,
            tuple(ref for warning in warnings for ref in warning.evidence_refs),
        )
        reason_codes = tuple(
            sorted({*review.reason_codes, *(warning.warning_code for warning in warnings)})
        )
        return replace(
            review,
            reason_codes=reason_codes,
            missing_metrics=missing,
            warnings=warnings,
            evidence_refs=evidence,
            eligibility_state=eligibility,
        )

    @staticmethod
    def _apply_critical_freshness(
        *,
        evidence: tuple[CandidateEvidenceRef, ...],
        label: str,
        as_of: datetime,
        eligibility: str,
        add_warning: Any,
        add_missing: Any,
    ) -> str:
        unknown = tuple(ref for ref in evidence if ref.freshness_state == "unknown")
        stale = tuple(ref for ref in evidence if ref.freshness_state == "stale")
        expired = tuple(ref for ref in stale if _is_expired(ref, as_of))
        if unknown:
            add_missing(
                f"metric.guardrail.{label}.freshness",
                criticality="critical",
                expected_source=f"current-candidate-{label}-evidence",
                reason_code=f"missing.guardrail.{label}.freshness",
                effect="block",
            )
            add_warning(
                f"guardrail.evidence.{label}_freshness_unknown",
                severity="critical",
                effect="block",
                evidence=unknown,
            )
            return _worse_eligibility(eligibility, "block")
        if expired:
            add_warning(
                f"guardrail.evidence.{label}_expired",
                severity="critical",
                effect="block",
                evidence=expired,
            )
            return _worse_eligibility(eligibility, "block")
        if stale:
            add_warning(
                f"guardrail.evidence.{label}_stale",
                severity="warning",
                effect="downgrade",
                evidence=stale,
            )
            return _worse_eligibility(eligibility, "downgrade")
        return eligibility

    def _identity_snapshot(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> _IdentitySnapshot | None:
        as_of_db = _as_db_timestamp(as_of)
        row = self.conn.execute(
            """
            SELECT asset_id, COALESCE(symbol, asset_id), asset_type, ccy, name,
                   sector, country, size, mkt_cap, updated_at, 'asset'
            FROM asset
            WHERE UPPER(asset_id) = UPPER(?)
              AND updated_at <= ?
            LIMIT 1
            """,
            [asset_id, as_of_db],
        ).fetchone()
        if row is None:
            row = self.conn.execute(
                """
                SELECT asset_id, symbol, asset_type, ccy, name, sector, country,
                       NULL, NULL, updated_at, 'stock_catalog'
                FROM stock_catalog
                WHERE UPPER(asset_id) = UPPER(?)
                  AND updated_at <= ?
                LIMIT 1
                """,
                [asset_id, as_of_db],
            ).fetchone()
        if row is None:
            return None
        evidence = candidate_source_evidence(
            source_domain="candidate-identity",
            source_schema_version=CANDIDATE_IDENTITY_SCHEMA_VERSION,
            source_record_id=f"identity:{row[10]}:{row[0]}",
            as_of=_as_utc(row[9]),
            payload={
                "asset_id": row[0],
                "symbol": row[1],
                "asset_type": row[2],
                "currency": row[3],
                "name": row[4],
                "sector": row[5],
                "country": row[6],
                "size": row[7],
                "market_cap": row[8],
                "updated_at": _as_utc(row[9]),
                "source": row[10],
            },
        )
        return _IdentitySnapshot(
            evidence=evidence,
            sector=_known_text(row[5]),
            country=_known_text(row[6]),
        )

    def _market_snapshot(self, asset_id: str, as_of: datetime) -> _MarketSnapshot:
        rows = self.conn.execute(
            """
            SELECT date, close, volume, ing_source, ing_at
            FROM asset_quote_daily
            WHERE UPPER(asset_id) = UPPER(?)
              AND date <= ?
              AND ing_at <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            [asset_id, as_of.date(), _as_db_timestamp(as_of), LIQUIDITY_OBSERVATION_COUNT],
        ).fetchall()
        valid_price_rows = tuple(row for row in rows if row[1] is not None and float(row[1]) > 0)
        if not valid_price_rows:
            return _MarketSnapshot(None, None, None, 0)
        latest = valid_price_rows[0]
        price_evidence = candidate_source_evidence(
            source_domain="candidate-price",
            source_schema_version=CANDIDATE_PRICE_SCHEMA_VERSION,
            source_record_id=f"price:{asset_id}:{latest[0].isoformat()}",
            as_of=_as_utc(latest[0]),
            payload={
                "asset_id": asset_id,
                "date": latest[0],
                "close": latest[1],
                "source": latest[3],
                "ingested_at": _as_utc(latest[4]),
            },
        )
        liquidity_rows = tuple(
            row for row in valid_price_rows if row[2] is not None and float(row[2]) > 0
        )
        observations = tuple(
            {
                "date": row[0],
                "close": row[1],
                "volume": row[2],
                "daily_notional": str(Decimal(str(row[1])) * Decimal(str(row[2]))),
            }
            for row in reversed(liquidity_rows)
        )
        median_notional = (
            median(Decimal(item["daily_notional"]) for item in observations)
            if len(observations) >= MIN_LIQUIDITY_OBSERVATIONS
            else None
        )
        liquidity_evidence = candidate_source_evidence(
            source_domain="candidate-liquidity",
            source_schema_version=CANDIDATE_LIQUIDITY_SCHEMA_VERSION,
            source_record_id=f"liquidity:{asset_id}:{latest[0].isoformat()}",
            as_of=_as_utc(latest[0]),
            payload={
                "asset_id": asset_id,
                "latest_date": latest[0],
                "observation_count": len(observations),
                "required_observations": MIN_LIQUIDITY_OBSERVATIONS,
                "median_daily_notional": str(median_notional)
                if median_notional is not None
                else None,
                "notional_currency": "asset_local_currency",
                "observations": observations,
            },
        )
        return _MarketSnapshot(
            price_evidence=price_evidence,
            liquidity_evidence=liquidity_evidence,
            median_daily_notional=median_notional,
            liquidity_observations=len(observations),
        )

    def _portfolio_asset_ids(
        self,
        portfolio_id: int,
        as_of: datetime,
    ) -> tuple[str, ...]:
        if not _table_exists(self.conn, "portfolio_analytics_snapshot"):
            return ()
        row = self.conn.execute(
            """
            SELECT payload_json
            FROM portfolio_analytics_snapshot
            WHERE portfolio_id = ?
              AND snapshot_date <= ?
              AND refreshed_at <= ?
            ORDER BY snapshot_date DESC, refreshed_at DESC
            LIMIT 1
            """,
            [portfolio_id, as_of.date(), _as_db_timestamp(as_of)],
        ).fetchone()
        if row is None:
            return ()
        payload = _json_object(row[0])
        positions = payload.get("positions")
        if not isinstance(positions, list):
            return ()
        return tuple(
            sorted(
                {
                    str(item["asset_id"])
                    for item in positions
                    if isinstance(item, dict) and item.get("asset_id")
                }
            )
        )

    def _uses_undated_lookthrough(
        self,
        candidate_asset_id: str,
        portfolio_asset_ids: tuple[str, ...],
    ) -> bool:
        if not _table_exists(self.conn, "etf_holding"):
            return False
        for asset_id in (candidate_asset_id, *portfolio_asset_ids):
            if self.conn.execute(
                "SELECT 1 FROM etf_holding WHERE UPPER(asset_id) = UPPER(?) LIMIT 1",
                [asset_id],
            ).fetchone():
                return True
        return False


def freshness_policy_for_domain(source_domain: str) -> EvidenceFreshnessPolicy:
    if source_domain in _POLICY_BY_DOMAIN:
        return _POLICY_BY_DOMAIN[source_domain]
    if source_domain.startswith("portfolio-"):
        return _PORTFOLIO_POLICY
    return _UNKNOWN_POLICY


def evidence_age_days(ref: CandidateEvidenceRef, as_of: datetime) -> int:
    normalized_as_of = _normalize_as_of(as_of)
    return (normalized_as_of.date() - ref.as_of.astimezone(timezone.utc).date()).days


def _freshen_review(
    review: CandidateReview,
    *,
    as_of: datetime,
    uses_undated_lookthrough: bool,
) -> CandidateReview:
    replacements = {
        ref.evidence_id: replace(
            ref,
            freshness_state=_freshness_state(
                ref,
                as_of,
                uses_undated_lookthrough=uses_undated_lookthrough,
            ),
        )
        for ref in review.evidence_refs
    }

    def refs(values: tuple[CandidateEvidenceRef, ...]) -> tuple[CandidateEvidenceRef, ...]:
        return tuple(replacements[value.evidence_id] for value in values)

    def component(value: CandidateScoreComponent) -> CandidateScoreComponent:
        return replace(value, evidence_refs=refs(value.evidence_refs))

    def score(value: CandidateScore) -> CandidateScore:
        return replace(
            value,
            components=tuple(component(item) for item in value.components),
            evidence_refs=refs(value.evidence_refs),
        )

    def source_match(value: CandidateSourceMatch) -> CandidateSourceMatch:
        return replace(value, evidence_refs=refs(value.evidence_refs))

    def highlight(value: CandidateHighlight) -> CandidateHighlight:
        return replace(value, evidence_refs=refs(value.evidence_refs))

    def warning(value: CandidateWarning) -> CandidateWarning:
        return replace(value, evidence_refs=refs(value.evidence_refs))

    return replace(
        review,
        source_matches=tuple(source_match(value) for value in review.source_matches),
        fit_score=score(review.fit_score),
        diversification_score=score(review.diversification_score),
        redundancy_score=score(review.redundancy_score),
        highlights=tuple(highlight(value) for value in review.highlights),
        warnings=tuple(warning(value) for value in review.warnings),
        evidence_refs=tuple(replacements[value.evidence_id] for value in review.evidence_refs),
    )


def _freshness_state(
    ref: CandidateEvidenceRef,
    as_of: datetime,
    *,
    uses_undated_lookthrough: bool,
) -> str:
    if ref.source_domain == "candidate-economic-overlap" and uses_undated_lookthrough:
        return "unknown"
    policy = freshness_policy_for_domain(ref.source_domain)
    if policy.current_days is None:
        return "unknown"
    return "current" if evidence_age_days(ref, as_of) <= policy.current_days else "stale"


def _is_expired(ref: CandidateEvidenceRef, as_of: datetime) -> bool:
    policy = freshness_policy_for_domain(ref.source_domain)
    if policy.block_days is None:
        return False
    return evidence_age_days(ref, as_of) > policy.block_days


def _merge_evidence(
    *groups: tuple[CandidateEvidenceRef, ...],
) -> tuple[CandidateEvidenceRef, ...]:
    by_id: dict[str, CandidateEvidenceRef] = {}
    for ref in (ref for group in groups for ref in group):
        existing = by_id.get(ref.evidence_id)
        if existing is not None and existing != ref:
            raise ValueError("identical evidence IDs must identify identical evidence")
        by_id[ref.evidence_id] = ref
    return tuple(by_id[key] for key in sorted(by_id))


def _highlight_evidence(
    highlights: tuple[CandidateHighlight, ...],
) -> tuple[CandidateEvidenceRef, ...]:
    return _merge_evidence(
        tuple(ref for highlight in highlights for ref in highlight.evidence_refs)
    )


def _worse_eligibility(current: str, effect: str) -> str:
    effect_state = {"none": "eligible", "downgrade": "downgraded", "block": "blocked"}[effect]
    rank = {"eligible": 0, "downgraded": 1, "blocked": 2}
    return current if rank[current] >= rank[effect_state] else effect_state


def _known_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"unknown", "unclassified", "other"}:
        return None
    return normalized


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("candidate guardrail as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _as_db_timestamp(value: datetime) -> datetime:
    return _normalize_as_of(value).replace(tzinfo=None)


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return aware.astimezone(timezone.utc).replace(microsecond=0)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def _table_exists(conn: Any, table_name: str) -> bool:
    return bool(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()[0]
    )
