"""Template-driven deterministic score explanations."""

from __future__ import annotations

from dashboard.services.business_strength.models import MetricScore


def metric_explanation(label: str, value: float | None, score: float | None, status: str) -> str:
    if status == "not_applicable":
        return f"{label} is not applicable for this template and does not affect the score."
    if value is None:
        return f"{label} is unavailable; confidence is reduced and the metric is excluded from score contribution."
    return f"{label} scored {score:.0f}/100 from reported or derived value {value:.4g}."


def category_explanation(label: str, metrics: list[MetricScore], score: float | None) -> str:
    present = [item for item in metrics if item.metric_score is not None]
    if not present:
        return f"{label} has insufficient usable inputs, so it is shown with low confidence."
    positives = sorted(present, key=lambda item: item.contribution or 0, reverse=True)[:2]
    drivers = ", ".join(item.label for item in positives)
    return f"{label} scored {score:.0f}/100 based on {drivers}." if score is not None else f"{label} has insufficient usable inputs."
