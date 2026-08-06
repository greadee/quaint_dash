"""Deserialization for persisted canonical candidate-review payloads."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from dashboard.ai_brain.candidates.models import (
    CandidateEvidenceRef,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidateReview,
    CandidateScore,
    CandidateScoreComponent,
    CandidateSourceMatch,
    CandidateWarning,
)


def candidate_review_from_json(payload: str) -> CandidateReview:
    """Rebuild and validate a candidate review from canonical JSON."""

    value = json.loads(payload)
    if not isinstance(value, dict):
        raise TypeError("candidate review payload must be a JSON object")
    return _review(value)


def _review(value: dict[str, Any]) -> CandidateReview:
    return CandidateReview(
        review_id=str(value["review_id"]),
        run_id=str(value["run_id"]),
        candidate_id=str(value["candidate_id"]),
        asset_id=str(value["asset_id"]),
        ticker=str(value["ticker"]),
        schema_version=str(value["schema_version"]),
        methodology_version=str(value["methodology_version"]),
        reason_codes_version=str(value["reason_codes_version"]),
        reason_codes=tuple(str(item) for item in value["reason_codes"]),
        source_matches=tuple(_source_match(item) for item in value["source_matches"]),
        fit_score=_score(value["fit_score"]),
        diversification_score=_score(value["diversification_score"]),
        redundancy_score=_score(value["redundancy_score"]),
        highlights=tuple(_highlight(item) for item in value["highlights"]),
        missing_metrics=tuple(_missing_metric(item) for item in value["missing_metrics"]),
        warnings=tuple(_warning(item) for item in value["warnings"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
        data_as_of=_timestamp(value["data_as_of"]),
        methodology_as_of=_timestamp(value["methodology_as_of"]),
        eligibility_state=str(value["eligibility_state"]),
    )


def _evidence(value: dict[str, Any]) -> CandidateEvidenceRef:
    return CandidateEvidenceRef(
        evidence_id=str(value["evidence_id"]),
        source_domain=str(value["source_domain"]),
        source_schema_version=str(value["source_schema_version"]),
        source_record_id=str(value["source_record_id"]),
        as_of=_timestamp(value["as_of"]),
        payload_hash=str(value["payload_hash"]),
        freshness_state=str(value["freshness_state"]),
        evidence_schema_version=str(value["evidence_schema_version"]),
    )


def _source_match(value: dict[str, Any]) -> CandidateSourceMatch:
    return CandidateSourceMatch(
        source_family=str(value["source_family"]),
        source_methodology_version=str(value["source_methodology_version"]),
        reason_code=str(value["reason_code"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
        nomination_strength=_decimal(value["nomination_strength"]),
    )


def _component(value: dict[str, Any]) -> CandidateScoreComponent:
    return CandidateScoreComponent(
        component_code=str(value["component_code"]),
        value=Decimal(str(value["value"])),
        weight=Decimal(str(value["weight"])),
        contribution=Decimal(str(value["contribution"])),
        reason_codes=tuple(str(item) for item in value["reason_codes"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
    )


def _score(value: dict[str, Any]) -> CandidateScore:
    return CandidateScore(
        score_type=str(value["score_type"]),
        value=_decimal(value["value"]),
        components=tuple(_component(item) for item in value["components"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
        missing_metric_code=(
            str(value["missing_metric_code"])
            if value["missing_metric_code"] is not None
            else None
        ),
    )


def _highlight(value: dict[str, Any]) -> CandidateHighlight:
    return CandidateHighlight(
        category=str(value["category"]),
        highlight_code=str(value["highlight_code"]),
        normalized_value=Decimal(str(value["normalized_value"])),
        unit=str(value["unit"]),
        direction=str(value["direction"]),
        as_of=_timestamp(value["as_of"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
    )


def _missing_metric(value: dict[str, Any]) -> CandidateMissingMetric:
    return CandidateMissingMetric(
        metric_code=str(value["metric_code"]),
        criticality=str(value["criticality"]),
        expected_source=str(value["expected_source"]),
        reason_code=str(value["reason_code"]),
        guardrail_effect=str(value["guardrail_effect"]),
    )


def _warning(value: dict[str, Any]) -> CandidateWarning:
    return CandidateWarning(
        warning_code=str(value["warning_code"]),
        severity=str(value["severity"]),
        blocking=bool(value["blocking"]),
        evidence_refs=tuple(_evidence(item) for item in value["evidence_refs"]),
    )


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("candidate timestamps must use RFC 3339 UTC Z format")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
