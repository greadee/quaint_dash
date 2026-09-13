"""Deterministic candidate score construction and stable ordering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

from dashboard.rules_and_data.candidates.canonical import (
    candidate_id,
    candidate_review_id,
    canonical_hash,
)
from dashboard.rules_and_data.candidates.guardrails import CandidateGuardrailPolicy
from dashboard.rules_and_data.candidates.models import (
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CandidateEvidenceRef,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidateReview,
    CandidateScore,
    CandidateScoreComponent,
    CandidateWarning,
)
from dashboard.rules_and_data.candidates.portfolio_sources import (
    PORTFOLIO_ANALYTICS_SCHEMA_VERSION,
    candidate_profile_conflict,
    candidate_profile_evidence,
)
from dashboard.rules_and_data.candidates.screen_adapters import (
    MOMENTUM_SCREEN_SCHEMA_VERSION,
    QUALITY_SCREEN_SCHEMA_VERSION,
    VALUE_SCREEN_SCHEMA_VERSION,
)
from dashboard.rules_and_data.candidates.source_adapters import candidate_source_evidence
from dashboard.rules_and_data.candidates.universe import (
    CandidateAssetIdentityResolver,
    CandidatePoolItem,
    CandidatePoolResult,
)
from dashboard.rules_and_data.models import InvestorProfile

CANDIDATE_SCORING_POLICY_VERSION = "candidate-scoring.v1"
CANDIDATE_METRIC_SCHEMA_VERSION = "candidate-score-inputs.v1"
CANDIDATE_OVERLAP_SCHEMA_VERSION = "candidate-economic-overlap.v1"
SCORING_METHODOLOGY_AS_OF = datetime(2026, 8, 7, tzinfo=timezone.utc)

HYPOTHETICAL_ALLOCATION_WEIGHT = 0.05
MATERIAL_REDUNDANCY_SCORE = 50.0
UNKNOWN_CLASSIFICATIONS = frozenset(
    {"", "unknown", "unclassified", "other", "broad market"}
)
FIT_WEIGHTS = {
    "growth": Decimal("0.16"),
    "value": Decimal("0.20"),
    "quality": Decimal("0.20"),
    "income": Decimal("0.12"),
    "speculative": Decimal("0.12"),
    "source_support": Decimal("0.20"),
}


@dataclass(frozen=True)
class CandidateScoringResult:
    portfolio_id: int
    as_of: datetime
    policy_version: str
    ordered_reviews: tuple[CandidateReview, ...]

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("candidate scoring as_of must be timezone-aware")
        if self.as_of.microsecond:
            raise ValueError("candidate scoring as_of must use whole-second precision")
        if self.policy_version != CANDIDATE_SCORING_POLICY_VERSION:
            raise ValueError("unsupported candidate scoring policy")
        expected = tuple(sorted(self.ordered_reviews, key=candidate_review_sort_key))
        if self.ordered_reviews != expected:
            raise ValueError("candidate scoring reviews must use the documented order")

    @property
    def output_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True)
class _MetricValue:
    value: float
    evidence_refs: tuple[CandidateEvidenceRef, ...]


@dataclass(frozen=True)
class _CandidateMetrics:
    factors: dict[str, _MetricValue]
    valuation: _MetricValue | None
    quality: _MetricValue | None
    momentum: _MetricValue | None
    risk: _MetricValue | None
    sentiment: _MetricValue | None
    sector: str | None
    geography: str | None
    classification_evidence: tuple[CandidateEvidenceRef, ...]


@dataclass(frozen=True)
class _PortfolioSnapshot:
    payload: dict[str, Any]
    evidence: CandidateEvidenceRef


class CandidateScoringEngine:
    """Build explainable reviews from one frozen candidate pool and profile."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self.identity = CandidateAssetIdentityResolver(conn)
        self.guardrails = CandidateGuardrailPolicy(conn)

    def score(
        self,
        *,
        pool: CandidatePoolResult,
        investor_profile: InvestorProfile,
        run_id: str,
    ) -> CandidateScoringResult:
        as_of = _normalize_as_of(pool.as_of)
        profile_evidence = candidate_profile_evidence(investor_profile, "scoring")
        profile_conflict = self._profile_conflict(
            investor_profile,
            pool.portfolio_id,
            as_of,
        )
        portfolio_snapshot = self._portfolio_snapshot(pool.portfolio_id, as_of)
        reviews = tuple(
            self._review(
                item=item,
                pool=pool,
                investor_profile=investor_profile,
                profile_evidence=profile_evidence,
                profile_conflict=profile_conflict,
                portfolio_snapshot=portfolio_snapshot,
                run_id=run_id,
            )
            for item in pool.candidates
        )
        reviews = self.guardrails.apply(
            portfolio_id=pool.portfolio_id,
            as_of=as_of,
            reviews=reviews,
        )
        return CandidateScoringResult(
            portfolio_id=pool.portfolio_id,
            as_of=as_of,
            policy_version=CANDIDATE_SCORING_POLICY_VERSION,
            ordered_reviews=tuple(sorted(reviews, key=candidate_review_sort_key)),
        )

    def _review(
        self,
        *,
        item: CandidatePoolItem,
        pool: CandidatePoolResult,
        investor_profile: InvestorProfile,
        profile_evidence: CandidateEvidenceRef,
        profile_conflict: str | None,
        portfolio_snapshot: _PortfolioSnapshot | None,
        run_id: str,
    ) -> CandidateReview:
        if profile_conflict is not None:
            return _blocked_profile_review(
                item=item,
                pool=pool,
                run_id=run_id,
                profile_evidence=profile_evidence,
                reason_code=profile_conflict,
            )

        metrics = self._candidate_metrics(item, pool.as_of)
        missing: list[CandidateMissingMetric] = []
        fit = self._fit_score(
            item=item,
            profile=investor_profile,
            profile_evidence=profile_evidence,
            metrics=metrics,
            missing=missing,
        )
        diversification = self._diversification_score(
            metrics=metrics,
            portfolio_snapshot=portfolio_snapshot,
            missing=missing,
        )
        redundancy = self._redundancy_score(
            item=item,
            portfolio_snapshot=portfolio_snapshot,
            as_of=pool.as_of,
            missing=missing,
        )
        highlights = self._highlights(metrics=metrics, as_of=pool.as_of, missing=missing)

        critical_missing = any(metric.criticality == "critical" for metric in missing)
        warnings: tuple[CandidateWarning, ...] = ()
        eligibility = "eligible"
        evidence_for_warning = _merge_evidence(
            item.evidence_refs,
            fit.evidence_refs,
            diversification.evidence_refs,
            redundancy.evidence_refs,
            tuple(ref for highlight in highlights for ref in highlight.evidence_refs),
        )
        if critical_missing:
            eligibility = "blocked"
            warnings = (
                CandidateWarning(
                    warning_code="guardrail.scoring.critical_evidence_missing",
                    severity="critical",
                    blocking=True,
                    evidence_refs=evidence_for_warning or item.evidence_refs,
                ),
            )
        elif redundancy.value is not None and redundancy.value >= _decimal(
            MATERIAL_REDUNDANCY_SCORE
        ):
            eligibility = "downgraded"

        evidence = _merge_evidence(
            item.evidence_refs,
            fit.evidence_refs,
            diversification.evidence_refs,
            redundancy.evidence_refs,
            tuple(ref for highlight in highlights for ref in highlight.evidence_refs),
            tuple(ref for warning in warnings for ref in warning.evidence_refs),
        )
        reasons = tuple(
            sorted(
                {
                    *item.reason_codes,
                    *(warning.warning_code for warning in warnings),
                }
            )
        )
        stable_candidate_id = candidate_id(item.asset_id)
        return CandidateReview(
            review_id=candidate_review_id(run_id, stable_candidate_id),
            run_id=run_id,
            candidate_id=stable_candidate_id,
            asset_id=item.asset_id,
            ticker=item.ticker,
            schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
            methodology_version=CANDIDATE_METHODOLOGY_VERSION,
            reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
            reason_codes=reasons,
            source_matches=item.source_matches,
            fit_score=fit,
            diversification_score=diversification,
            redundancy_score=redundancy,
            highlights=tuple(sorted(highlights, key=lambda value: (value.category, value.highlight_code))),
            missing_metrics=tuple(sorted(set(missing), key=lambda value: value.metric_code)),
            warnings=warnings,
            evidence_refs=evidence,
            data_as_of=_normalize_as_of(pool.as_of),
            methodology_as_of=SCORING_METHODOLOGY_AS_OF,
            eligibility_state=eligibility,
        )

    @staticmethod
    def _profile_conflict(
        profile: InvestorProfile,
        portfolio_id: int,
        as_of: datetime,
    ) -> str | None:
        for dimension in ("sector", "country"):
            conflict = candidate_profile_conflict(
                profile,
                as_of,
                dimension,
                expected_portfolio_id=portfolio_id,
            )
            if conflict is not None:
                return conflict
        factors = {item.code: item for item in profile.factor_scores}
        if any(
            code not in factors
            or factors[code].score is None
            or factors[code].confidence < 0.50
            for code in ("growth", "value", "quality", "income", "speculative")
        ):
            return "guardrail.profile.factor_coverage_conflict"
        return None

    def _fit_score(
        self,
        *,
        item: CandidatePoolItem,
        profile: InvestorProfile,
        profile_evidence: CandidateEvidenceRef,
        metrics: _CandidateMetrics,
        missing: list[CandidateMissingMetric],
    ) -> CandidateScore:
        profile_factors = {value.code: value for value in profile.factor_scores}
        components: list[CandidateScoreComponent] = []
        for code in ("growth", "value", "quality", "income", "speculative"):
            candidate_metric = metrics.factors.get(code)
            profile_metric = profile_factors.get(code)
            if candidate_metric is None or profile_metric is None or profile_metric.score is None:
                missing.append(
                    _missing_metric(
                        f"metric.fit.{code}",
                        criticality="noncritical",
                        expected_source="candidate-factor-and-investor-profile",
                        reason_code=f"missing.fit.{code}",
                        effect="none",
                    )
                )
                continue
            alignment = max(0.0, 100.0 - abs(candidate_metric.value - profile_metric.score))
            weight = FIT_WEIGHTS[code]
            refs = _merge_evidence((profile_evidence,), candidate_metric.evidence_refs)
            components.append(
                _component(
                    code=f"score.fit.{code}_alignment",
                    value=alignment,
                    weight=weight,
                    reason_code=f"score.fit.{code}_alignment",
                    evidence=refs,
                )
            )

        source_support = _source_support_score(item)
        components.append(
            _component(
                code="score.fit.source_support",
                value=source_support,
                weight=FIT_WEIGHTS["source_support"],
                reason_code="score.fit.source_support",
                evidence=item.evidence_refs,
            )
        )
        evidence = _merge_evidence(
            tuple(ref for component in components for ref in component.evidence_refs)
        )
        if len(components) != 6:
            missing.append(
                _missing_metric(
                    "metric.fit.factor_alignment",
                    criticality="critical",
                    expected_source="candidate-factor-and-investor-profile",
                    reason_code="missing.fit.factor_alignment",
                    effect="block",
                )
            )
            return CandidateScore(
                score_type="fit",
                value=None,
                components=tuple(components),
                evidence_refs=evidence,
                missing_metric_code="metric.fit.factor_alignment",
            )
        return CandidateScore(
            score_type="fit",
            value=sum((component.contribution for component in components), Decimal("0")),
            components=tuple(components),
            evidence_refs=evidence,
        )

    def _diversification_score(
        self,
        *,
        metrics: _CandidateMetrics,
        portfolio_snapshot: _PortfolioSnapshot | None,
        missing: list[CandidateMissingMetric],
    ) -> CandidateScore:
        components: list[CandidateScoreComponent] = []
        if portfolio_snapshot is not None:
            decomposition = _json_object(portfolio_snapshot.payload.get("risk_decomposition"))
            dimensions = (
                ("sector", metrics.sector, decomposition.get("sector_exposure")),
                ("geography", metrics.geography, decomposition.get("country_exposure")),
            )
            for code, candidate_key, raw_exposure in dimensions:
                exposures = _valid_exposures(raw_exposure)
                if candidate_key is None or exposures is None:
                    missing.append(
                        _missing_metric(
                            f"metric.diversification.{code}",
                            criticality="noncritical",
                            expected_source="portfolio-analytics-and-classification",
                            reason_code=f"missing.diversification.{code}",
                            effect="none",
                        )
                    )
                    continue
                value = diversification_effect_score(
                    exposures,
                    candidate_key,
                    allocation_weight=HYPOTHETICAL_ALLOCATION_WEIGHT,
                )
                refs = _merge_evidence(
                    (portfolio_snapshot.evidence,),
                    metrics.classification_evidence,
                )
                components.append(
                    _component(
                        code=f"score.diversification.{code}_effect",
                        value=value,
                        weight=Decimal("0.50"),
                        reason_code=f"score.diversification.{code}_effect",
                        evidence=refs,
                    )
                )
        if len(components) != 2:
            missing.append(
                _missing_metric(
                    "metric.diversification.coverage",
                    criticality="critical",
                    expected_source="portfolio-analytics-and-classification",
                    reason_code="missing.diversification.coverage",
                    effect="block",
                )
            )
            evidence = _merge_evidence(
                tuple(ref for component in components for ref in component.evidence_refs)
            )
            return CandidateScore(
                score_type="diversification",
                value=None,
                components=tuple(components),
                evidence_refs=evidence,
                missing_metric_code="metric.diversification.coverage",
            )
        evidence = _merge_evidence(
            tuple(ref for component in components for ref in component.evidence_refs)
        )
        return CandidateScore(
            score_type="diversification",
            value=sum((component.contribution for component in components), Decimal("0")),
            components=tuple(components),
            evidence_refs=evidence,
        )

    def _redundancy_score(
        self,
        *,
        item: CandidatePoolItem,
        portfolio_snapshot: _PortfolioSnapshot | None,
        as_of: datetime,
        missing: list[CandidateMissingMetric],
    ) -> CandidateScore:
        overlap = self._economic_overlap(item, portfolio_snapshot, as_of)
        if overlap is None:
            missing.append(
                _missing_metric(
                    "metric.redundancy.economic_overlap",
                    criticality="critical",
                    expected_source="portfolio-positions-and-etf-lookthrough",
                    reason_code="missing.redundancy.economic_overlap",
                    effect="block",
                )
            )
            return CandidateScore(
                score_type="redundancy",
                value=None,
                components=(),
                evidence_refs=(),
                missing_metric_code="metric.redundancy.economic_overlap",
            )
        value, evidence = overlap
        component = _component(
            code="score.redundancy.economic_overlap",
            value=value,
            weight=Decimal("1"),
            reason_code="score.redundancy.economic_overlap",
            evidence=(evidence,),
        )
        return CandidateScore(
            score_type="redundancy",
            value=_decimal(value),
            components=(component,),
            evidence_refs=(evidence,),
        )

    def _candidate_metrics(
        self,
        item: CandidatePoolItem,
        as_of: datetime,
    ) -> _CandidateMetrics:
        factor = self._factor_snapshot(item.asset_id, as_of)
        analytics = self._analytics_snapshot(item.asset_id, as_of)
        quality = self._quality_snapshot(item.asset_id, as_of)
        sentiment = self._sentiment_snapshot(item.asset_id, as_of)
        sector, geography, classification_evidence = self._classification(
            item.asset_id,
            as_of,
        )

        factors: dict[str, _MetricValue] = {}
        if factor is not None:
            values, evidence = factor
            direct_mapping = {
                "growth": values.get("growth_score"),
                "value": values.get("value_score"),
                "quality": values.get("quality_score"),
                "income": values.get("dividend_score"),
            }
            for code, value in direct_mapping.items():
                if value is not None:
                    factors[code] = _MetricValue(float(value), (evidence,))
            if values.get("volatility_score") is not None:
                factors["speculative"] = _MetricValue(
                    100.0 - float(values["volatility_score"]),
                    (evidence,),
                )

        valuation_metric: _MetricValue | None = None
        risk_metric: _MetricValue | None = None
        momentum_metric: _MetricValue | None = None
        if analytics is not None:
            values, evidence = analytics
            if "value_score" in values:
                valuation_metric = _MetricValue(values["value_score"], (evidence,))
                factors.setdefault("value", valuation_metric)
            if "growth_score" in values:
                factors.setdefault("growth", _MetricValue(values["growth_score"], (evidence,)))
            if "risk_score" in values:
                risk_metric = _MetricValue(values["risk_score"], (evidence,))
                factors.setdefault("speculative", risk_metric)
        if quality is not None:
            quality_metric = quality
            factors["quality"] = quality_metric
        else:
            quality_metric = factors.get("quality")
        if factor is not None and factor[0].get("momentum_score") is not None:
            momentum_metric = _MetricValue(float(factor[0]["momentum_score"]), (factor[1],))
        if risk_metric is None:
            risk_metric = factors.get("speculative")

        return _CandidateMetrics(
            factors=factors,
            valuation=valuation_metric or factors.get("value"),
            quality=quality_metric,
            momentum=momentum_metric,
            risk=risk_metric,
            sentiment=sentiment,
            sector=sector,
            geography=geography,
            classification_evidence=classification_evidence,
        )

    def _factor_snapshot(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> tuple[dict[str, float | None], CandidateEvidenceRef] | None:
        if not _table_exists(self.conn, "ticker_factor_snapshot"):
            return None
        row = self.conn.execute(
            """
            SELECT
                snapshot_date, growth_score, value_score, quality_score,
                momentum_score, defensive_score, dividend_score,
                volatility_score, overall_factor_score, factor_labels_json,
                explanation
            FROM ticker_factor_snapshot
            WHERE asset_id = ?
              AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [asset_id, as_of.date()],
        ).fetchone()
        if row is None:
            return None
        keys = (
            "growth_score",
            "value_score",
            "quality_score",
            "momentum_score",
            "defensive_score",
            "dividend_score",
            "volatility_score",
            "overall_factor_score",
        )
        values = {
            key: _bounded_score_or_none(row[index + 1])
            for index, key in enumerate(keys)
        }
        evidence = candidate_source_evidence(
            source_domain="ticker-factor",
            source_schema_version=MOMENTUM_SCREEN_SCHEMA_VERSION,
            source_record_id=f"ticker-factor:{row[0].isoformat()}:{asset_id}",
            as_of=_as_utc(row[0]),
            payload={
                "asset_id": asset_id,
                "snapshot_date": row[0],
                **values,
                "factor_labels_json": row[9],
                "explanation": row[10],
            },
        )
        return values, evidence

    def _analytics_snapshot(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> tuple[dict[str, float], CandidateEvidenceRef] | None:
        if not _table_exists(self.conn, "asset_analytics_snapshot"):
            return None
        row = self.conn.execute(
            """
            SELECT snapshot_date, payload_json
            FROM asset_analytics_snapshot
            WHERE asset_id = ?
              AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [asset_id, as_of.date()],
        ).fetchone()
        if row is None:
            return None
        payload = _json_object(row[1])
        dcf = _json_object(payload.get("discounted_cash_flow"))
        ddm = _json_object(payload.get("dividend_discount"))
        depth = _json_object(payload.get("valuation_depth"))
        risk = _json_object(payload.get("risk"))
        margins = tuple(
            float(value)
            for value in (dcf.get("margin_of_safety"), ddm.get("margin_of_safety"))
            if isinstance(value, (int, float))
        )
        growth_values = tuple(
            float(value)
            for value in (
                depth.get("revenue_growth_yoy"),
                depth.get("eps_growth_yoy"),
                depth.get("free_cash_flow_growth_yoy"),
            )
            if isinstance(value, (int, float))
        )
        values: dict[str, float] = {}
        if margins:
            values["value_score"] = value_score_from_margin(sum(margins) / len(margins))
        if growth_values:
            values["growth_score"] = growth_score_from_rate(
                sum(growth_values) / len(growth_values)
            )
        volatility = risk.get("annualized_volatility")
        if isinstance(volatility, (int, float)):
            values["risk_score"] = speculative_score_from_volatility(float(volatility))
        evidence = candidate_source_evidence(
            source_domain="asset-analytics-scoring",
            source_schema_version=VALUE_SCREEN_SCHEMA_VERSION,
            source_record_id=f"asset-analytics:{row[0].isoformat()}:{asset_id}",
            as_of=_as_utc(row[0]),
            payload={
                "asset_id": asset_id,
                "snapshot_date": row[0],
                "margin_of_safety_values": margins,
                "growth_values": growth_values,
                "annualized_volatility": volatility,
                "normalized_values": values,
            },
        )
        return values, evidence

    def _quality_snapshot(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> _MetricValue | None:
        row = self.conn.execute(
            """
            SELECT
                run.id, run.analysis_date, run.source_data_as_of,
                run.overall_score, run.confidence_score, run.completeness_score,
                run.status, methodology.version
            FROM business_strength_analysis_run run
            JOIN business_strength_methodology methodology
              ON methodology.id = run.methodology_id
            WHERE run.asset_id = ?
              AND run.analysis_date <= ?
              AND (run.source_data_as_of IS NULL OR run.source_data_as_of <= ?)
              AND run.status IN ('complete', 'partial')
              AND run.overall_score IS NOT NULL
            ORDER BY run.analysis_date DESC, run.id DESC
            LIMIT 1
            """,
            [asset_id, as_of.date(), _as_db_timestamp(as_of)],
        ).fetchone()
        if row is None:
            return None
        evidence = candidate_source_evidence(
            source_domain="business-strength-scorecard",
            source_schema_version=QUALITY_SCREEN_SCHEMA_VERSION,
            source_record_id=f"business-strength-run:{row[0]}",
            as_of=_as_utc(row[2] if row[2] is not None else row[1]),
            payload={
                "analysis_run_id": row[0],
                "asset_id": asset_id,
                "analysis_date": row[1],
                "source_data_as_of": (
                    _as_utc(row[2]) if row[2] is not None else None
                ),
                "overall_score": row[3],
                "confidence_score": row[4],
                "completeness_score": row[5],
                "status": row[6],
                "source_methodology_version": row[7],
            },
        )
        score = _bounded_score_or_none(row[3])
        return _MetricValue(score, (evidence,)) if score is not None else None

    def _sentiment_snapshot(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> _MetricValue | None:
        row = self.conn.execute(
            """
            SELECT
                date, blended_sentiment_score, retail_sentiment_score,
                news_sentiment_score, analyst_sentiment_score,
                reddit_post_count, x_post_count, article_count
            FROM ticker_sentiment_daily
            WHERE asset_id = ?
              AND date <= ?
              AND blended_sentiment_score IS NOT NULL
            ORDER BY date DESC
            LIMIT 1
            """,
            [asset_id, as_of.date()],
        ).fetchone()
        if row is None:
            return None
        normalized = max(0.0, min(100.0, (float(row[1]) + 1.0) * 50.0))
        evidence = candidate_source_evidence(
            source_domain="ticker-sentiment",
            source_schema_version=CANDIDATE_METRIC_SCHEMA_VERSION,
            source_record_id=f"ticker-sentiment:{row[0].isoformat()}:{asset_id}",
            as_of=_as_utc(row[0]),
            payload={
                "asset_id": asset_id,
                "date": row[0],
                "blended_sentiment_score": row[1],
                "retail_sentiment_score": row[2],
                "news_sentiment_score": row[3],
                "analyst_sentiment_score": row[4],
                "reddit_post_count": row[5],
                "x_post_count": row[6],
                "article_count": row[7],
                "normalized_score": normalized,
            },
        )
        return _MetricValue(normalized, (evidence,))

    def _classification(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> tuple[str | None, str | None, tuple[CandidateEvidenceRef, ...]]:
        row = self.conn.execute(
            """
            SELECT
                classification.sector,
                asset.country,
                classification.industry,
                classification.template_code,
                classification.classification_source,
                classification.confidence,
                classification.effective_from,
                classification.effective_to,
                asset.updated_at
            FROM asset_business_classification classification
            LEFT JOIN asset
              ON asset.asset_id = classification.asset_id
             AND asset.updated_at <= ?
            WHERE classification.asset_id = ?
              AND classification.effective_from <= ?
              AND (
                classification.effective_to IS NULL
                OR classification.effective_to >= ?
              )
            ORDER BY classification.effective_from DESC
            LIMIT 1
            """,
            [_as_db_timestamp(as_of), asset_id, as_of.date(), as_of.date()],
        ).fetchone()
        if row is None:
            asset = self.conn.execute(
                """
                SELECT sector, country, industry, updated_at
                FROM asset
                WHERE asset_id = ? AND updated_at <= ?
                """,
                [asset_id, _as_db_timestamp(as_of)],
            ).fetchone()
            if asset is None:
                return None, None, ()
            evidence = candidate_source_evidence(
                source_domain="asset-classification",
                source_schema_version=CANDIDATE_METRIC_SCHEMA_VERSION,
                source_record_id=f"asset:{asset_id}",
                as_of=_as_utc(asset[3]),
                payload={
                    "asset_id": asset_id,
                    "sector": asset[0],
                    "country": asset[1],
                    "industry": asset[2],
                    "coverage": "current_state",
                },
            )
            return _known_label(asset[0]), _known_label(asset[1]), (evidence,)
        evidence = candidate_source_evidence(
            source_domain="asset-business-classification",
            source_schema_version=CANDIDATE_METRIC_SCHEMA_VERSION,
            source_record_id=f"classification:{asset_id}:{row[6].isoformat()}",
            as_of=_as_utc(row[6]),
            payload={
                "asset_id": asset_id,
                "sector": row[0],
                "country": row[1],
                "industry": row[2],
                "template_code": row[3],
                "classification_source": row[4],
                "confidence": row[5],
                "effective_from": row[6],
                "effective_to": row[7],
                "asset_updated_at": _as_utc(row[8]) if row[8] is not None else None,
            },
        )
        return _known_label(row[0]), _known_label(row[1]), (evidence,)

    def _portfolio_snapshot(
        self,
        portfolio_id: int,
        as_of: datetime,
    ) -> _PortfolioSnapshot | None:
        row = self.conn.execute(
            """
            SELECT snapshot_date, payload_json, state_signature, refreshed_at
            FROM portfolio_analytics_snapshot
            WHERE portfolio_id = ?
              AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            [portfolio_id, as_of.date()],
        ).fetchone()
        if row is None:
            return None
        payload = _json_object(row[1])
        evidence = candidate_source_evidence(
            source_domain="portfolio-analytics-scoring",
            source_schema_version=PORTFOLIO_ANALYTICS_SCHEMA_VERSION,
            source_record_id=f"portfolio:{portfolio_id}:{row[0].isoformat()}:{row[2]}",
            as_of=_as_utc(row[0]),
            payload={
                "portfolio_id": portfolio_id,
                "snapshot_date": row[0],
                "state_signature": row[2],
                "positions": payload.get("positions"),
                "risk_decomposition": payload.get("risk_decomposition"),
            },
        )
        return _PortfolioSnapshot(payload=payload, evidence=evidence)

    def _economic_overlap(
        self,
        item: CandidatePoolItem,
        portfolio_snapshot: _PortfolioSnapshot | None,
        as_of: datetime,
    ) -> tuple[float, CandidateEvidenceRef] | None:
        if portfolio_snapshot is None:
            return None
        positions = portfolio_snapshot.payload.get("positions")
        if not isinstance(positions, list) or not positions:
            return None
        portfolio_map: dict[str, float] = {}
        for position in positions:
            if not isinstance(position, dict):
                return None
            held_asset_id = str(position.get("asset_id") or "").strip()
            weight = _float_or_none(position.get("weight"))
            if not held_asset_id or weight is None or weight < 0:
                return None
            exposure = self._asset_exposure_map(held_asset_id, as_of)
            if exposure is None:
                return None
            for key, exposure_weight in exposure.items():
                portfolio_map[key] = portfolio_map.get(key, 0.0) + weight * exposure_weight
        candidate_map = self._asset_exposure_map(item.asset_id, as_of)
        if candidate_map is None:
            return None
        overlap_ratio = min(
            1.0,
            sum(
                min(candidate_weight, portfolio_map.get(key, 0.0))
                for key, candidate_weight in candidate_map.items()
            ),
        )
        overlap_score = round(overlap_ratio * 100.0, 8)
        evidence = candidate_source_evidence(
            source_domain="candidate-economic-overlap",
            source_schema_version=CANDIDATE_OVERLAP_SCHEMA_VERSION,
            source_record_id=(
                f"overlap:{portfolio_snapshot.evidence.source_record_id}:{item.asset_id}"
            ),
            as_of=_normalize_as_of(as_of),
            payload={
                "candidate_asset_id": item.asset_id,
                "candidate_exposures": candidate_map,
                "portfolio_exposures": portfolio_map,
                "overlap_ratio": overlap_ratio,
                "overlap_score": overlap_score,
                "etf_lookthrough_coverage": "current_state_when_available",
                "policy_version": CANDIDATE_SCORING_POLICY_VERSION,
            },
        )
        return overlap_score, evidence

    def _asset_exposure_map(
        self,
        asset_id: str,
        as_of: datetime,
    ) -> dict[str, float] | None:
        asset_row = self.conn.execute(
            """
            SELECT asset_type, asset_subtype, symbol
            FROM asset
            WHERE asset_id = ? AND updated_at <= ?
            """,
            [asset_id, _as_db_timestamp(as_of)],
        ).fetchone()
        if asset_row is None:
            return None
        is_etf = str(asset_row[0] or "").lower() == "etf" or str(
            asset_row[1] or ""
        ).lower() == "etf"
        if is_etf:
            if not _table_exists(self.conn, "etf_holding"):
                return None
            rows = self.conn.execute(
                """
                SELECT holding_symbol, weight_pct
                FROM etf_holding
                WHERE asset_id = ?
                  AND holding_symbol IS NOT NULL
                  AND weight_pct IS NOT NULL
                  AND weight_pct > 0
                ORDER BY holding_symbol
                """,
                [asset_id],
            ).fetchall()
            if not rows:
                return None
            exposures: dict[str, float] = {}
            for symbol, raw_weight in rows:
                weight = _normalize_weight(float(raw_weight))
                identity = self.identity.resolve(
                    asset_id=str(symbol).upper(),
                    ticker=str(symbol).upper(),
                    as_of=as_of,
                )
                key = identity.economic_exposure_id
                exposures[key] = exposures.get(key, 0.0) + weight
            total = sum(exposures.values())
            if total <= 0 or total > 1.05:
                return None
            residual = max(0.0, 1.0 - total)
            if residual:
                identity = self.identity.resolve(
                    asset_id=asset_id,
                    ticker=str(asset_row[2] or asset_id).upper(),
                    as_of=as_of,
                )
                exposures[identity.economic_exposure_id] = residual
            return exposures
        identity = self.identity.resolve(
            asset_id=asset_id,
            ticker=str(asset_row[2] or asset_id).upper(),
            as_of=as_of,
        )
        return {identity.economic_exposure_id: 1.0} if identity.resolved else None

    @staticmethod
    def _highlights(
        *,
        metrics: _CandidateMetrics,
        as_of: datetime,
        missing: list[CandidateMissingMetric],
    ) -> tuple[CandidateHighlight, ...]:
        definitions = (
            ("valuation", "highlight.valuation.normalized", metrics.valuation, False),
            ("quality", "highlight.quality.business_strength", metrics.quality, False),
            ("momentum", "highlight.momentum.factor", metrics.momentum, False),
            ("risk", "highlight.risk.intensity", metrics.risk, True),
            ("sentiment", "highlight.sentiment.blended", metrics.sentiment, False),
        )
        highlights: list[CandidateHighlight] = []
        for category, code, metric, inverse in definitions:
            if metric is None:
                missing.append(
                    _missing_metric(
                        f"metric.highlight.{category}",
                        criticality="noncritical",
                        expected_source=f"candidate-{category}-snapshot",
                        reason_code=f"missing.highlight.{category}",
                        effect="none",
                    )
                )
                continue
            highlights.append(
                CandidateHighlight(
                    category=category,
                    highlight_code=code,
                    normalized_value=_decimal(metric.value),
                    unit="score_0_100",
                    direction=_highlight_direction(metric.value, inverse=inverse),
                    as_of=max(ref.as_of for ref in metric.evidence_refs),
                    evidence_refs=metric.evidence_refs,
                )
            )
        return tuple(highlights)


def candidate_review_sort_key(review: CandidateReview) -> tuple[Any, ...]:
    eligibility_rank = {"eligible": 0, "downgraded": 1, "blocked": 2}
    return (
        eligibility_rank[review.eligibility_state],
        _descending(review.fit_score.value),
        _descending(review.diversification_score.value),
        review.redundancy_score.value
        if review.redundancy_score.value is not None
        else Decimal("101"),
        -len({ref.source_domain for ref in review.evidence_refs}),
        review.asset_id,
    )


def diversification_effect_score(
    exposures: dict[str, float],
    candidate_key: str,
    *,
    allocation_weight: float = HYPOTHETICAL_ALLOCATION_WEIGHT,
) -> float:
    if allocation_weight <= 0 or allocation_weight >= 1:
        raise ValueError("hypothetical allocation weight must be between zero and one")
    normalized_key = candidate_key.strip().lower()
    if normalized_key in UNKNOWN_CLASSIFICATIONS:
        raise ValueError("candidate diversification classification must be known")
    total = sum(exposures.values())
    if total < 0.95 or total > 1.05:
        raise ValueError("diversification exposures must total 95% to 105%")
    normalized = {key: value / total for key, value in exposures.items()}
    before = sum(value * value for value in normalized.values())
    after = {
        key: value * (1.0 - allocation_weight)
        for key, value in normalized.items()
    }
    matching_key = next(
        (key for key in after if key.strip().lower() == normalized_key),
        candidate_key,
    )
    after[matching_key] = after.get(matching_key, 0.0) + allocation_weight
    after_hhi = sum(value * value for value in after.values())
    maximum_reduction = 2.0 * allocation_weight * (1.0 - allocation_weight)
    return round(
        max(0.0, min(100.0, ((before - after_hhi) / maximum_reduction) * 100.0)),
        8,
    )


def value_score_from_margin(margin: float) -> float:
    return round(max(0.0, min(100.0, ((margin + 0.25) / 0.75) * 100.0)), 8)


def growth_score_from_rate(rate: float) -> float:
    return round(max(0.0, min(100.0, ((rate + 0.10) / 0.40) * 100.0)), 8)


def speculative_score_from_volatility(volatility: float) -> float:
    return round(max(0.0, min(100.0, ((volatility - 0.10) / 0.50) * 100.0)), 8)


def _blocked_profile_review(
    *,
    item: CandidatePoolItem,
    pool: CandidatePoolResult,
    run_id: str,
    profile_evidence: CandidateEvidenceRef,
    reason_code: str,
) -> CandidateReview:
    missing = tuple(
        _missing_metric(
            f"metric.{score_type}.profile_compatibility",
            criticality="critical",
            expected_source="investor-profile",
            reason_code=reason_code,
            effect="block",
        )
        for score_type in ("fit", "diversification", "redundancy")
    )
    scores = {
        score_type: CandidateScore(
            score_type=score_type,
            value=None,
            components=(),
            evidence_refs=(),
            missing_metric_code=f"metric.{score_type}.profile_compatibility",
        )
        for score_type in ("fit", "diversification", "redundancy")
    }
    warning = CandidateWarning(
        warning_code=reason_code,
        severity="critical",
        blocking=True,
        evidence_refs=(profile_evidence,),
    )
    evidence = _merge_evidence(item.evidence_refs, (profile_evidence,))
    stable_candidate_id = candidate_id(item.asset_id)
    return CandidateReview(
        review_id=candidate_review_id(run_id, stable_candidate_id),
        run_id=run_id,
        candidate_id=stable_candidate_id,
        asset_id=item.asset_id,
        ticker=item.ticker,
        schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        reason_codes=tuple(sorted({*item.reason_codes, reason_code})),
        source_matches=item.source_matches,
        fit_score=scores["fit"],
        diversification_score=scores["diversification"],
        redundancy_score=scores["redundancy"],
        highlights=(),
        missing_metrics=missing,
        warnings=(warning,),
        evidence_refs=evidence,
        data_as_of=_normalize_as_of(pool.as_of),
        methodology_as_of=SCORING_METHODOLOGY_AS_OF,
        eligibility_state="blocked",
    )


def _source_support_score(item: CandidatePoolItem) -> float:
    family_count = len({match.source_family for match in item.source_matches})
    domain_count = len({ref.source_domain for ref in item.evidence_refs})
    return min(100.0, 35.0 + (15.0 * (family_count - 1)) + (5.0 * (domain_count - 1)))


def _component(
    *,
    code: str,
    value: float,
    weight: Decimal,
    reason_code: str,
    evidence: tuple[CandidateEvidenceRef, ...],
) -> CandidateScoreComponent:
    normalized_value = _decimal(value)
    return CandidateScoreComponent(
        component_code=code,
        value=normalized_value,
        weight=weight,
        contribution=(normalized_value * weight).quantize(
            Decimal("0.00000001"),
            rounding=ROUND_HALF_EVEN,
        ),
        reason_codes=(reason_code,),
        evidence_refs=evidence,
    )


def _missing_metric(
    metric_code: str,
    *,
    criticality: str,
    expected_source: str,
    reason_code: str,
    effect: str,
) -> CandidateMissingMetric:
    return CandidateMissingMetric(
        metric_code=metric_code,
        criticality=criticality,
        expected_source=expected_source,
        reason_code=reason_code,
        guardrail_effect=effect,
    )


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


def _valid_exposures(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    parsed: dict[str, float] = {}
    total = 0.0
    known = 0.0
    for key, raw in value.items():
        if not isinstance(raw, (int, float)) or raw < 0:
            return None
        numeric = float(raw)
        total += numeric
        if str(key).strip().lower() not in UNKNOWN_CLASSIFICATIONS:
            parsed[str(key)] = numeric
            known += numeric
    if total < 0.95 or total > 1.05 or known < 0.75:
        return None
    return {key: numeric / known for key, numeric in parsed.items()}


def _known_label(value: Any) -> str | None:
    if value is None:
        return None
    label = str(value).strip()
    return None if label.lower() in UNKNOWN_CLASSIFICATIONS else label


def _highlight_direction(value: float, *, inverse: bool) -> str:
    if value >= 65:
        return "negative" if inverse else "positive"
    if value <= 35:
        return "positive" if inverse else "negative"
    return "neutral"


def _normalize_weight(value: float) -> float:
    return value / 100.0 if value > 1.0 else value


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("candidate scoring as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _as_db_timestamp(value: datetime) -> datetime:
    return _normalize_as_of(value).replace(tzinfo=None)


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc, microsecond=0)
        return value.astimezone(timezone.utc).replace(microsecond=0)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    return parsed if isinstance(parsed, dict) else {}


def _float_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _bounded_score_or_none(value: Any) -> float | None:
    numeric = _float_or_none(value)
    return numeric if numeric is not None and 0 <= numeric <= 100 else None


def _decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)


def _descending(value: Decimal | None) -> Decimal:
    return -(value if value is not None else Decimal("-1"))


def _table_exists(conn: Any, table_name: str) -> bool:
    return bool(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
    )
