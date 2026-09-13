from __future__ import annotations

from datetime import date

import pytest

from dashboard.analytics import PricePoint, risk_return_metrics
from dashboard.api.evidence_contract import (
    ACTION_ELIGIBILITY_STATES,
    COVERAGE_STATES,
    EVIDENCE_DISPLAY_SCHEMA_VERSION,
    FRESHNESS_STATES,
    SOURCE_KINDS,
    EvidenceDisplayState,
)


def test_evidence_display_vocabulary_is_explicit_and_stable() -> None:
    assert SOURCE_KINDS == frozenset({"real", "proxy", "fixture", "inferred", "unknown"})
    assert FRESHNESS_STATES == frozenset({"current", "warning", "stale", "blocked", "unknown"})
    assert COVERAGE_STATES == frozenset(
        {"complete", "partial", "missing", "unsupported", "unknown"}
    )
    assert ACTION_ELIGIBILITY_STATES == frozenset({"eligible", "caution", "blocked"})
    assert EVIDENCE_DISPLAY_SCHEMA_VERSION == "evidence-display.v1"


def test_evidence_display_state_accepts_current_complete_real_evidence() -> None:
    state = EvidenceDisplayState(
        source_kind="real",
        freshness_state="current",
        coverage_state="complete",
        action_eligibility="eligible",
    )

    assert state.reason_codes == ()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            dict(
                source_kind="proxy",
                freshness_state="current",
                coverage_state="complete",
                action_eligibility="caution",
            ),
            "non-current evidence display state requires a reason code",
        ),
        (
            dict(
                source_kind="real",
                freshness_state="stale",
                coverage_state="complete",
                action_eligibility="caution",
            ),
            "non-current evidence display state requires a reason code",
        ),
        (
            dict(
                source_kind="real",
                freshness_state="current",
                coverage_state="missing",
                action_eligibility="blocked",
            ),
            "non-current evidence display state requires a reason code",
        ),
    ],
)
def test_evidence_display_state_requires_explanation_for_non_current_evidence(
    state: dict[str, str],
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        EvidenceDisplayState(**state)


def test_evidence_display_state_rejects_unstable_reason_codes_and_unknown_states() -> None:
    with pytest.raises(ValueError, match="lowercase dotted codes"):
        EvidenceDisplayState(
            source_kind="fixture",
            freshness_state="stale",
            coverage_state="partial",
            action_eligibility="blocked",
            reason_codes=("Fixture data",),
        )
    with pytest.raises(ValueError, match="unknown freshness_state"):
        EvidenceDisplayState(
            source_kind="real",
            freshness_state="expired",
            coverage_state="complete",
            action_eligibility="eligible",
        )


def test_display_contract_is_read_only_and_does_not_change_financial_calculation_output() -> None:
    prices = [
        PricePoint(date(2026, 1, 1), 100.0),
        PricePoint(date(2026, 1, 2), 110.0),
        PricePoint(date(2026, 1, 3), 105.0),
    ]
    before = risk_return_metrics(prices)

    state = EvidenceDisplayState(
        source_kind="proxy",
        freshness_state="stale",
        coverage_state="partial",
        action_eligibility="blocked",
        reason_codes=("evidence.price.stale", "evidence.source.proxy"),
    )
    after = risk_return_metrics(prices)

    assert state.action_eligibility == "blocked"
    assert after == before
    assert after.cumulative_return == pytest.approx(0.05)
