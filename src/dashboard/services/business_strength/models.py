"""Typed models for deterministic Business Strength analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


METHODOLOGY_VERSION = "business-strength.deterministic.v1"

CATEGORY_LABELS = {
    "competitive_strength": "Competitive Strength - Quantitative",
    "growth_quality": "Growth Quality",
    "profitability": "Profitability",
    "durability": "Earnings and Revenue Durability",
    "financial_strength": "Financial Strength",
    "capital_efficiency": "Capital Efficiency",
    "capital_allocation": "Capital Allocation",
    "cyclicality_resilience": "Cyclicality and Resilience",
    "concentration_risk": "Concentration and Dependency Risk",
}

DEFAULT_CATEGORY_WEIGHTS = {
    "competitive_strength": 0.15,
    "growth_quality": 0.12,
    "profitability": 0.13,
    "durability": 0.13,
    "financial_strength": 0.12,
    "capital_efficiency": 0.12,
    "capital_allocation": 0.08,
    "cyclicality_resilience": 0.08,
    "concentration_risk": 0.07,
}

VALID_STATUSES = {
    "reported",
    "derived",
    "normalized",
    "estimated",
    "unknown",
    "not_applicable",
    "stale",
    "conflicting",
}


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    label: str
    category: str
    weight: float
    direction: str
    unit: str
    normalization: str
    absolute_min: float | None = None
    absolute_max: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    required: bool = True
    source: str = "financial_statement"


@dataclass(frozen=True)
class BusinessStrengthTemplate:
    template_code: str
    name: str
    sector: str
    industry: str
    version: int
    category_weights: dict[str, float]
    metrics: tuple[MetricDefinition, ...]
    parent_template_code: str = "base"
    notes: str = ""


@dataclass
class MetricInput:
    code: str
    value: float | None
    status: str
    source: str
    source_timestamp: datetime | None = None
    peer_values: list[float] = field(default_factory=list)
    historical_values: list[float] = field(default_factory=list)


@dataclass
class StandardizedBusinessStrengthInput:
    asset_id: str
    symbol: str
    name: str | None
    sector: str | None
    industry: str | None
    fundamental_asset_id: str
    analysis_date: date
    source_data_as_of: datetime | None
    metrics: dict[str, MetricInput]
    peer_group: list[str]
    missing_inputs: list[str] = field(default_factory=list)


@dataclass
class MetricScore:
    category_code: str
    metric_code: str
    label: str
    raw_value: float | None
    normalized_value: float | None
    metric_score: float | None
    metric_weight: float
    contribution: float | None
    unit: str
    direction: str
    value_status: str
    source: str
    source_timestamp: datetime | None
    peer_percentile: float | None
    historical_percentile: float | None
    confidence: float
    explanation: str


@dataclass
class CategoryScore:
    category_code: str
    label: str
    raw_score: float | None
    adjusted_score: float | None
    category_weight: float
    confidence_score: float
    completeness_score: float
    explanation: str
    metrics: list[MetricScore]


@dataclass
class BusinessStrengthScorecard:
    analysis_run_id: int | None
    asset_id: str
    symbol: str
    name: str | None
    sector: str | None
    industry: str | None
    template_code: str
    template_name: str
    template_version: int
    methodology_version: str
    analysis_date: date
    source_data_as_of: datetime | None
    overall_score: float | None
    score_10: float | None
    classification: str
    confidence_score: float
    completeness_score: float
    easy_hold_score: float | None
    easy_hold_label: str
    status: str
    missing_critical_metrics: list[str]
    stale_metrics: list[str]
    estimated_metrics: list[str]
    category_scores: list[CategoryScore]
    strengths: list[str]
    weaknesses: list[str]
    peer_group: list[str]
    warnings: list[str]
    future_research_enabled: bool = False


@dataclass(frozen=True)
class BusinessStrengthQualitativeInput:
    input_type: str
    structured_payload: dict
    source: str
    confidence: float
    review_status: str = "disabled"


@dataclass(frozen=True)
class BusinessStrengthEvidenceRecord:
    evidence_type: str
    source: str
    payload: dict
    confidence: float


@dataclass(frozen=True)
class BusinessStrengthOverrideProposal:
    target_code: str
    proposed_value: str
    reason: str
    source: str


class BusinessStrengthResearchProvider(Protocol):
    """Future qualitative research extension. Not used by deterministic scoring."""

    def load_inputs(self, asset_id: str) -> list[BusinessStrengthQualitativeInput]:
        ...
