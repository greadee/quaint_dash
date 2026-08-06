"""DuckDB persistence for immutable deterministic candidate runs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dashboard.ai_brain.candidates.canonical import (
    canonical_hash,
    canonical_json,
    normalize_decimal,
)
from dashboard.ai_brain.candidates.models import (
    CandidateEvidenceRef,
    CandidateReview,
    CandidateRun,
    CandidateSourceWatermark,
)
from dashboard.ai_brain.candidates.serialization import candidate_review_from_json


class CandidatePersistenceError(RuntimeError):
    """Base error for candidate persistence integrity failures."""


class CandidatePersistenceConflict(CandidatePersistenceError):
    """Raised when an immutable run identity is reused for different material output."""


class CandidatePersistenceIntegrityError(CandidatePersistenceError):
    """Raised when persisted candidate data no longer matches its canonical contract."""


def ensure_candidate_schema(conn: Any) -> None:
    schema_path = Path(__file__).resolve().parents[2] / "db" / "migrations" / "candidate_runs.sql"
    conn.execute(schema_path.read_text(encoding="utf-8"))


class CandidateRunRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def ensure_schema(self) -> None:
        ensure_candidate_schema(self.conn)

    def save(self, run: CandidateRun) -> bool:
        """Persist one immutable run; return False when the same run already exists."""

        if not run.output_hash_is_valid:
            raise CandidatePersistenceIntegrityError("candidate run output hash is invalid")
        evidence = _candidate_evidence_registry(run)
        existing = self.conn.execute(
            "SELECT input_snapshot_hash, output_hash FROM candidate_run WHERE run_id = ?",
            [run.run_id],
        ).fetchone()
        if existing is not None:
            if existing[0] != run.input_snapshot_hash or existing[1] != run.output_hash:
                raise CandidatePersistenceConflict(
                    "candidate run identity already exists with different material output"
                )
            stored = self.get(run.run_id)
            if stored is None or canonical_hash(stored) != canonical_hash(run):
                raise CandidatePersistenceConflict(
                    "candidate run identity already exists with different canonical content"
                )
            return False

        self.conn.execute("BEGIN TRANSACTION")
        try:
            self._insert_run(run)
            self._insert_watermarks(run)
            self._insert_evidence(run.run_id, evidence.values())
            for review in sorted(run.candidate_reviews, key=lambda item: item.candidate_id):
                self._insert_review(review)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return True

    def get(self, run_id: str) -> CandidateRun | None:
        row = self.conn.execute(
            """
            SELECT
                run_id, portfolio_id, as_of, schema_version, methodology_version,
                reason_codes_version, evidence_schema_version, investor_profile_id,
                investor_profile_schema_version, investor_profile_methodology_version,
                input_snapshot_hash, output_hash, run_status, blocking_conditions_json,
                created_at, runtime_ms, request_id
            FROM candidate_run
            WHERE run_id = ?
            """,
            [run_id],
        ).fetchone()
        if row is None:
            return None
        watermarks = self._load_watermarks(run_id)
        reviews = self._load_reviews(run_id)
        run = CandidateRun(
            run_id=row[0],
            portfolio_id=row[1],
            as_of=_utc(row[2]),
            schema_version=row[3],
            methodology_version=row[4],
            reason_codes_version=row[5],
            evidence_schema_version=row[6],
            investor_profile_id=row[7],
            investor_profile_schema_version=row[8],
            investor_profile_methodology_version=row[9],
            input_snapshot_hash=row[10],
            output_hash=row[11],
            source_watermarks=watermarks,
            candidate_reviews=reviews,
            run_status=row[12],
            blocking_conditions=tuple(json.loads(str(row[13]))),
            created_at=_utc(row[14]),
            runtime_ms=int(row[15]) if row[15] is not None else None,
            request_id=row[16],
        )
        if not run.output_hash_is_valid:
            raise CandidatePersistenceIntegrityError("persisted candidate run output hash is invalid")
        self._validate_evidence_rows(run)
        return run

    def list_for_portfolio(self, portfolio_id: str) -> tuple[CandidateRun, ...]:
        rows = self.conn.execute(
            """
            SELECT run_id
            FROM candidate_run
            WHERE portfolio_id = ?
            ORDER BY as_of, run_id
            """,
            [portfolio_id],
        ).fetchall()
        runs = tuple(self.get(row[0]) for row in rows)
        if any(run is None for run in runs):
            raise CandidatePersistenceIntegrityError("candidate run disappeared during history read")
        return tuple(run for run in runs if run is not None)

    def _insert_run(self, run: CandidateRun) -> None:
        self.conn.execute(
            """
            INSERT INTO candidate_run(
                run_id, portfolio_id, as_of, schema_version, methodology_version,
                reason_codes_version, evidence_schema_version, investor_profile_id,
                investor_profile_schema_version, investor_profile_methodology_version,
                input_snapshot_hash, output_hash, run_status, blocking_conditions_json,
                created_at, runtime_ms, request_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run.run_id,
                run.portfolio_id,
                run.as_of,
                run.schema_version,
                run.methodology_version,
                run.reason_codes_version,
                run.evidence_schema_version,
                run.investor_profile_id,
                run.investor_profile_schema_version,
                run.investor_profile_methodology_version,
                run.input_snapshot_hash,
                run.output_hash,
                run.run_status,
                _json_array(run.blocking_conditions),
                run.created_at,
                run.runtime_ms,
                run.request_id,
            ],
        )

    def _insert_watermarks(self, run: CandidateRun) -> None:
        for watermark in sorted(run.source_watermarks, key=lambda item: item.source_domain):
            self.conn.execute(
                """
                INSERT INTO candidate_source_watermark(
                    run_id, source_domain, source_schema_version, as_of, coverage_state
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    run.run_id,
                    watermark.source_domain,
                    watermark.source_schema_version,
                    watermark.as_of,
                    watermark.coverage_state,
                ],
            )

    def _insert_evidence(
        self,
        run_id: str,
        evidence_refs: Iterable[CandidateEvidenceRef],
    ) -> None:
        for ref in sorted(evidence_refs, key=lambda item: item.evidence_id):
            self.conn.execute(
                """
                INSERT INTO candidate_evidence(
                    run_id, evidence_id, evidence_schema_version, source_domain,
                    source_schema_version, source_record_id, as_of, payload_hash,
                    freshness_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    ref.evidence_id,
                    ref.evidence_schema_version,
                    ref.source_domain,
                    ref.source_schema_version,
                    ref.source_record_id,
                    ref.as_of,
                    ref.payload_hash,
                    ref.freshness_state,
                ],
            )

    def _insert_review(self, review: CandidateReview) -> None:
        payload = canonical_json(review)
        self.conn.execute(
            """
            INSERT INTO candidate_review(
                review_id, run_id, candidate_id, asset_id, ticker, schema_version,
                methodology_version, reason_codes_version, fit_score,
                diversification_score, redundancy_score, data_as_of, methodology_as_of,
                eligibility_state, payload_hash, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                review.review_id,
                review.run_id,
                review.candidate_id,
                review.asset_id,
                review.ticker,
                review.schema_version,
                review.methodology_version,
                review.reason_codes_version,
                _db_decimal(review.fit_score.value),
                _db_decimal(review.diversification_score.value),
                _db_decimal(review.redundancy_score.value),
                review.data_as_of,
                review.methodology_as_of,
                review.eligibility_state,
                review.output_hash,
                payload,
            ],
        )
        for reason_code in sorted(review.reason_codes):
            self.conn.execute(
                "INSERT INTO candidate_review_reason VALUES (?, ?)",
                [review.review_id, reason_code],
            )
        for match in sorted(
            review.source_matches,
            key=lambda item: (
                item.source_family,
                item.reason_code,
                item.source_methodology_version,
            ),
        ):
            self.conn.execute(
                """
                INSERT INTO candidate_source_match(
                    review_id, source_family, source_methodology_version, reason_code,
                    nomination_strength, evidence_ids_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    review.review_id,
                    match.source_family,
                    match.source_methodology_version,
                    match.reason_code,
                    _db_decimal(match.nomination_strength),
                    _json_array(ref.evidence_id for ref in match.evidence_refs),
                ],
            )
        for metric in sorted(review.missing_metrics, key=lambda item: item.metric_code):
            self.conn.execute(
                """
                INSERT INTO candidate_missing_metric(
                    review_id, metric_code, criticality, expected_source, reason_code,
                    guardrail_effect
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    review.review_id,
                    metric.metric_code,
                    metric.criticality,
                    metric.expected_source,
                    metric.reason_code,
                    metric.guardrail_effect,
                ],
            )
        for warning in sorted(review.warnings, key=lambda item: item.warning_code):
            self.conn.execute(
                """
                INSERT INTO candidate_warning(
                    review_id, warning_code, severity, blocking, evidence_ids_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    review.review_id,
                    warning.warning_code,
                    warning.severity,
                    warning.blocking,
                    _json_array(ref.evidence_id for ref in warning.evidence_refs),
                ],
            )

    def _load_watermarks(self, run_id: str) -> tuple[CandidateSourceWatermark, ...]:
        rows = self.conn.execute(
            """
            SELECT source_domain, source_schema_version, as_of, coverage_state
            FROM candidate_source_watermark
            WHERE run_id = ?
            ORDER BY source_domain
            """,
            [run_id],
        ).fetchall()
        return tuple(
            CandidateSourceWatermark(
                source_domain=row[0],
                source_schema_version=row[1],
                as_of=_utc(row[2]) if row[2] is not None else None,
                coverage_state=row[3],
            )
            for row in rows
        )

    def _load_reviews(self, run_id: str) -> tuple[CandidateReview, ...]:
        rows = self.conn.execute(
            """
            SELECT
                review_id, run_id, candidate_id, asset_id, ticker, schema_version,
                methodology_version, reason_codes_version, fit_score,
                diversification_score, redundancy_score, data_as_of, methodology_as_of,
                eligibility_state, payload_hash, payload_json
            FROM candidate_review
            WHERE run_id = ?
            ORDER BY candidate_id
            """,
            [run_id],
        ).fetchall()
        reviews = []
        for row in rows:
            try:
                review = candidate_review_from_json(str(row[15]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CandidatePersistenceIntegrityError(
                    f"invalid candidate review payload: {row[0]}"
                ) from exc
            self._validate_review_row(row, review)
            self._validate_review_children(review)
            reviews.append(review)
        return tuple(reviews)

    def _validate_review_row(self, row: tuple[Any, ...], review: CandidateReview) -> None:
        stored_values = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            _decimal_text(row[8]),
            _decimal_text(row[9]),
            _decimal_text(row[10]),
            _utc(row[11]),
            _utc(row[12]),
            row[13],
            row[14],
        )
        review_values = (
            review.review_id,
            review.run_id,
            review.candidate_id,
            review.asset_id,
            review.ticker,
            review.schema_version,
            review.methodology_version,
            review.reason_codes_version,
            _decimal_text(review.fit_score.value),
            _decimal_text(review.diversification_score.value),
            _decimal_text(review.redundancy_score.value),
            review.data_as_of,
            review.methodology_as_of,
            review.eligibility_state,
            review.output_hash,
        )
        if stored_values != review_values or canonical_json(review) != str(row[15]):
            raise CandidatePersistenceIntegrityError(
                f"candidate review row does not match canonical payload: {review.review_id}"
            )

    def _validate_review_children(self, review: CandidateReview) -> None:
        reasons = tuple(
            row[0]
            for row in self.conn.execute(
                """
                SELECT reason_code FROM candidate_review_reason
                WHERE review_id = ? ORDER BY reason_code
                """,
                [review.review_id],
            ).fetchall()
        )
        if reasons != tuple(sorted(review.reason_codes)):
            raise CandidatePersistenceIntegrityError("candidate review reasons do not match payload")

        source_rows = self.conn.execute(
            """
            SELECT source_family, source_methodology_version, reason_code,
                   nomination_strength, evidence_ids_json
            FROM candidate_source_match
            WHERE review_id = ?
            ORDER BY source_family, reason_code, source_methodology_version
            """,
            [review.review_id],
        ).fetchall()
        expected_sources = tuple(
            (
                match.source_family,
                match.source_methodology_version,
                match.reason_code,
                _decimal_text(match.nomination_strength),
                _json_array(ref.evidence_id for ref in match.evidence_refs),
            )
            for match in sorted(
                review.source_matches,
                key=lambda item: (
                    item.source_family,
                    item.reason_code,
                    item.source_methodology_version,
                ),
            )
        )
        actual_sources = tuple(
            (row[0], row[1], row[2], _decimal_text(row[3]), str(row[4])) for row in source_rows
        )
        if actual_sources != expected_sources:
            raise CandidatePersistenceIntegrityError("candidate source matches do not match payload")

        metric_rows = self.conn.execute(
            """
            SELECT metric_code, criticality, expected_source, reason_code, guardrail_effect
            FROM candidate_missing_metric
            WHERE review_id = ? ORDER BY metric_code
            """,
            [review.review_id],
        ).fetchall()
        expected_metrics = tuple(
            (
                item.metric_code,
                item.criticality,
                item.expected_source,
                item.reason_code,
                item.guardrail_effect,
            )
            for item in sorted(review.missing_metrics, key=lambda item: item.metric_code)
        )
        if tuple(metric_rows) != expected_metrics:
            raise CandidatePersistenceIntegrityError("candidate missing metrics do not match payload")

        warning_rows = self.conn.execute(
            """
            SELECT warning_code, severity, blocking, evidence_ids_json
            FROM candidate_warning
            WHERE review_id = ? ORDER BY warning_code
            """,
            [review.review_id],
        ).fetchall()
        expected_warnings = tuple(
            (
                item.warning_code,
                item.severity,
                item.blocking,
                _json_array(ref.evidence_id for ref in item.evidence_refs),
            )
            for item in sorted(review.warnings, key=lambda item: item.warning_code)
        )
        if tuple((row[0], row[1], row[2], str(row[3])) for row in warning_rows) != expected_warnings:
            raise CandidatePersistenceIntegrityError("candidate warnings do not match payload")

    def _validate_evidence_rows(self, run: CandidateRun) -> None:
        expected = _candidate_evidence_registry(run)
        rows = self.conn.execute(
            """
            SELECT evidence_id, evidence_schema_version, source_domain, source_schema_version,
                   source_record_id, as_of, payload_hash, freshness_state
            FROM candidate_evidence
            WHERE run_id = ? ORDER BY evidence_id
            """,
            [run.run_id],
        ).fetchall()
        actual = {
            row[0]: (
                row[1],
                row[2],
                row[3],
                row[4],
                _utc(row[5]),
                row[6],
                row[7],
            )
            for row in rows
        }
        expected_values = {
            evidence_id: (
                ref.evidence_schema_version,
                ref.source_domain,
                ref.source_schema_version,
                ref.source_record_id,
                ref.as_of,
                ref.payload_hash,
                ref.freshness_state,
            )
            for evidence_id, ref in expected.items()
        }
        if actual != expected_values:
            raise CandidatePersistenceIntegrityError("candidate evidence rows do not match payloads")


def _candidate_evidence_registry(run: CandidateRun) -> dict[str, CandidateEvidenceRef]:
    evidence: dict[str, CandidateEvidenceRef] = {}
    for review in run.candidate_reviews:
        for ref in review.evidence_refs:
            existing = evidence.get(ref.evidence_id)
            if existing is not None and existing != ref:
                raise CandidatePersistenceIntegrityError(
                    "identical evidence IDs must be consistent across a candidate run"
                )
            evidence[ref.evidence_id] = ref
    return evidence


def _json_array(values: Iterable[str]) -> str:
    return json.dumps(sorted(values), separators=(",", ":"))


def _decimal_text(value: Decimal | None) -> str | None:
    return normalize_decimal(value) if value is not None else None


def _db_decimal(value: Decimal | None) -> Decimal | None:
    return Decimal(normalize_decimal(value)) if value is not None else None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
