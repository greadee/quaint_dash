from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from dashboard.api.evidence_contract import (
    EVIDENCE_FRESHNESS_POLICIES,
    EvidencePolicyInput,
    EvidenceDisplayState,
    FreshnessWindow,
    attach_evidence_display,
    evaluate_evidence,
    select_public_fields_with_evidence,
)
from dashboard.api.models import EvidenceDisplayResponse


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def evidence(**overrides) -> EvidencePolicyInput:
    values = {
        "evidence_type": "price",
        "source_kind": "real",
        "source_name": "yfinance",
        "source_health": "healthy",
        "observed_at": NOW - timedelta(hours=1),
        "retrieved_at": NOW - timedelta(minutes=30),
    }
    values.update(overrides)
    return EvidencePolicyInput(**values)


@pytest.mark.parametrize(
    ("evidence_type", "current_for", "warning_for"),
    [
        ("price", timedelta(hours=36), timedelta(hours=96)),
        ("news", timedelta(hours=24), timedelta(hours=72)),
        ("financial_statement", timedelta(days=150), timedelta(days=240)),
        ("benchmark", timedelta(hours=36), timedelta(hours=96)),
        ("monthly_signal", timedelta(days=45), timedelta(days=75)),
        ("retail_sentiment", timedelta(hours=36), timedelta(hours=96)),
    ],
)
def test_each_evidence_type_has_explicit_boundary_behavior(
    evidence_type: str,
    current_for: timedelta,
    warning_for: timedelta,
) -> None:
    assert EVIDENCE_FRESHNESS_POLICIES[evidence_type] == FreshnessWindow(
        current_for,
        warning_for,
    )
    current = evaluate_evidence(
        evidence(evidence_type=evidence_type, observed_at=NOW - current_for),
        clock=lambda: NOW,
    )
    warning = evaluate_evidence(
        evidence(evidence_type=evidence_type, observed_at=NOW - current_for - timedelta(seconds=1)),
        clock=lambda: NOW,
    )
    stale = evaluate_evidence(
        evidence(evidence_type=evidence_type, observed_at=NOW - warning_for - timedelta(seconds=1)),
        clock=lambda: NOW,
    )

    assert (current.freshness_state, current.action_eligibility) == ("current", "eligible")
    assert (warning.freshness_state, warning.action_eligibility) == ("warning", "caution")
    assert (stale.freshness_state, stale.action_eligibility) == ("stale", "blocked")
    assert warning.reason_codes == (f"evidence.freshness.{evidence_type}.warning",)
    assert stale.reason_codes == (f"evidence.freshness.{evidence_type}.stale",)


def test_policy_is_type_aware_for_the_same_observation_age() -> None:
    price = evaluate_evidence(evidence(observed_at=NOW - timedelta(days=10)), clock=lambda: NOW)
    statement = evaluate_evidence(
        evidence(
            evidence_type="financial_statement",
            observed_at=NOW - timedelta(days=10),
        ),
        clock=lambda: NOW,
    )
    signal = evaluate_evidence(
        evidence(evidence_type="monthly_signal", observed_at=NOW - timedelta(days=10)),
        clock=lambda: NOW,
    )

    assert price.freshness_state == "stale"
    assert statement.freshness_state == signal.freshness_state == "current"


def test_policy_has_no_mutable_or_generic_freshness_fallback() -> None:
    with pytest.raises(TypeError):
        EVIDENCE_FRESHNESS_POLICIES["price"] = FreshnessWindow(  # type: ignore[index]
            timedelta(hours=1),
            timedelta(hours=2),
        )
    with pytest.raises(ValueError, match="missing freshness policy for price"):
        evaluate_evidence(evidence(), clock=lambda: NOW, policies={})


