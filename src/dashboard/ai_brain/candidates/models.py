"""Immutable domain models for deterministic outside-holding candidate reviews."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from dashboard.ai_brain.candidates.canonical import (
    candidate_evidence_id,
    candidate_id,
    candidate_review_id,
    candidate_run_id,
    canonical_hash,
    is_sha256,
    is_typed_hash,
)

CANDIDATE_RUN_SCHEMA_VERSION = "candidate-run.v1"
CANDIDATE_REVIEW_SCHEMA_VERSION = "candidate-review.v1"
CANDIDATE_EVIDENCE_SCHEMA_VERSION = "candidate-evidence.v1"
CANDIDATE_METHODOLOGY_VERSION = "candidate-engine.deterministic.v2"
CANDIDATE_REASON_CODES_VERSION = "candidate-reason-codes.v2"

CANDIDATE_ELIGIBILITY_STATES = frozenset({"eligible", "downgraded", "blocked"})
CANDIDATE_RUN_STATES = frozenset({"completed", "partial", "blocked"})
CANDIDATE_SOURCE_FAMILIES = frozenset(
    {
        "all_universe",
        "benchmark",
        "geography_gap",
        "industry",
        "momentum_screen",
        "peer",
        "quality_screen",
        "ranking",
        "sector_gap",
        "theme",
        "value_screen",
        "watchlist",
    }
)
CANDIDATE_SCORE_TYPES = frozenset({"fit", "diversification", "redundancy"})
EVIDENCE_FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})
SOURCE_COVERAGE_STATES = frozenset({"available", "partial", "missing", "unsupported"})
MISSING_METRIC_CRITICALITIES = frozenset({"critical", "noncritical"})
GUARDRAIL_EFFECTS = frozenset({"none", "downgrade", "block"})
WARNING_SEVERITIES = frozenset({"info", "warning", "critical"})
HIGHLIGHT_CATEGORIES = frozenset(
    {"momentum", "quality", "risk", "sentiment", "valuation"}
)
HIGHLIGHT_DIRECTIONS = frozenset({"positive", "negative", "neutral", "unknown"})

_DOTTED_CODE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9][a-z0-9_-]*)+$")


def _validate_text(name: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty and trimmed")


def _validate_code(name: str, value: str) -> None:
    if not _DOTTED_CODE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase dotted code")


def _validate_timestamp(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.microsecond != 0:
        raise ValueError(f"{name} must use whole-second precision")


def _validate_decimal_range(name: str, value: Decimal, low: str, high: str) -> None:
    if not value.is_finite() or value < Decimal(low) or value > Decimal(high):
        raise ValueError(f"{name} must be between {low} and {high}")


def _validate_unique(name: str, values: Iterable[str]) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True)
class CandidateEvidenceRef:
    evidence_id: str
    source_domain: str
    source_schema_version: str
    source_record_id: str
    as_of: datetime
    payload_hash: str
    freshness_state: str
    evidence_schema_version: str = CANDIDATE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "source_domain",
            "source_schema_version",
            "source_record_id",
            "evidence_schema_version",
        ):
            _validate_text(name, getattr(self, name))
        if self.evidence_schema_version != CANDIDATE_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported candidate evidence schema version")
        _validate_timestamp("evidence as_of", self.as_of)
        if not is_sha256(self.payload_hash):
            raise ValueError("payload_hash must be a lowercase SHA-256 digest")
        if self.freshness_state not in EVIDENCE_FRESHNESS_STATES:
            raise ValueError(f"unknown evidence freshness state: {self.freshness_state}")
        expected_id = candidate_evidence_id(
            source_domain=self.source_domain,
            source_schema_version=self.source_schema_version,
            source_record_id=self.source_record_id,
            as_of=self.as_of,
            payload_hash=self.payload_hash,
        )
        if self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match its material evidence identity")


@dataclass(frozen=True)
class CandidateSourceWatermark:
    source_domain: str
    source_schema_version: str
    as_of: datetime | None
    coverage_state: str

    def __post_init__(self) -> None:
        _validate_text("source_domain", self.source_domain)
        _validate_text("source_schema_version", self.source_schema_version)
        if self.as_of is not None:
            _validate_timestamp("source watermark as_of", self.as_of)
        if self.coverage_state not in SOURCE_COVERAGE_STATES:
            raise ValueError(f"unknown source coverage state: {self.coverage_state}")
        if self.coverage_state in {"available", "partial"} and self.as_of is None:
            raise ValueError("available or partial sources require an as_of watermark")


@dataclass(frozen=True)
class CandidateSourceMatch:
    source_family: str
    source_methodology_version: str
    reason_code: str
    evidence_refs: tuple[CandidateEvidenceRef, ...]
    nomination_strength: Decimal | None = None

    def __post_init__(self) -> None:
        if self.source_family not in CANDIDATE_SOURCE_FAMILIES:
            raise ValueError(f"unknown candidate source family: {self.source_family}")
        _validate_text("source_methodology_version", self.source_methodology_version)
        _validate_code("source reason_code", self.reason_code)
        if not self.evidence_refs:
            raise ValueError("candidate source matches require evidence")
        _validate_unique("source evidence IDs", _evidence_ids(self.evidence_refs))
        if self.nomination_strength is not None:
            _validate_decimal_range("nomination_strength", self.nomination_strength, "0", "100")


@dataclass(frozen=True)
class CandidateScoreComponent:
    component_code: str
    value: Decimal
    weight: Decimal
    contribution: Decimal
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[CandidateEvidenceRef, ...]

    def __post_init__(self) -> None:
        _validate_code("component_code", self.component_code)
        _validate_decimal_range("component value", self.value, "0", "100")
        _validate_decimal_range("component weight", self.weight, "0", "1")
        _validate_decimal_range("component contribution", self.contribution, "0", "100")
        if not self.reason_codes:
            raise ValueError("score components require at least one reason code")
        for reason_code in self.reason_codes:
            _validate_code("component reason_code", reason_code)
        _validate_unique("component reason codes", self.reason_codes)
        if not self.evidence_refs:
            raise ValueError("score components require evidence")
        _validate_unique("component evidence IDs", _evidence_ids(self.evidence_refs))


@dataclass(frozen=True)
class CandidateScore:
    score_type: str
    value: Decimal | None
    components: tuple[CandidateScoreComponent, ...]
    evidence_refs: tuple[CandidateEvidenceRef, ...]
    missing_metric_code: str | None = None

    def __post_init__(self) -> None:
        if self.score_type not in CANDIDATE_SCORE_TYPES:
            raise ValueError(f"unknown candidate score type: {self.score_type}")
        _validate_unique(
            "score component codes",
            (component.component_code for component in self.components),
        )
        _validate_unique("score evidence IDs", _evidence_ids(self.evidence_refs))
        nested_evidence = {
            evidence_id
            for component in self.components
            for evidence_id in _evidence_ids(component.evidence_refs)
        }
        if not nested_evidence.issubset(set(_evidence_ids(self.evidence_refs))):
            raise ValueError("score evidence must include every component evidence reference")
        if self.value is None:
            if self.missing_metric_code is None:
                raise ValueError("null candidate scores require a missing metric code")
            _validate_code("score missing_metric_code", self.missing_metric_code)
        else:
            _validate_decimal_range("candidate score", self.value, "0", "100")
            if not self.components or not self.evidence_refs:
                raise ValueError("numeric candidate scores require components and evidence")
            if self.missing_metric_code is not None:
                raise ValueError("numeric candidate scores cannot name a missing metric")


@dataclass(frozen=True)
class CandidateHighlight:
    category: str
    highlight_code: str
    normalized_value: Decimal
    unit: str
    direction: str
    as_of: datetime
    evidence_refs: tuple[CandidateEvidenceRef, ...]

    def __post_init__(self) -> None:
        if self.category not in HIGHLIGHT_CATEGORIES:
            raise ValueError(f"unknown candidate highlight category: {self.category}")
        _validate_code("highlight_code", self.highlight_code)
        _validate_decimal_range("highlight normalized_value", self.normalized_value, "0", "100")
        _validate_text("highlight unit", self.unit)
        if self.direction not in HIGHLIGHT_DIRECTIONS:
            raise ValueError(f"unknown highlight direction: {self.direction}")
        _validate_timestamp("highlight as_of", self.as_of)
        if not self.evidence_refs:
            raise ValueError("candidate highlights require evidence")
        _validate_unique("highlight evidence IDs", _evidence_ids(self.evidence_refs))


@dataclass(frozen=True)
class CandidateWarning:
    warning_code: str
    severity: str
    blocking: bool
    evidence_refs: tuple[CandidateEvidenceRef, ...]

    def __post_init__(self) -> None:
        _validate_code("warning_code", self.warning_code)
        if self.severity not in WARNING_SEVERITIES:
            raise ValueError(f"unknown candidate warning severity: {self.severity}")
        if not self.evidence_refs:
            raise ValueError("candidate warnings require evidence")
        _validate_unique("warning evidence IDs", _evidence_ids(self.evidence_refs))


@dataclass(frozen=True)
class CandidateMissingMetric:
    metric_code: str
    criticality: str
    expected_source: str
    reason_code: str
    guardrail_effect: str

    def __post_init__(self) -> None:
        _validate_code("metric_code", self.metric_code)
        if self.criticality not in MISSING_METRIC_CRITICALITIES:
            raise ValueError(f"unknown missing-metric criticality: {self.criticality}")
        _validate_text("expected_source", self.expected_source)
        _validate_code("missing metric reason_code", self.reason_code)
        if self.guardrail_effect not in GUARDRAIL_EFFECTS:
            raise ValueError(f"unknown missing-metric guardrail effect: {self.guardrail_effect}")


@dataclass(frozen=True)
class CandidateReview:
    review_id: str
    run_id: str
    candidate_id: str
    asset_id: str
    ticker: str
    schema_version: str
    methodology_version: str
    reason_codes_version: str
    reason_codes: tuple[str, ...]
    source_matches: tuple[CandidateSourceMatch, ...]
    fit_score: CandidateScore
    diversification_score: CandidateScore
    redundancy_score: CandidateScore
    highlights: tuple[CandidateHighlight, ...]
    missing_metrics: tuple[CandidateMissingMetric, ...]
    warnings: tuple[CandidateWarning, ...]
    evidence_refs: tuple[CandidateEvidenceRef, ...]
    data_as_of: datetime
    methodology_as_of: datetime
    eligibility_state: str

    def __post_init__(self) -> None:
        if not is_typed_hash(self.run_id, "candidate-run"):
            raise ValueError("run_id must use candidate-run:<lowercase SHA-256>")
        _validate_text("asset_id", self.asset_id)
        if self.ticker != self.ticker.strip().upper() or not self.ticker:
            raise ValueError("ticker must be nonempty, trimmed, and uppercase")
        for name in ("schema_version", "methodology_version", "reason_codes_version"):
            _validate_text(name, getattr(self, name))
        if self.schema_version != CANDIDATE_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported candidate review schema version")
        expected_candidate_id = candidate_id(self.asset_id)
        if self.candidate_id != expected_candidate_id:
            raise ValueError("candidate_id does not match canonical asset identity")
        expected_review_id = candidate_review_id(self.run_id, self.candidate_id)
        if self.review_id != expected_review_id:
            raise ValueError("review_id does not match run and candidate identity")
        if self.eligibility_state not in CANDIDATE_ELIGIBILITY_STATES:
            raise ValueError(f"unknown candidate eligibility state: {self.eligibility_state}")
        if not self.reason_codes:
            raise ValueError("candidate reviews require at least one reason code")
        for reason_code in self.reason_codes:
            _validate_code("candidate reason_code", reason_code)
        _validate_unique("candidate reason codes", self.reason_codes)
        if not self.source_matches:
            raise ValueError("candidate reviews require at least one source match")
        _validate_unique(
            "candidate source matches",
            (
                f"{match.source_family}\x1f{match.reason_code}\x1f{match.source_methodology_version}"
                for match in self.source_matches
            ),
        )
        source_reason_codes = {match.reason_code for match in self.source_matches}
        if not source_reason_codes.issubset(set(self.reason_codes)):
            raise ValueError("candidate reason codes must include every source-match reason")
        expected_score_types = {
            "fit_score": "fit",
            "diversification_score": "diversification",
            "redundancy_score": "redundancy",
        }
        for field_name, score_type in expected_score_types.items():
            if getattr(self, field_name).score_type != score_type:
                raise ValueError(f"{field_name} must contain the {score_type} score state")
        _validate_unique(
            "candidate missing metric codes",
            (metric.metric_code for metric in self.missing_metrics),
        )
        _validate_unique(
            "candidate warning codes",
            (warning.warning_code for warning in self.warnings),
        )
        _validate_unique("candidate evidence IDs", _evidence_ids(self.evidence_refs))
        if not self.evidence_refs:
            raise ValueError("candidate reviews require stable evidence")
        missing_metric_codes = {metric.metric_code for metric in self.missing_metrics}
        for score in (self.fit_score, self.diversification_score, self.redundancy_score):
            if score.missing_metric_code and score.missing_metric_code not in missing_metric_codes:
                raise ValueError("null score missing metric must exist in candidate missing_metrics")
        nested_evidence = _nested_review_evidence_ids(self)
        if not nested_evidence.issubset(set(_evidence_ids(self.evidence_refs))):
            raise ValueError("candidate evidence must include every nested evidence reference")
        canonical_evidence = {ref.evidence_id: ref for ref in self.evidence_refs}
        for ref in _nested_review_evidence_refs(self):
            if canonical_evidence[ref.evidence_id] != ref:
                raise ValueError("identical evidence IDs must resolve to identical evidence")
        _validate_timestamp("candidate data_as_of", self.data_as_of)
        _validate_timestamp("candidate methodology_as_of", self.methodology_as_of)
        if any(ref.as_of > self.data_as_of for ref in self.evidence_refs):
            raise ValueError("candidate evidence cannot be newer than data_as_of")
        if any(warning.blocking for warning in self.warnings) and self.eligibility_state != "blocked":
            raise ValueError("blocking warnings require blocked eligibility")

    @property
    def output_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True)
class CandidateRun:
    run_id: str
    portfolio_id: str
    as_of: datetime
    schema_version: str
    methodology_version: str
    reason_codes_version: str
    evidence_schema_version: str
    investor_profile_id: str
    investor_profile_schema_version: str
    investor_profile_methodology_version: str
    input_snapshot_hash: str
    output_hash: str
    source_watermarks: tuple[CandidateSourceWatermark, ...]
    candidate_reviews: tuple[CandidateReview, ...]
    run_status: str
    blocking_conditions: tuple[str, ...]
    created_at: datetime
    runtime_ms: int | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        _validate_text("portfolio_id", self.portfolio_id)
        _validate_timestamp("candidate run as_of", self.as_of)
        _validate_timestamp("candidate run created_at", self.created_at)
        for name in (
            "schema_version",
            "methodology_version",
            "reason_codes_version",
            "evidence_schema_version",
            "investor_profile_schema_version",
            "investor_profile_methodology_version",
        ):
            _validate_text(name, getattr(self, name))
        if self.schema_version != CANDIDATE_RUN_SCHEMA_VERSION:
            raise ValueError("unsupported candidate run schema version")
        if not is_typed_hash(self.investor_profile_id, "profile"):
            raise ValueError("investor_profile_id must use profile:<lowercase SHA-256>")
        if not is_sha256(self.input_snapshot_hash):
            raise ValueError("input_snapshot_hash must be a lowercase SHA-256 digest")
        if not is_sha256(self.output_hash):
            raise ValueError("output_hash must be a lowercase SHA-256 digest")
        expected_run_id = candidate_run_id(self.methodology_version, self.input_snapshot_hash)
        if self.run_id != expected_run_id:
            raise ValueError("run_id does not match methodology and input snapshot")
        if self.run_status not in CANDIDATE_RUN_STATES:
            raise ValueError(f"unknown candidate run state: {self.run_status}")
        _validate_unique(
            "source watermark domains",
            (watermark.source_domain for watermark in self.source_watermarks),
        )
        _validate_unique(
            "candidate review IDs",
            (review.review_id for review in self.candidate_reviews),
        )
        _validate_unique(
            "candidate IDs",
            (review.candidate_id for review in self.candidate_reviews),
        )
        for review in self.candidate_reviews:
            if review.run_id != self.run_id:
                raise ValueError("candidate review run_id must match its candidate run")
            if review.methodology_version != self.methodology_version:
                raise ValueError("candidate review methodology must match its candidate run")
            if review.reason_codes_version != self.reason_codes_version:
                raise ValueError("candidate review reason codes must match its candidate run")
            if any(
                ref.evidence_schema_version != self.evidence_schema_version
                for ref in review.evidence_refs
            ):
                raise ValueError("candidate evidence schema must match its candidate run")
            if review.data_as_of > self.as_of or review.methodology_as_of > self.as_of:
                raise ValueError("candidate reviews cannot be newer than run as_of")
        if any(
            watermark.as_of is not None and watermark.as_of > self.as_of
            for watermark in self.source_watermarks
        ):
            raise ValueError("source watermarks cannot be newer than run as_of")
        for condition in self.blocking_conditions:
            _validate_code("run blocking condition", condition)
        _validate_unique("run blocking conditions", self.blocking_conditions)
        if self.runtime_ms is not None and self.runtime_ms < 0:
            raise ValueError("runtime_ms must be nonnegative")
        if self.request_id is not None:
            _validate_text("request_id", self.request_id)

    @property
    def expected_output_hash(self) -> str:
        return canonical_hash(self)

    @property
    def output_hash_is_valid(self) -> bool:
        return self.output_hash == self.expected_output_hash

    @property
    def eligible_count(self) -> int:
        return sum(review.eligibility_state == "eligible" for review in self.candidate_reviews)

    @property
    def downgraded_count(self) -> int:
        return sum(review.eligibility_state == "downgraded" for review in self.candidate_reviews)

    @property
    def blocked_count(self) -> int:
        return sum(review.eligibility_state == "blocked" for review in self.candidate_reviews)


def _evidence_ids(refs: Iterable[CandidateEvidenceRef]) -> tuple[str, ...]:
    return tuple(ref.evidence_id for ref in refs)


def _nested_review_evidence_ids(review: CandidateReview) -> set[str]:
    return {ref.evidence_id for ref in _nested_review_evidence_refs(review)}


def _nested_review_evidence_refs(review: CandidateReview) -> tuple[CandidateEvidenceRef, ...]:
    return tuple(
        ref
        for refs in (
            *(match.evidence_refs for match in review.source_matches),
            review.fit_score.evidence_refs,
            review.diversification_score.evidence_refs,
            review.redundancy_score.evidence_refs,
            *(highlight.evidence_refs for highlight in review.highlights),
            *(warning.evidence_refs for warning in review.warnings),
        )
        for ref in refs
    )
