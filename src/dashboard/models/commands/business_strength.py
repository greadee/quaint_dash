"""CLI helpers for deterministic Business Strength scorecards."""

from __future__ import annotations

class BusinessStrengthCommands:
    def business_strength_run(self, target: str, *, force: bool = False, max_assets: int | None = None):
        from dashboard.services.business_strength import BusinessStrengthAnalyzer

        analyzer = BusinessStrengthAnalyzer(self.conn)
        if target.lower() == "all":
            rows = self.conn.execute(
                """
                SELECT asset_id FROM asset
                WHERE COALESCE(asset_type, 'stock') IN ('stock', 'equity')
                  AND track = TRUE
                ORDER BY asset_id
                LIMIT ?
                """,
                [max_assets or 1000],
            ).fetchall()
            return [analyzer.run(row[0]) if force else analyzer.latest_or_run(row[0]) for row in rows]
        return [analyzer.run(target) if force else analyzer.latest_or_run(target)]

    def business_strength_show(self, target: str) -> str:
        from dashboard.services.business_strength import BusinessStrengthAnalyzer

        scorecard = BusinessStrengthAnalyzer(self.conn).latest_or_run(target)
        score = "insufficient" if scorecard.overall_score is None else f"{scorecard.overall_score:.0f}"
        easy = "insufficient" if scorecard.easy_hold_score is None else f"{scorecard.easy_hold_score:.0f}"
        return (
            f"{scorecard.symbol}: Business Strength {score} ({scorecard.classification}), "
            f"Easy-Hold {easy}, confidence {scorecard.confidence_score:.0f}%, "
            f"template {scorecard.template_code}."
        )

    def business_strength_validate(self, target: str, *, max_assets: int | None = None) -> list[str]:
        scorecards = self.business_strength_run(target, max_assets=max_assets)
        messages = []
        for item in scorecards:
            total_weight = round(sum(category.category_weight for category in item.category_scores), 6)
            if total_weight != 1:
                messages.append(f"{item.symbol}: invalid category weight sum {total_weight}")
            if item.overall_score is not None:
                recomputed = sum((category.adjusted_score or 0) * category.category_weight for category in item.category_scores if category.adjusted_score is not None)
                if abs(recomputed - item.overall_score) > 0.05:
                    messages.append(f"{item.symbol}: overall score does not reconcile")
            if not item.category_scores:
                messages.append(f"{item.symbol}: no categories")
        return messages or ["Business Strength validation passed."]

    def business_strength_template_list(self) -> list[str]:
        from dashboard.services.business_strength import BusinessStrengthTemplateRegistry

        return [f"{template.template_code}: {template.name} v{template.version}" for template in BusinessStrengthTemplateRegistry().all()]

    def business_strength_template_show(self, template_code: str) -> str:
        from dashboard.services.business_strength import BusinessStrengthTemplateRegistry

        template = BusinessStrengthTemplateRegistry().get(template_code)
        metrics = ", ".join(metric.code for metric in template.metrics)
        return f"{template.template_code}: {template.name}; categories={template.category_weights}; metrics={metrics}"