@pytest.mark.parametrize(
    ("changes", "freshness", "coverage", "eligibility", "reason"),
    [
        (
            {"source_health": "blocked", "confidence": 1.0},
            "blocked",
            "complete",
            "blocked",
            "evidence.source_health.blocked",
        ),
        (
            {"source_kind": "fixture", "confidence": 1.0},
            "current",
            "complete",
            "blocked",
            "evidence.source_kind.fixture",
        ),
        (
            {"source_kind": "proxy", "confidence": 1.0},
            "current",
            "complete",
            "blocked",
            "evidence.source_kind.proxy",
        ),
        (
            {"essential_missing_inputs": ("free_cash_flow",), "confidence": 1.0},
            "current",
            "missing",
            "blocked",
            "evidence.coverage.essential_missing",
        ),
    ],
)
def test_blocking_evidence_cannot_be_overridden_by_high_confidence(
    changes: dict,
    freshness: str,
    coverage: str,
    eligibility: str,
    reason: str,
) -> None:
    state = evaluate_evidence(evidence(**changes), clock=lambda: NOW)

    assert state.confidence == 1.0
    assert (state.freshness_state, state.coverage_state) == (freshness, coverage)
    assert state.action_eligibility == eligibility
    assert reason in state.reason_codes


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"source_health": "degraded"}, "evidence.source_health.degraded"),
        ({"source_kind": "inferred"}, "evidence.source_kind.inferred"),
        ({"missing_inputs": ("cash_flow",)}, "evidence.coverage.partial"),
        ({"effectiveness_sample_size": 0}, "evidence.effectiveness.no_sample"),
    ],
)
def test_non_blocking_limitations_require_caution(changes: dict, reason: str) -> None:
    state = evaluate_evidence(evidence(**changes), clock=lambda: NOW)

    assert state.action_eligibility == "caution"
    assert reason in state.reason_codes


def test_unknown_provenance_and_unsupported_coverage_are_explicitly_blocked() -> None:
    unknown = evaluate_evidence(
        evidence(source_kind="unknown", source_name=None, source_health="unknown"),
        clock=lambda: NOW,
    )
    unsupported = evaluate_evidence(evidence(coverage_supported=False), clock=lambda: NOW)

    assert unknown.action_eligibility == "blocked"
    assert unknown.reason_codes[:3] == (
        "evidence.source_health.unknown",
        "evidence.source_kind.unknown",
        "evidence.source_name.missing",
    )
    assert unsupported.coverage_state == "unsupported"
    assert unsupported.action_eligibility == "blocked"
    assert "evidence.coverage.unsupported" in unsupported.reason_codes


def test_missing_or_future_timestamps_are_not_presented_as_current() -> None:
    missing = evaluate_evidence(evidence(observed_at=None), clock=lambda: NOW)
    future = evaluate_evidence(
        evidence(observed_at=NOW + timedelta(minutes=1)),
        clock=lambda: NOW,
    )
    future_retrieval = evaluate_evidence(
        evidence(retrieved_at=NOW + timedelta(minutes=1)),
        clock=lambda: NOW,
    )

    assert (missing.freshness_state, missing.action_eligibility) == ("unknown", "blocked")
    assert "evidence.observed_at.missing" in missing.reason_codes
    assert (future.freshness_state, future.action_eligibility) == ("unknown", "blocked")
    assert "evidence.observed_at.future" in future.reason_codes
    assert future_retrieval.action_eligibility == "blocked"
    assert "evidence.retrieved_at.future" in future_retrieval.reason_codes


