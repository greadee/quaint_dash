"""Read-only quality, value, and momentum screen source adapters."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from dashboard.ai_brain.candidates.models import (
    CandidateSourceMatch,
    CandidateSourceWatermark,
)
from dashboard.ai_brain.candidates.source_adapters import (
    CandidateNomination,
    SourceAdapterResult,
    candidate_source_evidence,
)

SCREEN_POLICY_VERSION = "candidate-screens.v1"
QUALITY_SCREEN_SCHEMA_VERSION = "business-strength-screen.v1"
VALUE_SCREEN_SCHEMA_VERSION = "asset-analytics-value-screen.v1"
MOMENTUM_SCREEN_SCHEMA_VERSION = "ticker-factor-momentum-screen.v1"

QUALITY_MIN_SCORE = 70.0
QUALITY_MIN_CONFIDENCE = 60.0
QUALITY_MIN_COMPLETENESS = 60.0
VALUE_MIN_SCORE = 65.0
MOMENTUM_MIN_SCORE = 70.0


class CandidateScreenAdapters:
    """Nominate candidates from stored screens without hydrating source data."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def quality(self, *, as_of: datetime, limit: int = 25) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit(limit)
        if not _table_exists(self.conn, "business_strength_analysis_run"):
            return _missing_result(
                "quality_screen",
                "business-strength-scorecard",
                QUALITY_SCREEN_SCHEMA_VERSION,
            )
        rows = self.conn.execute(
            """
            WITH latest AS (
                SELECT
                    run.id,
                    run.asset_id,
                    COALESCE(asset.symbol, run.asset_id) AS ticker,
                    run.analysis_date,
                    run.source_data_as_of,
                    run.overall_score,
                    run.confidence_score,
                    run.completeness_score,
                    run.classification,
                    run.status,
                    methodology.version,
                    ROW_NUMBER() OVER (
                        PARTITION BY run.asset_id
                        ORDER BY run.analysis_date DESC, run.id DESC
                    ) AS snapshot_rank
                FROM business_strength_analysis_run run
                JOIN business_strength_methodology methodology
                  ON methodology.id = run.methodology_id
                LEFT JOIN asset
                  ON asset.asset_id = run.asset_id
                 AND asset.updated_at <= ?
                WHERE run.analysis_date <= ?
                  AND (
                    run.source_data_as_of IS NULL
                    OR run.source_data_as_of <= ?
                  )
            )
            SELECT
                id, asset_id, ticker, analysis_date, source_data_as_of,
                overall_score, confidence_score, completeness_score,
                classification, status, version
            FROM latest
            WHERE snapshot_rank = 1
              AND status IN ('complete', 'partial')
              AND overall_score BETWEEN ? AND 100
              AND confidence_score BETWEEN ? AND 100
              AND completeness_score BETWEEN ? AND 100
            ORDER BY overall_score DESC, confidence_score DESC, asset_id
            LIMIT ?
            """,
            [
                _as_db_timestamp(as_of),
                as_of.date(),
                _as_db_timestamp(as_of),
                QUALITY_MIN_SCORE,
                QUALITY_MIN_CONFIDENCE,
                QUALITY_MIN_COMPLETENESS,
                limit,
            ],
        ).fetchall()
        source_as_of = self.conn.execute(
            """
            SELECT MAX(analysis_date)
            FROM business_strength_analysis_run
            WHERE analysis_date <= ?
            """,
            [as_of.date()],
        ).fetchone()[0]
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[1]),
                ticker=str(row[2]).upper(),
                source_match=CandidateSourceMatch(
                    source_family="quality_screen",
                    source_methodology_version=SCREEN_POLICY_VERSION,
                    reason_code="source.screen.quality",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="business-strength-scorecard",
                            source_schema_version=QUALITY_SCREEN_SCHEMA_VERSION,
                            source_record_id=f"business-strength-run:{row[0]}",
                            as_of=_source_timestamp(row[4], row[3]),
                            payload={
                                "analysis_run_id": row[0],
                                "asset_id": row[1],
                                "analysis_date": row[3],
                                "source_data_as_of": (
                                    _as_utc(row[4]) if row[4] is not None else None
                                ),
                                "overall_score": row[5],
                                "confidence_score": row[6],
                                "completeness_score": row[7],
                                "classification": row[8],
                                "status": row[9],
                                "source_methodology_version": row[10],
                                "screen_policy_version": SCREEN_POLICY_VERSION,
                                "thresholds": {
                                    "score": QUALITY_MIN_SCORE,
                                    "confidence": QUALITY_MIN_CONFIDENCE,
                                    "completeness": QUALITY_MIN_COMPLETENESS,
                                },
                            },
                        ),
                    ),
                    nomination_strength=_score_decimal(row[5]),
                ),
            )
            for row in rows
        )
        return _result(
            source_family="quality_screen",
            source_domain="business-strength-scorecard",
            source_schema_version=QUALITY_SCREEN_SCHEMA_VERSION,
            source_as_of=source_as_of,
            nominations=nominations,
        )

    def value(self, *, as_of: datetime, limit: int = 25) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit(limit)
        if not _table_exists(self.conn, "asset_analytics_snapshot"):
            return _missing_result(
                "value_screen",
                "asset-analytics-valuation",
                VALUE_SCREEN_SCHEMA_VERSION,
            )
        rows = self.conn.execute(
            """
            WITH latest AS (
                SELECT
                    snapshot.asset_id,
                    COALESCE(asset.symbol, snapshot.asset_id) AS ticker,
                    snapshot.snapshot_date,
                    snapshot.payload_json,
                    snapshot.missing_inputs_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY snapshot.asset_id
                        ORDER BY snapshot.snapshot_date DESC
                    ) AS snapshot_rank
                FROM asset_analytics_snapshot snapshot
                LEFT JOIN asset
                  ON asset.asset_id = snapshot.asset_id
                 AND asset.updated_at <= ?
                WHERE snapshot.snapshot_date <= ?
            )
            SELECT asset_id, ticker, snapshot_date, payload_json, missing_inputs_json
            FROM latest
            WHERE snapshot_rank = 1
            ORDER BY asset_id
            """,
            [_as_db_timestamp(as_of), as_of.date()],
        ).fetchall()
        qualified: list[tuple[Any, float, tuple[float, ...]]] = []
        for row in rows:
            payload = _json_object(row[3])
            margins = _valuation_margins(payload)
            if not margins:
                continue
            score = _value_score(margins)
            if score >= VALUE_MIN_SCORE:
                qualified.append((row, score, margins))
        qualified.sort(key=lambda item: (-item[1], str(item[0][0])))
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=CandidateSourceMatch(
                    source_family="value_screen",
                    source_methodology_version=SCREEN_POLICY_VERSION,
                    reason_code="source.screen.value",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="asset-analytics-valuation",
                            source_schema_version=VALUE_SCREEN_SCHEMA_VERSION,
                            source_record_id=f"asset-analytics:{row[2].isoformat()}:{row[0]}",
                            as_of=_as_utc(row[2]),
                            payload={
                                "asset_id": row[0],
                                "snapshot_date": row[2],
                                "margin_of_safety_values": margins,
                                "normalized_value_score": score,
                                "missing_inputs_json": row[4],
                                "screen_policy_version": SCREEN_POLICY_VERSION,
                                "minimum_score": VALUE_MIN_SCORE,
                            },
                        ),
                    ),
                    nomination_strength=_score_decimal(score),
                ),
            )
            for row, score, margins in qualified[:limit]
        )
        source_as_of = max((row[2] for row in rows), default=None)
        return _result(
            source_family="value_screen",
            source_domain="asset-analytics-valuation",
            source_schema_version=VALUE_SCREEN_SCHEMA_VERSION,
            source_as_of=source_as_of,
            nominations=nominations,
        )

    def momentum(self, *, as_of: datetime, limit: int = 25) -> SourceAdapterResult:
        as_of = _normalize_as_of(as_of)
        _validate_limit(limit)
        if not _table_exists(self.conn, "ticker_factor_snapshot"):
            return _missing_result(
                "momentum_screen",
                "ticker-factor",
                MOMENTUM_SCREEN_SCHEMA_VERSION,
            )
        rows = self.conn.execute(
            """
            WITH latest AS (
                SELECT
                    snapshot.asset_id,
                    COALESCE(asset.symbol, snapshot.ticker, snapshot.asset_id) AS ticker,
                    snapshot.snapshot_date,
                    snapshot.momentum_score,
                    snapshot.volatility_score,
                    snapshot.overall_factor_score,
                    snapshot.explanation,
                    ROW_NUMBER() OVER (
                        PARTITION BY snapshot.asset_id
                        ORDER BY snapshot.snapshot_date DESC
                    ) AS snapshot_rank
                FROM ticker_factor_snapshot snapshot
                LEFT JOIN asset
                  ON asset.asset_id = snapshot.asset_id
                 AND asset.updated_at <= ?
                WHERE snapshot.snapshot_date <= ?
            )
            SELECT
                asset_id, ticker, snapshot_date, momentum_score,
                volatility_score, overall_factor_score, explanation
            FROM latest
            WHERE snapshot_rank = 1
              AND momentum_score BETWEEN ? AND 100
            ORDER BY momentum_score DESC, asset_id
            LIMIT ?
            """,
            [
                _as_db_timestamp(as_of),
                as_of.date(),
                MOMENTUM_MIN_SCORE,
                limit,
            ],
        ).fetchall()
        source_as_of = self.conn.execute(
            """
            SELECT MAX(snapshot_date)
            FROM ticker_factor_snapshot
            WHERE snapshot_date <= ?
            """,
            [as_of.date()],
        ).fetchone()[0]
        nominations = tuple(
            CandidateNomination(
                source_asset_id=str(row[0]),
                ticker=str(row[1]).upper(),
                source_match=CandidateSourceMatch(
                    source_family="momentum_screen",
                    source_methodology_version=SCREEN_POLICY_VERSION,
                    reason_code="source.screen.momentum",
                    evidence_refs=(
                        candidate_source_evidence(
                            source_domain="ticker-factor",
                            source_schema_version=MOMENTUM_SCREEN_SCHEMA_VERSION,
                            source_record_id=f"ticker-factor:{row[2].isoformat()}:{row[0]}",
                            as_of=_as_utc(row[2]),
                            payload={
                                "asset_id": row[0],
                                "snapshot_date": row[2],
                                "momentum_score": row[3],
                                "volatility_score": row[4],
                                "overall_factor_score": row[5],
                                "explanation": row[6],
                                "screen_policy_version": SCREEN_POLICY_VERSION,
                                "minimum_score": MOMENTUM_MIN_SCORE,
                            },
                        ),
                    ),
                    nomination_strength=_score_decimal(row[3]),
                ),
            )
            for row in rows
        )
        return _result(
            source_family="momentum_screen",
            source_domain="ticker-factor",
            source_schema_version=MOMENTUM_SCREEN_SCHEMA_VERSION,
            source_as_of=source_as_of,
            nominations=nominations,
        )


