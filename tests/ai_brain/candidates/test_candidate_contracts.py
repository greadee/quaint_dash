from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dashboard.ai_brain.candidates import (
    CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CANDIDATE_RUN_SCHEMA_VERSION,
    VOLATILE_HASH_FIELDS,
    CandidateEvidenceRef,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidateReview,
    CandidateRun,
    CandidateScore,
    CandidateScoreComponent,
    CandidateSourceMatch,
    CandidateSourceWatermark,
    CandidateWarning,
    candidate_evidence_id,
    candidate_id,
    candidate_review_id,
    candidate_run_id,
    canonical_hash,
    canonical_json,
)


AS_OF = datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc)
METHODOLOGY_AS_OF = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _payload_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _evidence(code: str, *, freshness: str = "current") -> CandidateEvidenceRef:
    payload_hash = _payload_hash(code)
    values = {
        "source_domain": "stock-ranking",
        "source_schema_version": "stock-ranking.v1",
        "source_record_id": f"ranking:{code}",
        "as_of": AS_OF,
        "payload_hash": payload_hash,
    }
    return CandidateEvidenceRef(
        evidence_id=candidate_evidence_id(**values),
        freshness_state=freshness,
        **values,
    )


def _score(
    score_type: str,
    value: str,
    evidence_refs: tuple[CandidateEvidenceRef, ...],
) -> CandidateScore:
    reason_code = f"score.{score_type}.observed"
    component = CandidateScoreComponent(
        component_code=f"component.{score_type}.observed",
        value=Decimal(value),
        weight=Decimal("1"),
        contribution=Decimal(value),
        reason_codes=(reason_code,),
        evidence_refs=evidence_refs,
    )
    return CandidateScore(
        score_type=score_type,
        value=Decimal(value),
        components=(component,),
        evidence_refs=evidence_refs,
    )


def _review(
    *,
    asset_id: str = "asset:321",
    ticker: str = "ACME",
    evidence_refs: tuple[CandidateEvidenceRef, ...] | None = None,
    source_matches: tuple[CandidateSourceMatch, ...] | None = None,
    reason_codes: tuple[str, ...] | None = None,
) -> CandidateReview:
    evidence_refs = evidence_refs or (_evidence("ranking"), _evidence("watchlist"))
    run_id = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, _payload_hash("snapshot"))
    stable_candidate_id = candidate_id(asset_id)
    source_matches = source_matches or (
        CandidateSourceMatch(
            source_family="ranking",
            source_methodology_version="stock-ranking.v1",
            reason_code="source.ranking.aggregate",
            nomination_strength=Decimal("82.500000004"),
            evidence_refs=(evidence_refs[0],),
        ),
        CandidateSourceMatch(
            source_family="watchlist",
            source_methodology_version="watchlist.v1",
            reason_code="source.watchlist.active",
            evidence_refs=(evidence_refs[1],),
        ),
    )
    reason_codes = reason_codes or (
        "source.ranking.aggregate",
        "source.watchlist.active",
    )
    return CandidateReview(
        review_id=candidate_review_id(run_id, stable_candidate_id),
        run_id=run_id,
        candidate_id=stable_candidate_id,
        asset_id=asset_id,
        ticker=ticker,
        schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        reason_codes=reason_codes,
        source_matches=source_matches,
        fit_score=_score("fit", "76.25", evidence_refs),
        diversification_score=_score("diversification", "64.50", evidence_refs),
        redundancy_score=_score("redundancy", "20.00", evidence_refs),
        highlights=(
            CandidateHighlight(
                category="valuation",
                highlight_code="highlight.valuation.relative",
                normalized_value=Decimal("61.25"),
                unit="score_0_100",
                direction="positive",
                as_of=AS_OF,
                evidence_refs=(evidence_refs[0],),
            ),
        ),
        missing_metrics=(),
        warnings=(
            CandidateWarning(
                warning_code="warning.coverage.partial",
                severity="warning",
                blocking=False,
                evidence_refs=(evidence_refs[1],),
            ),
        ),
        evidence_refs=evidence_refs,
        data_as_of=AS_OF,
        methodology_as_of=METHODOLOGY_AS_OF,
        eligibility_state="downgraded",
    )


