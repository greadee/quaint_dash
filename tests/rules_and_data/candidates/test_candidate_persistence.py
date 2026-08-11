from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import duckdb
import pytest

from dashboard.rules_and_data.candidates import (
    CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    CANDIDATE_METHODOLOGY_VERSION,
    CANDIDATE_REASON_CODES_VERSION,
    CANDIDATE_REVIEW_SCHEMA_VERSION,
    CANDIDATE_RUN_SCHEMA_VERSION,
    CandidateEvidenceRef,
    CandidateHighlight,
    CandidateMissingMetric,
    CandidatePersistenceConflict,
    CandidatePersistenceIntegrityError,
    CandidateReview,
    CandidateRun,
    CandidateRunRepository,
    CandidateScore,
    CandidateScoreComponent,
    CandidateSourceMatch,
    CandidateSourceWatermark,
    CandidateWarning,
    candidate_evidence_id,
    candidate_id,
    candidate_review_id,
    candidate_run_id,
    canonical_json,
    ensure_candidate_schema,
)


AS_OF = datetime(2026, 8, 5, 20, 0, tzinfo=timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence(code: str) -> CandidateEvidenceRef:
    values = {
        "source_domain": "stock-ranking",
        "source_schema_version": "stock-ranking.v1",
        "source_record_id": f"ranking:{code}",
        "as_of": AS_OF,
        "payload_hash": _hash(f"payload:{code}"),
    }
    return CandidateEvidenceRef(
        evidence_id=candidate_evidence_id(**values),
        freshness_state="current",
        **values,
    )


def _score(
    score_type: str,
    value: str,
    evidence: CandidateEvidenceRef,
) -> CandidateScore:
    component = CandidateScoreComponent(
        component_code=f"component.{score_type}.fixture",
        value=Decimal(value),
        weight=Decimal("1"),
        contribution=Decimal(value),
        reason_codes=(f"score.{score_type}.fixture",),
        evidence_refs=(evidence,),
    )
    return CandidateScore(
        score_type=score_type,
        value=Decimal(value),
        components=(component,),
        evidence_refs=(evidence,),
    )


def _review(run_id: str, asset_id: str, ticker: str, score: str) -> CandidateReview:
    evidence = _evidence(asset_id)
    stable_candidate_id = candidate_id(asset_id)
    return CandidateReview(
        review_id=candidate_review_id(run_id, stable_candidate_id),
        run_id=run_id,
        candidate_id=stable_candidate_id,
        asset_id=asset_id,
        ticker=ticker,
        schema_version=CANDIDATE_REVIEW_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        reason_codes=("source.ranking.aggregate",),
        source_matches=(
            CandidateSourceMatch(
                source_family="ranking",
                source_methodology_version="stock-ranking.v1",
                reason_code="source.ranking.aggregate",
                evidence_refs=(evidence,),
                nomination_strength=Decimal("81.123456785"),
            ),
        ),
        fit_score=_score("fit", score, evidence),
        diversification_score=_score("diversification", "62.5", evidence),
        redundancy_score=_score("redundancy", "18.75", evidence),
        highlights=(
            CandidateHighlight(
                category="valuation",
                highlight_code="highlight.valuation.fixture",
                normalized_value=Decimal("58.125"),
                unit="score_0_100",
                direction="positive",
                as_of=AS_OF,
                evidence_refs=(evidence,),
            ),
        ),
        missing_metrics=(
            CandidateMissingMetric(
                metric_code="metric.sentiment.coverage",
                criticality="noncritical",
                expected_source="sentiment-snapshot",
                reason_code="missing.sentiment.coverage",
                guardrail_effect="none",
            ),
        ),
        warnings=(
            CandidateWarning(
                warning_code="warning.sentiment.missing",
                severity="info",
                blocking=False,
                evidence_refs=(evidence,),
            ),
        ),
        evidence_refs=(evidence,),
        data_as_of=AS_OF,
        methodology_as_of=AS_OF - timedelta(days=1),
        eligibility_state="eligible",
    )


def _run(snapshot: str, *, as_of: datetime = AS_OF) -> CandidateRun:
    input_hash = _hash(snapshot)
    run_id = candidate_run_id(CANDIDATE_METHODOLOGY_VERSION, input_hash)
    reviews = (
        _review(run_id, "asset:beta", "BETA", "73.333333335"),
        _review(run_id, "asset:alpha", "ALPHA", "77.125"),
    )
    provisional = CandidateRun(
        run_id=run_id,
        portfolio_id="portfolio:7",
        as_of=as_of,
        schema_version=CANDIDATE_RUN_SCHEMA_VERSION,
        methodology_version=CANDIDATE_METHODOLOGY_VERSION,
        reason_codes_version=CANDIDATE_REASON_CODES_VERSION,
        evidence_schema_version=CANDIDATE_EVIDENCE_SCHEMA_VERSION,
        investor_profile_id=f"profile:{_hash('profile')}",
        investor_profile_schema_version="investor-profile.v1",
        investor_profile_methodology_version="investor-profile.deterministic.v1",
        input_snapshot_hash=input_hash,
        output_hash="0" * 64,
        source_watermarks=(
            CandidateSourceWatermark(
                source_domain="watchlist",
                source_schema_version="watchlist.v1",
                as_of=AS_OF,
                coverage_state="partial",
            ),
            CandidateSourceWatermark(
                source_domain="stock-ranking",
                source_schema_version="stock-ranking.v1",
                as_of=AS_OF,
                coverage_state="available",
            ),
        ),
        candidate_reviews=reviews,
        run_status="completed",
        blocking_conditions=(),
        created_at=as_of,
        runtime_ms=145,
        request_id=f"request:{snapshot}",
    )
    return replace(provisional, output_hash=provisional.expected_output_hash)


@pytest.fixture
def repository():
    conn = duckdb.connect(":memory:")
    repo = CandidateRunRepository(conn)
    repo.ensure_schema()
    yield repo
    conn.close()


def test_candidate_schema_initialization_is_repeatable() -> None:
    conn = duckdb.connect(":memory:")
    try:
        ensure_candidate_schema(conn)
        ensure_candidate_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "candidate_run",
        "candidate_source_watermark",
        "candidate_review",
        "candidate_review_reason",
        "candidate_source_match",
        "candidate_evidence",
        "candidate_missing_metric",
        "candidate_warning",
    } <= tables