def _result(
    *,
    source_family: str,
    source_domain: str,
    source_schema_version: str,
    source_as_of: date | datetime | None,
    nominations: tuple[CandidateNomination, ...],
) -> SourceAdapterResult:
    watermark = _as_utc(source_as_of) if source_as_of is not None else None
    limitations: tuple[str, ...]
    if watermark is None:
        limitations = (f"source.{source_family}.snapshot_missing",)
    elif not nominations:
        limitations = (f"source.{source_family}.no_qualifying_assets",)
    else:
        limitations = ()
    return SourceAdapterResult(
        source_family=source_family,
        watermark=CandidateSourceWatermark(
            source_domain=source_domain,
            source_schema_version=source_schema_version,
            as_of=watermark,
            coverage_state="available" if watermark is not None else "missing",
        ),
        nominations=nominations,
        limitations=limitations,
    )


def _missing_result(
    source_family: str,
    source_domain: str,
    source_schema_version: str,
) -> SourceAdapterResult:
    return _result(
        source_family=source_family,
        source_domain=source_domain,
        source_schema_version=source_schema_version,
        source_as_of=None,
        nominations=(),
    )


def _valuation_margins(payload: dict[str, Any]) -> tuple[float, ...]:
    margins: list[float] = []
    for key in ("discounted_cash_flow", "dividend_discount"):
        section = payload.get(key)
        if not isinstance(section, dict):
            continue
        value = section.get("margin_of_safety")
        if isinstance(value, (int, float)):
            margins.append(float(value))
    return tuple(sorted(margins))


def _value_score(margins: tuple[float, ...]) -> float:
    mean_margin = sum(margins) / len(margins)
    return round(max(0.0, min(100.0, ((mean_margin + 0.25) / 0.75) * 100.0)), 8)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    return parsed if isinstance(parsed, dict) else {}


def _normalize_as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("screen adapter as_of must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _as_db_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc, microsecond=0)
        return value.astimezone(timezone.utc).replace(microsecond=0)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _source_timestamp(value: datetime | None, fallback: date) -> datetime:
    return _as_utc(value if value is not None else fallback)


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 500:
        raise ValueError("screen limit must be between 1 and 500")


def _score_decimal(value: float) -> Decimal:
    return Decimal(str(round(float(value), 8)))


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