def _run(review: CandidateReview, *, created_at: datetime = AS_OF) -> CandidateRun:
    provisional = CandidateRun(
        run_id=review.run_id,
        portfolio_id="portfolio:7",
        as_of=AS_OF,
        schema_version=CANDIDATE_RUN_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        evidence_schema_version=CANDIDATE_EVIDENCE_SCHEMA_VERSION,
        investor_profile_id=f"profile:{_payload_hash('profile')}",
        investor_profile_schema_version="investor-profile.v1",
        investor_profile_methodology_version="investor-profile.deterministic.v1",
        input_snapshot_hash=_payload_hash("snapshot"),
        output_hash="0" * 64,
        source_watermarks=(
            CandidateSourceWatermark(
                source_domain="stock-ranking",
                source_schema_version="stock-ranking.v1",
                as_of=AS_OF,
                coverage_state="available",
            ),
            CandidateSourceWatermark(
                source_domain="watchlist",
                source_schema_version="watchlist.v1",
                as_of=AS_OF,
                coverage_state="available",
            ),
        ),
        candidate_reviews=(review,),
        run_status="completed",
        blocking_conditions=(),
        created_at=created_at,
        runtime_ms=125,
        request_id="request-one",
    )
    return replace(provisional, output_hash=provisional.expected_output_hash)


def test_candidate_review_rejects_malformed_and_mismatched_ids() -> None:
    review = _review()

    with pytest.raises(ValueError, match="candidate_id does not match"):
        replace(review, candidate_id=f"candidate:{'0' * 64}")
    with pytest.raises(ValueError, match="review_id does not match"):
        replace(review, review_id=f"candidate-review:{'0' * 64}")
    with pytest.raises(ValueError, match="run_id must use"):
        replace(review, run_id="run:bad")


def test_candidate_evidence_rejects_malformed_or_mismatched_identity() -> None:
    evidence = _evidence("identity")

    with pytest.raises(ValueError, match="does not match"):
        replace(evidence, evidence_id=f"candidate-evidence:{'0' * 64}")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(evidence, payload_hash="not-a-hash")


@pytest.mark.parametrize("state", ["recommended", "pending", "unknown"])
def test_candidate_review_rejects_unknown_eligibility_states(state: str) -> None:
    with pytest.raises(ValueError, match="unknown candidate eligibility state"):
        replace(_review(), eligibility_state=state)


def test_contracts_reject_unknown_nested_states() -> None:
    with pytest.raises(ValueError, match="unknown evidence freshness"):
        replace(_evidence("freshness"), freshness_state="expired")
    with pytest.raises(ValueError, match="unknown candidate source family"):
        replace(_review().source_matches[0], source_family="social_media")
    with pytest.raises(ValueError, match="unknown candidate score type"):
        replace(_review().fit_score, score_type="alpha")


def test_candidate_review_rejects_duplicate_reason_codes() -> None:
    with pytest.raises(ValueError, match="candidate reason codes must be unique"):
        replace(
            _review(),
            reason_codes=("source.ranking.aggregate", "source.ranking.aggregate"),
        )


def test_candidate_review_rejects_top_level_evidence_free_contract() -> None:
    with pytest.raises(ValueError, match="require stable evidence"):
        replace(_review(), evidence_refs=())


def test_candidate_review_rejects_conflicting_evidence_for_the_same_id() -> None:
    review = _review()
    conflicting = replace(review.evidence_refs[0], freshness_state="stale")

    with pytest.raises(ValueError, match="identical evidence IDs"):
        replace(review, evidence_refs=(conflicting, review.evidence_refs[1]))


def test_candidate_source_match_rejects_evidence_free_nomination() -> None:
    with pytest.raises(ValueError, match="source matches require evidence"):
        replace(_review().source_matches[0], evidence_refs=())


def test_null_score_requires_structured_missing_metric() -> None:
    review = _review()
    null_fit = CandidateScore(
        score_type="fit",
        value=None,
        components=(),
        evidence_refs=(),
        missing_metric_code="score.fit.unavailable",
    )

    with pytest.raises(ValueError, match="must exist in candidate missing_metrics"):
        replace(review, fit_score=null_fit)

    missing = CandidateMissingMetric(
        metric_code="score.fit.unavailable",
        criticality="critical",
        expected_source="investor-profile",
        reason_code="missing.profile.fit_inputs",
        guardrail_effect="block",
    )
    blocked = replace(
        review,
        fit_score=null_fit,
        missing_metrics=(missing,),
        eligibility_state="blocked",
    )

    assert blocked.fit_score.value is None
    assert blocked.missing_metrics == (missing,)


