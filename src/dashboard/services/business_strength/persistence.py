"""Persistence for deterministic Business Strength scorecards."""

from __future__ import annotations

import json
from dataclasses import asdict

from dashboard.services.business_strength.models import (
    CATEGORY_LABELS,
    METHODOLOGY_VERSION,
    BusinessStrengthScorecard,
    BusinessStrengthTemplate,
    CategoryScore,
    MetricScore,
)


class BusinessStrengthRepository:
    def __init__(self, conn, registry) -> None:
        self.conn = conn
        self.registry = registry

    def upsert_methodology(self) -> int:
        self.conn.execute(
            """
            INSERT INTO business_strength_methodology(version, name, description, is_active)
            VALUES (?, ?, ?, TRUE)
            ON CONFLICT(version) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                is_active = TRUE,
                updated_at = now()
            """,
            [
                METHODOLOGY_VERSION,
                "Deterministic Business Strength Scorecard",
                "Sector-aware deterministic scoring from stored structured financial and metadata inputs.",
            ],
        )
        return int(self.conn.execute(
            "SELECT id FROM business_strength_methodology WHERE version = ?",
            [METHODOLOGY_VERSION],
        ).fetchone()[0])

    def upsert_template(self, template: BusinessStrengthTemplate) -> int:
        methodology_id = self.upsert_methodology()
        self.conn.execute(
            """
            INSERT INTO business_strength_template(
                methodology_id, template_code, sector, industry, name, version, configuration_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(methodology_id, template_code, version) DO UPDATE SET
                sector = excluded.sector,
                industry = excluded.industry,
                name = excluded.name,
                configuration_json = excluded.configuration_json,
                updated_at = now()
            """,
            [
                methodology_id,
                template.template_code,
                template.sector,
                template.industry,
                template.name,
                template.version,
                json.dumps({
                    "category_weights": template.category_weights,
                    "metrics": [asdict(metric) for metric in template.metrics],
                    "parent_template_code": template.parent_template_code,
                }),
            ],
        )
        return int(self.conn.execute(
            """
            SELECT id FROM business_strength_template
            WHERE methodology_id = ? AND template_code = ? AND version = ?
            """,
            [methodology_id, template.template_code, template.version],
        ).fetchone()[0])

    def upsert_classification(self, asset_id: str, template: BusinessStrengthTemplate, source: str, confidence: float) -> None:
        self.conn.execute(
            """
            INSERT INTO asset_business_classification(
                asset_id, sector, industry, template_code, classification_source, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, effective_from) DO UPDATE SET
                sector = excluded.sector,
                industry = excluded.industry,
                template_code = excluded.template_code,
                classification_source = excluded.classification_source,
                confidence = excluded.confidence,
                updated_at = now()
            """,
            [asset_id, template.sector, template.industry, template.template_code, source, confidence],
        )

    def persist(self, scorecard: BusinessStrengthScorecard, template_id: int) -> int:
        methodology_id = self.upsert_methodology()
        self.conn.execute(
            """
            INSERT INTO business_strength_analysis_run(
                asset_id, methodology_id, template_id, analysis_date, source_data_as_of,
                overall_score, classification, confidence_score, completeness_score,
                easy_hold_score, status, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            [
                scorecard.asset_id,
                methodology_id,
                template_id,
                scorecard.analysis_date,
                scorecard.source_data_as_of,
                scorecard.overall_score,
                scorecard.classification,
                scorecard.confidence_score,
                scorecard.completeness_score,
                scorecard.easy_hold_score,
                scorecard.status,
            ],
        )
        run_id = int(self.conn.execute("SELECT max(id) FROM business_strength_analysis_run").fetchone()[0])
        for category in scorecard.category_scores:
            self.conn.execute(
                """
                INSERT INTO business_strength_category_score(
                    analysis_run_id, category_code, raw_score, adjusted_score, category_weight,
                    confidence_score, completeness_score, explanation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    category.category_code,
                    category.raw_score,
                    category.adjusted_score,
                    category.category_weight,
                    category.confidence_score,
                    category.completeness_score,
                    category.explanation,
                ],
            )
            for metric in category.metrics:
                self.conn.execute(
                    """
                    INSERT INTO business_strength_metric_result(
                        analysis_run_id, category_code, metric_code, raw_value, normalized_value,
                        metric_score, metric_weight, contribution, unit, direction, value_status,
                        source, source_timestamp, peer_percentile, historical_percentile,
                        confidence, explanation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        metric.category_code,
                        metric.metric_code,
                        metric.raw_value,
                        metric.normalized_value,
                        metric.metric_score,
                        metric.metric_weight,
                        metric.contribution,
                        metric.unit,
                        metric.direction,
                        metric.value_status,
                        metric.source,
                        metric.source_timestamp,
                        metric.peer_percentile,
                        metric.historical_percentile,
                        metric.confidence,
                        metric.explanation,
                    ],
                )
        return run_id

    def latest(self, asset_id: str) -> BusinessStrengthScorecard | None:
        row = self.conn.execute(
            """
            SELECT
                r.id, r.asset_id, COALESCE(a.symbol, sc.symbol), COALESCE(a.name, sc.name),
                COALESCE(a.sector, sc.sector), COALESCE(a.industry, sc.industry),
                t.template_code, t.name, t.version, m.version,
                r.analysis_date, r.source_data_as_of, r.overall_score, r.classification,
                r.confidence_score, r.completeness_score, r.easy_hold_score, r.status
            FROM business_strength_analysis_run r
            JOIN business_strength_template t ON t.id = r.template_id
            JOIN business_strength_methodology m ON m.id = r.methodology_id
            LEFT JOIN asset a ON a.asset_id = r.asset_id
            LEFT JOIN stock_catalog sc ON sc.asset_id = r.asset_id
            WHERE UPPER(r.asset_id) = UPPER(?)
            ORDER BY r.analysis_date DESC, r.created_at DESC
            LIMIT 1
            """,
            [asset_id],
        ).fetchone()
        if row is None:
            return None
        categories = self._categories(int(row[0]))
        drivers = [m for c in categories for m in c.metrics if m.contribution is not None]
        missing = sorted({m.label for c in categories for m in c.metrics if m.value_status == "unknown"})
        stale = sorted({m.label for c in categories for m in c.metrics if m.value_status == "stale"})
        estimated = sorted({m.label for c in categories for m in c.metrics if m.value_status == "estimated"})
        peer_group = self._peer_group(row[6], row[1])
        return BusinessStrengthScorecard(
            analysis_run_id=int(row[0]),
            asset_id=row[1],
            symbol=row[2] or row[1],
            name=row[3],
            sector=row[4],
            industry=row[5],
            template_code=row[6],
            template_name=row[7],
            template_version=int(row[8]),
            methodology_version=row[9],
            analysis_date=row[10],
            source_data_as_of=row[11],
            overall_score=row[12],
            score_10=round(row[12] / 10, 1) if row[12] is not None else None,
            classification=row[13],
            confidence_score=row[14],
            completeness_score=row[15],
            easy_hold_score=row[16],
            easy_hold_label=self._classification(row[16]),
            status=row[17],
            missing_critical_metrics=missing,
            stale_metrics=stale,
            estimated_metrics=estimated,
            category_scores=categories,
            strengths=[m.label for m in sorted(drivers, key=lambda m: m.contribution or 0, reverse=True)[:5]],
            weaknesses=[m.label for m in sorted(drivers, key=lambda m: m.metric_score or 100)[:5]],
            peer_group=peer_group,
            warnings=[],
        )

    def _categories(self, run_id: int) -> list[CategoryScore]:
        rows = self.conn.execute(
            """
            SELECT category_code, raw_score, adjusted_score, category_weight, confidence_score, completeness_score, explanation
            FROM business_strength_category_score
            WHERE analysis_run_id = ?
            ORDER BY category_weight DESC, category_code
            """,
            [run_id],
        ).fetchall()
        return [
            CategoryScore(
                category_code=row[0],
                label=CATEGORY_LABELS.get(row[0], row[0].replace("_", " ").title()),
                raw_score=row[1],
                adjusted_score=row[2],
                category_weight=row[3],
                confidence_score=row[4],
                completeness_score=row[5],
                explanation=row[6],
                metrics=self._metrics(run_id, row[0]),
            )
            for row in rows
        ]

    def _metrics(self, run_id: int, category_code: str) -> list[MetricScore]:
        rows = self.conn.execute(
            """
            SELECT
                metric_code, raw_value, normalized_value, metric_score, metric_weight, contribution,
                unit, direction, value_status, source, source_timestamp, peer_percentile,
                historical_percentile, confidence, explanation
            FROM business_strength_metric_result
            WHERE analysis_run_id = ? AND category_code = ?
            ORDER BY metric_weight DESC, metric_code
            """,
            [run_id, category_code],
        ).fetchall()
        definitions = {}
        for candidate in self.registry.all():
            for metric in candidate.metrics:
                definitions[metric.code] = metric.label
        return [
            MetricScore(
                category_code=category_code,
                metric_code=row[0],
                label=definitions.get(row[0], row[0].replace("_", " ").title()),
                raw_value=row[1],
                normalized_value=row[2],
                metric_score=row[3],
                metric_weight=row[4],
                contribution=row[5],
                unit=row[6],
                direction=row[7],
                value_status=row[8],
                source=row[9],
                source_timestamp=row[10],
                peer_percentile=row[11],
                historical_percentile=row[12],
                confidence=row[13],
                explanation=row[14],
            )
            for row in rows
        ]

    def _peer_group(self, template_code: str, asset_id: str) -> list[str]:
        row = self.conn.execute("SELECT sector, industry FROM asset WHERE asset_id = ?", [asset_id]).fetchone()
        if row is None:
            return [asset_id]
        rows = self.conn.execute(
            """
            SELECT asset_id FROM asset
            WHERE (? IS NOT NULL AND industry = ?)
               OR (? IS NOT NULL AND sector = ?)
            ORDER BY asset_id
            LIMIT 20
            """,
            [row[1], row[1], row[0], row[0]],
        ).fetchall()
        return [item[0] for item in rows] or [asset_id]

    def _classification(self, score: float | None) -> str:
        if score is None:
            return "Insufficient Data"
        if score >= 90:
            return "Exceptional"
        if score >= 80:
            return "Very Strong"
        if score >= 70:
            return "Strong"
        if score >= 60:
            return "Above Average"
        if score >= 50:
            return "Average"
        if score >= 40:
            return "Below Average"
        if score >= 30:
            return "Weak"
        return "Very Weak"