def test_naive_and_date_observations_use_documented_utc_normalization() -> None:
    naive = evaluate_evidence(
        evidence(observed_at=datetime(2026, 9, 8, 11), retrieved_at=datetime(2026, 9, 8, 11, 30)),
        clock=lambda: datetime(2026, 9, 8, 12),
    )
    statement = evaluate_evidence(
        evidence(evidence_type="financial_statement", observed_at=date(2026, 9, 8)),
        clock=lambda: NOW,
    )

    assert naive.observed_at == datetime(2026, 9, 8, 11, tzinfo=timezone.utc)
    assert naive.retrieved_at == datetime(2026, 9, 8, 11, 30, tzinfo=timezone.utc)
    assert statement.observed_at == datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_evaluator_is_deterministic_and_does_not_mutate_input() -> None:
    item = evidence(missing_inputs=("dividend",), effectiveness_sample_size=0)

    first = evaluate_evidence(item, clock=lambda: NOW)
    second = evaluate_evidence(item, clock=lambda: NOW)

    assert first == second
    assert item == evidence(missing_inputs=("dividend",), effectiveness_sample_size=0)


def test_response_model_accepts_the_shared_public_shape() -> None:
    state = evaluate_evidence(evidence(), clock=lambda: NOW)
    response = EvidenceDisplayResponse.model_validate(state.to_public_dict())

    assert response.schema_version == "evidence-display.v1"
    assert response.observed_at == NOW - timedelta(hours=1)
    assert response.action_eligibility == "eligible"


def test_compatibility_adapter_is_additive_and_does_not_mutate_existing_values() -> None:
    payload = {"value": 12.34, "confidence_label": "high", "nested": {"kept": True}}
    state = evaluate_evidence(evidence(confidence=0.99), clock=lambda: NOW)

    adapted = attach_evidence_display(payload, state)

    assert {key: adapted[key] for key in payload} == payload
    assert adapted["evidence"]["confidence"] == 0.99
    adapted["nested"]["kept"] = False
    assert payload["nested"]["kept"] is True


def test_allowlisted_adapter_omits_raw_provider_and_secret_fields() -> None:
    payload = {
        "value": 12.34,
        "label": "Example",
        "raw_payload": {"Authorization": "Bearer secret-token"},
        "provider_debug": {"request": "private"},
    }
    state = evaluate_evidence(evidence(), clock=lambda: NOW)

    public = select_public_fields_with_evidence(payload, ("value", "label"), state)

    assert public["value"] == 12.34
    assert "raw_payload" not in public
    assert "provider_debug" not in public
    assert "secret-token" not in str(public)


@pytest.mark.parametrize(
    "payload",
    [
        {"raw_payload": {"safe-looking": True}},
        {"nested": {"credentials": "secret"}},
        {"items": [{"access_token": "secret"}]},
        {"nested": {"x_bearer_token": "secret"}},
    ],
)
def test_additive_adapter_rejects_known_sensitive_shapes(payload: dict) -> None:
    state = evaluate_evidence(evidence(), clock=lambda: NOW)

    with pytest.raises(ValueError, match="sensitive or raw-provider"):
        attach_evidence_display(payload, state)


def test_input_validation_rejects_ambiguous_policy_data() -> None:
    with pytest.raises(ValueError, match="unknown evidence_type"):
        replace(evidence(), evidence_type="generic")
    with pytest.raises(ValueError, match="compact display label"):
        replace(evidence(), source_name="provider\nprivate")
    with pytest.raises(ValueError, match="confidence must be between"):
        replace(evidence(), confidence=1.1)
    with pytest.raises(ValueError, match="non-negative"):
        replace(evidence(), effectiveness_sample_size=-1)


def test_display_state_rejects_callers_that_bypass_policy_precedence() -> None:
    with pytest.raises(ValueError, match="blocking evidence"):
        EvidenceDisplayState(
            evidence_type="price",
            source_kind="fixture",
            source_name="sample",
            source_health="healthy",
            freshness_state="current",
            coverage_state="complete",
            action_eligibility="eligible",
            reason_codes=("evidence.source_kind.fixture",),
        )
    with pytest.raises(ValueError, match="limited evidence"):
        EvidenceDisplayState(
            evidence_type="news",
            source_kind="real",
            source_name="wire",
            source_health="degraded",
            freshness_state="current",
            coverage_state="complete",
            action_eligibility="eligible",
            reason_codes=("evidence.source_health.degraded",),
        )