def test_canonically_equivalent_permutations_serialize_and_hash_identically() -> None:
    review = _review()
    permuted = replace(
        review,
        evidence_refs=tuple(reversed(review.evidence_refs)),
        source_matches=tuple(reversed(review.source_matches)),
        reason_codes=tuple(reversed(review.reason_codes)),
    )
    permuted = replace(
        permuted,
        fit_score=replace(
            permuted.fit_score,
            evidence_refs=tuple(reversed(permuted.fit_score.evidence_refs)),
        ),
        diversification_score=replace(
            permuted.diversification_score,
            evidence_refs=tuple(reversed(permuted.diversification_score.evidence_refs)),
        ),
        redundancy_score=replace(
            permuted.redundancy_score,
            evidence_refs=tuple(reversed(permuted.redundancy_score.evidence_refs)),
        ),
    )

    assert canonical_json(review) == canonical_json(permuted)
    assert review.output_hash == permuted.output_hash


def test_materially_different_evidence_changes_review_hash() -> None:
    first = _review()
    changed_evidence = (_evidence("ranking-changed"), first.evidence_refs[1])
    changed = _review(evidence_refs=changed_evidence)

    assert first.output_hash != changed.output_hash
    assert canonical_json(first) != canonical_json(changed)


def test_decimal_canonicalization_uses_eight_places_and_round_half_even() -> None:
    review = _review()
    serialized = canonical_json(review)

    assert '"nomination_strength":"82.50000000"' in serialized
    assert canonical_json(Decimal("1.234567885")) == '"1.23456788"'
    assert canonical_json(Decimal("1.234567895")) == '"1.23456790"'


def test_run_identity_output_hash_and_volatile_exclusions_are_stable() -> None:
    review = _review()
    first = _run(review)
    later = replace(
        first,
        created_at=AS_OF + timedelta(hours=1),
        runtime_ms=999,
        request_id="request-two",
    )

    assert VOLATILE_HASH_FIELDS == {
        "created_at",
        "output_hash",
        "request_id",
        "runtime_ms",
    }
    assert first.expected_output_hash == later.expected_output_hash
    assert first.output_hash_is_valid
    assert later.output_hash_is_valid
    assert canonical_json(first) != canonical_json(later)
    assert canonical_hash(first) == canonical_hash(later)
    assert first.run_id == candidate_run_id(
        CANDIDATE_METHODOLOGY_VERSION,
        first.input_snapshot_hash,
    )


def test_run_rejects_review_from_another_run_and_newer_data() -> None:
    run = _run(_review())
    other_run_id = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, _payload_hash("other"))
    other_review = replace(
        run.candidate_reviews[0],
        run_id=other_run_id,
        review_id=candidate_review_id(other_run_id, run.candidate_reviews[0].candidate_id),
    )

    with pytest.raises(ValueError, match="run_id must match"):
        replace(run, candidate_reviews=(other_review,))
    with pytest.raises(ValueError, match="cannot be newer"):
        replace(
            run,
            candidate_reviews=(
                replace(run.candidate_reviews[0], data_as_of=AS_OF + timedelta(seconds=1)),
            ),
        )


def test_run_rejects_incompatible_review_versions_and_future_watermarks() -> None:
    run = _run(_review())

    with pytest.raises(ValueError, match="methodology must match"):
        replace(
            run,
            candidate_reviews=(
                replace(run.candidate_reviews[0], methodology_version="candidate-engine.other.v1"),
            ),
        )
    with pytest.raises(ValueError, match="watermarks cannot be newer"):
        replace(
            run,
            source_watermarks=(
                replace(run.source_watermarks[0], as_of=AS_OF + timedelta(seconds=1)),
                run.source_watermarks[1],
            ),
        )


def test_candidate_run_exposes_derived_eligibility_counts() -> None:
    run = _run(_review())

    assert run.eligible_count == 0
    assert run.downgraded_count == 1
    assert run.blocked_count == 0
    assert run.output_hash_is_valid
