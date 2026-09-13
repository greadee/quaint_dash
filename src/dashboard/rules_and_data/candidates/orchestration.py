"""Deterministic orchestration for persisted candidate-review runs."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from dashboard.rules_and_data.candidates.canonical import (
    candidate_review_id,
    candidate_run_id,
    canonical_hash,
    is_sha256,
)
from dashboard.rules_and_data.candidates.guardrails import CANDIDATE_GUARDRAIL_POLICY_VERSION
from dashboard.rules_and_data.candidates.models import (
    CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CANDIDATE_RUN_SCHEMA_VERSION,
    CandidateReview,
    CandidateRun,
)
from dashboard.rules_and_data.candidates.persistence import CandidateRunRepository
from dashboard.rules_and_data.candidates.portfolio_sources import (
    BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
    BUSINESS_PEER_SCHEMA_VERSION,
    PORTFOLIO_GAP_POLICY_VERSION,
    PROFILE_THEME_SCHEMA_VERSION,
)
from dashboard.rules_and_data.candidates.scoring import (
    CANDIDATE_SCORING_POLICY_VERSION,
    CandidateScoringEngine,
)
from dashboard.rules_and_data.candidates.screen_adapters import (
    MOMENTUM_SCREEN_SCHEMA_VERSION,
    QUALITY_SCREEN_SCHEMA_VERSION,
    SCREEN_POLICY_VERSION,
    VALUE_SCREEN_SCHEMA_VERSION,
)
from dashboard.rules_and_data.candidates.source_adapters import (
    ALL_UNIVERSE_SCHEMA_VERSION,
    BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
    CANDIDATE_SOURCE_ADAPTER_VERSION,
    STOCK_RANKING_SCHEMA_VERSION,
    WATCHLIST_SCHEMA_VERSION,
)
from dashboard.rules_and_data.candidates.universe import (
    IDENTITY_METHODOLOGY_VERSION,
    CandidatePoolResult,
    OutsideHoldingUniverseBuilder,
)
from dashboard.rules_and_data.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    InvestorProfile,
    ProfileDimension,
)

CANDIDATE_ORCHESTRATION_POLICY_VERSION = "candidate-orchestration.v1"

_SOURCE_SCHEMA_VERSIONS = {
    "asset-business-classification": BUSINESS_CLASSIFICATION_SCHEMA_VERSION,
    "asset-catalog-search": ALL_UNIVERSE_SCHEMA_VERSION,
    "asset-analytics-valuation": VALUE_SCREEN_SCHEMA_VERSION,
    "benchmark-composition": BENCHMARK_CONSTITUENT_SCHEMA_VERSION,
    "business-strength-peer-groups": BUSINESS_PEER_SCHEMA_VERSION,
    "business-strength-scorecard": QUALITY_SCREEN_SCHEMA_VERSION,
    "portfolio-geography-gap": PORTFOLIO_GAP_POLICY_VERSION,
    "portfolio-sector-gap": PORTFOLIO_GAP_POLICY_VERSION,
    "profile-theme-benchmark": PROFILE_THEME_SCHEMA_VERSION,
    "stock-ranking": STOCK_RANKING_SCHEMA_VERSION,
    "ticker-factor": MOMENTUM_SCREEN_SCHEMA_VERSION,
    "watchlist": WATCHLIST_SCHEMA_VERSION,
}


@dataclass(frozen=True)
class CandidateRunRequest:
    """One frozen point-in-time candidate invocation."""

    portfolio_id: int
    as_of: datetime
    investor_profile: InvestorProfile
    ranking_factor: str = "aggregate"
    ranking_universe: str = "all"
    ranking_limit: int = 25
    search_terms: tuple[str, ...] = ()
    benchmark_index_ids: tuple[str, ...] = ()
    comparison_benchmark_index_id: str | None = None

    def __post_init__(self) -> None:
        if self.portfolio_id <= 0:
            raise ValueError("portfolio_id must be positive")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("candidate request as_of must be timezone-aware")
        normalized_as_of = self.as_of.astimezone(timezone.utc)
        if normalized_as_of.microsecond:
            raise ValueError("candidate request as_of must use whole-second precision")
        if self.ranking_limit <= 0 or self.ranking_limit > 250:
            raise ValueError("ranking_limit must be between 1 and 250")
        ranking_factor = self.ranking_factor.strip().lower()
        ranking_universe = self.ranking_universe.strip().lower()
        if not ranking_factor or not ranking_universe:
            raise ValueError("ranking factor and universe must be nonempty")
        search_terms = tuple(
            sorted({term.strip().lower() for term in self.search_terms if term.strip()})
        )
        benchmark_ids = tuple(
            sorted({index_id.strip() for index_id in self.benchmark_index_ids if index_id.strip()})
        )
        comparison = (
            self.comparison_benchmark_index_id.strip()
            if self.comparison_benchmark_index_id
            and self.comparison_benchmark_index_id.strip()
            else None
        )
        object.__setattr__(self, "as_of", normalized_as_of)
        object.__setattr__(self, "ranking_factor", ranking_factor)
        object.__setattr__(self, "ranking_universe", ranking_universe)
        object.__setattr__(self, "search_terms", search_terms)
        object.__setattr__(self, "benchmark_index_ids", benchmark_ids)
        object.__setattr__(self, "comparison_benchmark_index_id", comparison)


@dataclass(frozen=True)
class CandidateInputFailure:
    reason_code: str
    dependency: str
    expected: str | None
    actual: str | None


class CandidateInputCompatibilityError(RuntimeError):
    """A required frozen input cannot be consumed by this methodology."""

    def __init__(self, failure: CandidateInputFailure) -> None:
        self.failure = failure
        super().__init__(
            f"{failure.reason_code}: {failure.dependency} expected "
            f"{failure.expected!r}, received {failure.actual!r}"
        )


class CandidateRunService:
    """Compose stored source reads, scoring, guardrails, and immutable persistence."""

    def __init__(
        self,
        conn: Any,
        *,
        universe_builder: OutsideHoldingUniverseBuilder | None = None,
        scoring_engine: CandidateScoringEngine | None = None,
        repository: CandidateRunRepository | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.conn = conn
        self.universe_builder = universe_builder or OutsideHoldingUniverseBuilder(conn)
        self.scoring_engine = scoring_engine or CandidateScoringEngine(conn)
        self.repository = repository or CandidateRunRepository(conn)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.perf_counter

    def execute(
        self,
        request: CandidateRunRequest,
        *,
        request_id: str | None = None,
    ) -> CandidateRun:
        self.conn.execute("BEGIN TRANSACTION")
        try:
            persisted = self._execute_in_transaction(
                request,
                request_id=request_id,
            )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return persisted

    def _execute_in_transaction(
        self,
        request: CandidateRunRequest,
        *,
        request_id: str | None,
    ) -> CandidateRun:
        started_at = self.monotonic()
        self._validate_profile(request)
        pool = self.universe_builder.build(
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
        pool = _normalized_pool(pool)
        self._validate_pool(request, pool)

        provisional_hash = canonical_hash(_snapshot_material(request, pool, ()))
        provisional_run_id = candidate_run_id(
            CANDIDATE_METHODOLOGY_VERSION,
            provisional_hash,
        )
        scored = self.scoring_engine.score(
            pool=pool,
            investor_profile=request.investor_profile,
            run_id=provisional_run_id,
        )
        if scored.portfolio_id != request.portfolio_id or scored.as_of != request.as_of:
            _raise_incompatible(
                "candidate.input.scoring_scope_incompatible",
                "candidate-scoring-scope",
                f"{request.portfolio_id}@{request.as_of.isoformat()}",
                f"{scored.portfolio_id}@{scored.as_of.isoformat()}",
            )
        if scored.policy_version != CANDIDATE_SCORING_POLICY_VERSION:
            _raise_incompatible(
                "candidate.input.version_incompatible",
                "candidate-scoring-policy",
                CANDIDATE_SCORING_POLICY_VERSION,
                scored.policy_version,
            )

        input_snapshot_hash = canonical_hash(
            _snapshot_material(request, pool, scored.ordered_reviews)
        )
        run_id = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, input_snapshot_hash)
        reviews = tuple(
            replace(
                review,
                run_id=run_id,
                review_id=candidate_review_id(run_id, review.candidate_id),
            )
            for review in scored.ordered_reviews
        )
        run_status, blocking_conditions = _run_state(pool, reviews)
        runtime_ms = max(0, round((self.monotonic() - started_at) * 1000))
        created_at = self.clock()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("candidate service clock must be timezone-aware")
        created_at = created_at.astimezone(timezone.utc).replace(microsecond=0)
        provisional = CandidateRun(
            run_id=run_id,
            portfolio_id=f"portfolio:{request.portfolio_id}",
            as_of=request.as_of,
            schema_version=CANDIDATE_RUN_SCHEMA_VERSION,
            methodology_version=CANDIDATE_METHODOLOGY_VERSION,
            reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
            evidence_schema_version=CANDIDATE_EVIDENCE_SCHEMA_VERSION,
            investor_profile_id=request.investor_profile.profile_id,
            investor_profile_schema_version=request.investor_profile.schema_version,
            investor_profile_methodology_version=request.investor_profile.methodology_version,
            input_snapshot_hash=input_snapshot_hash,
            output_hash="0" * 64,
            source_watermarks=pool.source_watermarks,
            candidate_reviews=reviews,
            run_status=run_status,
            blocking_conditions=blocking_conditions,
            created_at=created_at,
            runtime_ms=runtime_ms,
            request_id=request_id,
        )
        run = replace(provisional, output_hash=provisional.expected_output_hash)
        self.repository.save(run, manage_transaction=False)
        persisted = self.repository.get(run_id)
        if persisted is None:
            raise RuntimeError("candidate run disappeared after persistence")
        return persisted

    @staticmethod
    def _validate_profile(request: CandidateRunRequest) -> None:
        profile = request.investor_profile
        expected_profile_id = f"profile:{profile.input_snapshot_hash}"
        checks = (
            (
                profile.schema_version == INVESTOR_PROFILE_SCHEMA_VERSION,
                "investor-profile-schema",
                INVESTOR_PROFILE_SCHEMA_VERSION,
                profile.schema_version,
            ),
            (
                profile.methodology_version == INVESTOR_PROFILE_METHODOLOGY_VERSION,
                "investor-profile-methodology",
                INVESTOR_PROFILE_METHODOLOGY_VERSION,
                profile.methodology_version,
            ),
            (
                is_sha256(profile.input_snapshot_hash) and profile.profile_id == expected_profile_id,
                "investor-profile-identity",
                expected_profile_id,
                profile.profile_id,
            ),
            (
                profile.portfolio_id == str(request.portfolio_id),
                "investor-profile-portfolio",
                str(request.portfolio_id),
                profile.portfolio_id,
            ),
            (
                profile.as_of.tzinfo is not None
                and profile.as_of.utcoffset() is not None
                and profile.as_of.microsecond == 0
                and profile.as_of.astimezone(timezone.utc) <= request.as_of,
                "investor-profile-as-of",
                f"whole-second UTC <= {request.as_of.isoformat()}",
                profile.as_of.isoformat(),
            ),
        )
        for valid, dependency, expected, actual in checks:
            if not valid:
                _raise_incompatible(
                    "candidate.input.version_incompatible"
                    if "schema" in dependency or "methodology" in dependency
                    else "candidate.input.profile_incompatible",
                    dependency,
                    expected,
                    actual,
                )

    @staticmethod
    def _validate_pool(request: CandidateRunRequest, pool: CandidatePoolResult) -> None:
        if pool.portfolio_id != request.portfolio_id or pool.as_of != request.as_of:
            _raise_incompatible(
                "candidate.input.pool_scope_incompatible",
                "candidate-pool-scope",
                f"{request.portfolio_id}@{request.as_of.isoformat()}",
                f"{pool.portfolio_id}@{pool.as_of.isoformat()}",
            )
        if pool.methodology_version != IDENTITY_METHODOLOGY_VERSION:
            _raise_incompatible(
                "candidate.input.version_incompatible",
                "candidate-identity-methodology",
                IDENTITY_METHODOLOGY_VERSION,
                pool.methodology_version,
            )
        actual_watermarks = {
            watermark.source_domain: watermark for watermark in pool.source_watermarks
        }
        missing_domains = sorted(set(_SOURCE_SCHEMA_VERSIONS) - set(actual_watermarks))
        if missing_domains:
            _raise_incompatible(
                "candidate.input.source_watermark_missing",
                missing_domains[0],
                _SOURCE_SCHEMA_VERSIONS[missing_domains[0]],
                None,
            )
        unexpected_domains = sorted(set(actual_watermarks) - set(_SOURCE_SCHEMA_VERSIONS))
        if unexpected_domains:
            _raise_incompatible(
                "candidate.input.source_watermark_incompatible",
                unexpected_domains[0],
                None,
                actual_watermarks[unexpected_domains[0]].source_schema_version,
            )
        for source_domain, expected_version in sorted(_SOURCE_SCHEMA_VERSIONS.items()):
            actual_version = actual_watermarks[source_domain].source_schema_version
            if actual_version != expected_version:
                _raise_incompatible(
                    "candidate.input.version_incompatible",
                    source_domain,
                    expected_version,
                    actual_version,
                )


def _snapshot_material(
    request: CandidateRunRequest,
    pool: CandidatePoolResult,
    reviews: tuple[CandidateReview, ...],
) -> dict[str, Any]:
    return {
        "as_of": request.as_of,
        "candidate_versions": {
            "evidence_schema": CANDIDATE_EVIDENCE_SCHEMA_VERSION,
            "guardrail_policy": CANDIDATE_GUARDRAIL_POLICY_VERSION,
            "identity_methodology": IDENTITY_METHODOLOGY_VERSION,
            "methodology": CANDIDATE_METHODOLOGY_VERSION,
            "orchestration_policy": CANDIDATE_ORCHESTRATION_POLICY_VERSION,
            "reason_codes": CANDIDATE_REASON_CODES_VERSION,
            "review_schema": CANDIDATE_REVIEW_SCHEMA_VERSION,
            "run_schema": CANDIDATE_RUN_SCHEMA_VERSION,
            "scoring_policy": CANDIDATE_SCORING_POLICY_VERSION,
            "screen_policy": SCREEN_POLICY_VERSION,
            "source_adapters": CANDIDATE_SOURCE_ADAPTER_VERSION,
        },
        "investor_profile": _profile_material(request.investor_profile),
        "portfolio_id": str(request.portfolio_id),
        "resolved_candidate_inputs": tuple(
            _review_input_material(review)
            for review in sorted(reviews, key=lambda item: item.candidate_id)
        ),
        "resolved_pool": pool,
        "source_request": {
            "benchmark_index_ids": request.benchmark_index_ids,
            "comparison_benchmark_index_id": request.comparison_benchmark_index_id,
            "ranking_factor": request.ranking_factor,
            "ranking_limit": request.ranking_limit,
            "ranking_universe": request.ranking_universe,
            "search_terms": request.search_terms,
        },
    }


def _profile_material(profile: InvestorProfile) -> dict[str, Any]:
    return {
        "allocation_mix": {
            "classified_weight": _number(profile.allocation_mix.classified_weight),
            "confidence": _number(profile.allocation_mix.confidence),
            "direct_stock_weight": _number(profile.allocation_mix.direct_stock_weight),
            "etf_weight": _number(profile.allocation_mix.etf_weight),
            "evidence_refs": tuple(sorted(profile.allocation_mix.evidence_refs)),
            "label": profile.allocation_mix.label,
            "passive_weight": _number(profile.allocation_mix.passive_weight),
        },
        "archetype_labels": tuple(sorted(profile.archetype_labels)),
        "as_of": profile.as_of,
        "confidence": _number(profile.confidence),
        "concentration_profile": _dimension_material(profile.concentration_profile),
        "data_gaps": tuple(sorted(profile.data_gaps)),
        "evidence_refs": tuple(sorted(profile.evidence_refs)),
        "factor_scores": tuple(
            _dimension_material(dimension)
            for dimension in sorted(profile.factor_scores, key=lambda item: item.code)
        ),
        "geography_tilt": _dimension_material(profile.geography_tilt),
        "inference_scope": profile.inference_scope,
        "input_snapshot_hash": profile.input_snapshot_hash,
        "methodology_version": profile.methodology_version,
        "portfolio_id": profile.portfolio_id,
        "profile_id": profile.profile_id,
        "schema_version": profile.schema_version,
        "sector_tilts": tuple(
            _tilt_material(tilt)
            for tilt in sorted(profile.sector_tilts, key=lambda item: (item.dimension, item.key))
        ),
        "suitability_status": profile.suitability_status,
        "theme_tilts": tuple(
            _tilt_material(tilt)
            for tilt in sorted(profile.theme_tilts, key=lambda item: (item.dimension, item.key))
        ),
        "observed_risk_posture": _dimension_material(profile.observed_risk_posture),
    }


def _dimension_material(dimension: ProfileDimension) -> dict[str, Any]:
    return {
        "code": dimension.code,
        "confidence": _number(dimension.confidence),
        "data_gaps": tuple(sorted(dimension.data_gaps)),
        "evidence_refs": tuple(sorted(dimension.evidence_refs)),
        "label": dimension.label,
        "score": _number(dimension.score),
    }


def _tilt_material(tilt: Any) -> dict[str, Any]:
    return {
        "confidence": _number(tilt.confidence),
        "dimension": tilt.dimension,
        "evidence_refs": tuple(sorted(tilt.evidence_refs)),
        "key": tilt.key,
        "label": tilt.label,
        "weight": _number(tilt.weight),
    }


def _review_input_material(review: CandidateReview) -> dict[str, Any]:
    return {
        "asset_id": review.asset_id,
        "candidate_id": review.candidate_id,
        "data_as_of": review.data_as_of,
        "diversification_score": review.diversification_score,
        "eligibility_state": review.eligibility_state,
        "evidence_refs": review.evidence_refs,
        "fit_score": review.fit_score,
        "highlights": review.highlights,
        "methodology_as_of": review.methodology_as_of,
        "missing_metrics": review.missing_metrics,
        "reason_codes": review.reason_codes,
        "redundancy_score": review.redundancy_score,
        "source_matches": review.source_matches,
        "ticker": review.ticker,
        "warnings": review.warnings,
    }


def _normalized_pool(pool: CandidatePoolResult) -> CandidatePoolResult:
    return replace(
        pool,
        source_watermarks=tuple(
            sorted(pool.source_watermarks, key=lambda item: item.source_domain)
        ),
        candidates=tuple(sorted(pool.candidates, key=lambda item: item.asset_id)),
        exclusions=tuple(
            sorted(
                pool.exclusions,
                key=lambda item: (
                    item.economic_exposure_id,
                    item.reason_code,
                    item.asset_id,
                ),
            )
        ),
        blocked_identities=tuple(
            sorted(
                pool.blocked_identities,
                key=lambda item: (item.source_asset_id, item.reason_code),
            )
        ),
        source_limitations=tuple(sorted(set(pool.source_limitations))),
    )


def _run_state(
    pool: CandidatePoolResult,
    reviews: tuple[CandidateReview, ...],
) -> tuple[str, tuple[str, ...]]:
    if not reviews:
        return "blocked", ("run.candidates.none",)
    if all(review.eligibility_state == "blocked" for review in reviews):
        return "blocked", ("run.candidates.all_blocked",)
    incomplete_coverage = any(
        watermark.coverage_state != "available"
        for watermark in pool.source_watermarks
    )
    return ("partial" if incomplete_coverage else "completed"), ()


def _number(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _raise_incompatible(
    reason_code: str,
    dependency: str,
    expected: str | None,
    actual: str | None,
) -> None:
    raise CandidateInputCompatibilityError(
        CandidateInputFailure(
            reason_code=reason_code,
            dependency=dependency,
            expected=expected,
            actual=actual,
        )
    )