def test_candidate_run_round_trips_canonical_order_and_precision(repository) -> None:
    run = _run("snapshot-one")

    assert repository.save(run) is True
    loaded = repository.get(run.run_id)

    assert loaded is not None
    assert canonical_json(loaded) == canonical_json(run)
    assert loaded.output_hash == run.output_hash
    assert loaded.output_hash_is_valid
    assert tuple(review.candidate_id for review in loaded.candidate_reviews) == tuple(
        sorted(review.candidate_id for review in run.candidate_reviews)
    )
    assert {review.asset_id for review in loaded.candidate_reviews} == {
        "asset:alpha",
        "asset:beta",
    }
    assert tuple(item.source_domain for item in loaded.source_watermarks) == (
        "stock-ranking",
        "watchlist",
    )
    stored_scores = repository.conn.execute(
        "SELECT fit_score FROM candidate_review ORDER BY candidate_id"
    ).fetchall()
    assert all(isinstance(row[0], Decimal) for row in stored_scores)
    loaded_by_asset = {review.asset_id: review for review in loaded.candidate_reviews}
    assert loaded_by_asset["asset:beta"].fit_score.value == Decimal("73.33333334")


def test_repeating_same_run_is_idempotent_and_does_not_mutate_history(repository) -> None:
    run = _run("same-snapshot")
    retry = replace(
        run,
        created_at=run.created_at + timedelta(hours=1),
        runtime_ms=999,
        request_id="request:retry",
    )

    assert repository.save(run) is True
    assert repository.save(retry) is False
    assert repository.conn.execute("SELECT count(*) FROM candidate_run").fetchone()[0] == 1
    assert repository.get(run.run_id).created_at == run.created_at


def test_changed_snapshot_creates_distinct_run_and_preserves_history(repository) -> None:
    first = _run("snapshot-one")
    second = _run("snapshot-two", as_of=AS_OF + timedelta(days=1))

    assert repository.save(first) is True
    assert repository.save(second) is True

    history = repository.list_for_portfolio("portfolio:7")
    assert tuple(run.run_id for run in history) == (first.run_id, second.run_id)
    assert repository.get(first.run_id).output_hash == first.output_hash
    assert repository.get(second.run_id).output_hash == second.output_hash


def test_same_run_identity_with_changed_output_is_rejected(repository) -> None:
    run = _run("conflicting-snapshot")
    changed_review = replace(run.candidate_reviews[0], eligibility_state="downgraded")
    changed = replace(run, candidate_reviews=(changed_review, run.candidate_reviews[1]))
    changed = replace(changed, output_hash=changed.expected_output_hash)

    repository.save(run)

    with pytest.raises(CandidatePersistenceConflict, match="different material output"):
        repository.save(changed)


def test_invalid_run_hash_is_rejected_before_write(repository) -> None:
    invalid = replace(_run("invalid-hash"), output_hash="0" * 64)

    with pytest.raises(CandidatePersistenceIntegrityError, match="output hash is invalid"):
        repository.save(invalid)

    assert repository.conn.execute("SELECT count(*) FROM candidate_run").fetchone()[0] == 0


def test_normalized_row_corruption_fails_closed(repository) -> None:
    run = _run("corrupt-row")
    repository.save(run)
    review_id = run.candidate_reviews[0].review_id
    repository.conn.execute(
        "UPDATE candidate_review SET eligibility_state = 'blocked' WHERE review_id = ?",
        [review_id],
    )

    with pytest.raises(CandidatePersistenceIntegrityError, match="does not match canonical payload"):
        repository.get(run.run_id)
