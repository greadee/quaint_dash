"""Deterministic inference of observed investor-profile characteristics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any, Iterable

from dashboard.rules_and_data.models import (
    INVESTOR_PROFILE_METHODOLOGY_VERSION,
    INVESTOR_PROFILE_SCHEMA_VERSION,
    AllocationMix,
    EvidenceRef,
    ExposureTilt,
    InvestorProfile,
    InvestorProfileInput,
    ProfileDimension,
    ProfileHolding,
)


_FACTOR_NAMES = ("growth", "value", "quality", "income", "speculative")
_QUANTUM = Decimal("0.00000001")


class InvestorProfileEngine:
    """Infer a reproducible profile from observed holdings and stored metrics."""

    def infer(self, profile_input: InvestorProfileInput) -> InvestorProfile:
        canonical_input = _canonical_json(profile_input)
        snapshot_hash = hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()
        profile_id = f"profile:{snapshot_hash}"
        holdings = tuple(sorted(profile_input.holdings, key=lambda item: item.asset_id))
        factor_scores = tuple(
            self._factor_dimension(name, holdings) for name in _FACTOR_NAMES
        )
        factor_scores = self._apply_watchlist_behavior(factor_scores, profile_input)
        factor_by_name = {item.code: item for item in factor_scores}
        concentration = self._concentration_dimension(holdings)
        risk = self._risk_dimension(profile_input, holdings, factor_by_name, concentration)
        geography = self._geography_dimension(profile_input.domestic_country, holdings)
        sector_tilts = self._sector_tilts(holdings)
        theme_tilts = self._theme_tilts(holdings)
        allocation_mix = self._allocation_mix(holdings)
        data_gaps = self._profile_data_gaps(
            profile_input,
            holdings,
            factor_scores,
            risk,
            concentration,
            geography,
            allocation_mix,
        )
        confidence = self._overall_confidence(
            factor_scores,
            risk,
            concentration,
            geography,
            allocation_mix,
        )
        archetypes = self._archetypes(
            factor_by_name,
            risk,
            concentration,
            allocation_mix,
            confidence,
        )
        evidence_ids = _evidence_ids(
            [
                *profile_input.evidence_refs,
                *(ref for holding in holdings for ref in holding.evidence_refs),
                *(
                    profile_input.watchlist_behavior.evidence_refs
                    if profile_input.watchlist_behavior
                    else ()
                ),
                *(
                    profile_input.stated_preferences.evidence_refs
                    if profile_input.stated_preferences
                    else ()
                ),
            ]
        )
        suitability_status = (
            "stated_inputs_present_not_assessed"
            if profile_input.stated_preferences is not None
            else "not_assessed_missing_stated_inputs"
        )
        return InvestorProfile(
            profile_id=profile_id,
            portfolio_id=profile_input.portfolio_id,
            as_of=profile_input.as_of.astimezone(timezone.utc),
            schema_version=INVESTOR_PROFILE_SCHEMA_VERSION,
            methodology_version=INVESTOR_PROFILE_METHODOLOGY_VERSION,
            input_snapshot_hash=snapshot_hash,
            inference_scope="observed_portfolio_behavior",
            suitability_status=suitability_status,
            archetype_labels=archetypes,
            factor_scores=factor_scores,
            observed_risk_posture=risk,
            concentration_profile=concentration,
            geography_tilt=geography,
            sector_tilts=sector_tilts,
            theme_tilts=theme_tilts,
            allocation_mix=allocation_mix,
            confidence=confidence,
            evidence_refs=evidence_ids,
            data_gaps=data_gaps,
        )

    def _factor_dimension(
        self,
        factor: str,
        holdings: tuple[ProfileHolding, ...],
    ) -> ProfileDimension:
        values: list[tuple[float, float, tuple[EvidenceRef, ...]]] = []
        for holding in holdings:
            score = self._holding_factor_score(factor, holding)
            if score is not None and holding.weight > 0:
                values.append((score, holding.weight, holding.evidence_refs))
        total_weight = sum(holding.weight for holding in holdings)
        score = _weighted_average((value, weight) for value, weight, _refs in values)
        evidence_adjusted_weight = sum(
            weight * _evidence_quality(refs) for _score, weight, refs in values
        )
        confidence = _coverage(evidence_adjusted_weight, total_weight)
        gaps = () if confidence >= 0.75 else (f"missing.factor.{factor}",)
        label = _factor_label(score)
        return ProfileDimension(
            code=factor,
            score=_round_score(score),
            label=label,
            confidence=confidence,
            evidence_refs=_evidence_ids(ref for _value, _weight, refs in values for ref in refs),
            data_gaps=gaps,
        )

    @staticmethod
    def _apply_watchlist_behavior(
        factors: tuple[ProfileDimension, ...],
        profile_input: InvestorProfileInput,
    ) -> tuple[ProfileDimension, ...]:
        behavior = profile_input.watchlist_behavior
        if behavior is None or behavior.speculative_ratio is None:
            return factors
        adjusted = []
        for factor in factors:
            if factor.code != "speculative":
                adjusted.append(factor)
                continue
            behavior_score = behavior.speculative_ratio * 100.0
            if factor.score is None:
                score = behavior_score
                confidence = round(0.15 * _evidence_quality(behavior.evidence_refs), 2)
            else:
                score = (factor.score * 0.85) + (behavior_score * 0.15)
                confidence = round(
                    min(
                        1.0,
                        (factor.confidence * 0.85)
                        + (0.15 * _evidence_quality(behavior.evidence_refs)),
                    ),
                    2,
                )
            adjusted.append(
                ProfileDimension(
                    code=factor.code,
                    score=_round_score(score),
                    label=_factor_label(score),
                    confidence=confidence,
                    evidence_refs=tuple(
                        sorted(
                            {
                                *factor.evidence_refs,
                                *(ref.evidence_id for ref in behavior.evidence_refs),
                            }
                        )
                    ),
                    data_gaps=(
                        () if confidence >= 0.75 else ("missing.factor.speculative",)
                    ),
                )
            )
        return tuple(adjusted)

    @staticmethod
    def _holding_factor_score(factor: str, holding: ProfileHolding) -> float | None:
        explicit = getattr(holding, f"{factor}_score")
        if explicit is not None:
            return explicit
        if factor == "income" and holding.dividend_yield is not None:
            return min(100.0, holding.dividend_yield / 0.05 * 100.0)
        if factor == "speculative":
            cap_score = {
                "micro": 95.0,
                "small": 75.0,
                "mid": 45.0,
                "large": 20.0,
                "mega": 10.0,
            }.get((holding.market_cap_band or "").strip().lower())
            volatility_score = (
                _risk_score_from_volatility(holding.annualized_volatility)
                if holding.annualized_volatility is not None
                else None
            )
            return _mean_optional(cap_score, volatility_score)
        return None

    def _risk_dimension(
        self,
        profile_input: InvestorProfileInput,
        holdings: tuple[ProfileHolding, ...],
        factors: dict[str, ProfileDimension],
        concentration: ProfileDimension,
    ) -> ProfileDimension:
        volatility = profile_input.portfolio_volatility
        if volatility is None:
            volatility = _weighted_average(
                (holding.annualized_volatility, holding.weight)
                for holding in holdings
                if holding.annualized_volatility is not None
            )
        components = [
            (_risk_score_from_volatility(volatility), 0.40, "missing.risk.volatility"),
            (factors["speculative"].score, 0.30, "missing.risk.speculative"),
            (concentration.score, 0.20, "missing.risk.concentration"),
            (_risk_score_from_turnover(profile_input.turnover_rate), 0.10, "missing.risk.turnover"),
        ]
        available = [(value, weight) for value, weight, _gap in components if value is not None]
        score = _weighted_average(available)
        evidence_quality = _evidence_quality(
            [
                *profile_input.evidence_refs,
                *(ref for holding in holdings for ref in holding.evidence_refs),
            ]
        )
        confidence = round(sum(weight for _value, weight in available) * evidence_quality, 2)
        gaps = tuple(gap for value, _weight, gap in components if value is None)
        if score is None or confidence < 0.50:
            label = "unknown"
        elif score <= 35:
            label = "conservative"
        elif score <= 65:
            label = "moderate"
        else:
            label = "aggressive"
        refs = [
            *profile_input.evidence_refs,
            *(ref for holding in holdings for ref in holding.evidence_refs),
        ]
        return ProfileDimension(
            code="observed_risk_posture",
            score=_round_score(score),
            label=label,
            confidence=confidence,
            evidence_refs=_evidence_ids(refs) if score is not None else (),
            data_gaps=gaps,
        )

    def _concentration_dimension(
        self,
        holdings: tuple[ProfileHolding, ...],
    ) -> ProfileDimension:
        weighted = [holding for holding in holdings if holding.weight > 0]
        if not weighted:
            return ProfileDimension(
                code="concentration_profile",
                score=None,
                label="unknown",
                confidence=0.0,
                data_gaps=("missing.concentration.holdings",),
            )
        effective_exposures = []
        for holding in weighted:
            divisor = 1
            if holding.is_etf and holding.look_through_holding_count:
                divisor = min(100, holding.look_through_holding_count)
            effective_exposures.append(holding.weight / divisor)
        hhi = sum(
            holding.weight**2
            / (
                min(100, holding.look_through_holding_count)
                if holding.is_etf and holding.look_through_holding_count
                else 1
            )
            for holding in weighted
        )
        largest = max(effective_exposures)
        score = min(100.0, max(largest * 200.0, hhi * 200.0))
        if largest <= 0.15 and hhi <= 0.10:
            label = "diversified"
        elif largest <= 0.30 and hhi <= 0.25:
            label = "moderate"
        else:
            label = "concentrated"
        total_weight = sum(holding.weight for holding in weighted)
        confidence = _coverage(
            sum(holding.weight * _evidence_quality(holding.evidence_refs) for holding in weighted),
            total_weight,
        )
        return ProfileDimension(
            code="concentration_profile",
            score=_round_score(score),
            label=label,
            confidence=confidence,
            evidence_refs=_evidence_ids(
                ref for holding in weighted for ref in holding.evidence_refs
            ),
            data_gaps=() if total_weight >= 0.95 else ("missing.allocation.coverage",),
        )

    def _geography_dimension(
        self,
        domestic_country: str,
        holdings: tuple[ProfileHolding, ...],
    ) -> ProfileDimension:
        total_weight = sum(holding.weight for holding in holdings)
        exposures: dict[str, float] = {}
        classified: list[ProfileHolding] = []
        for holding in holdings:
            if holding.weight <= 0:
                continue
            holding_exposure = holding.geography_exposure
            if not holding_exposure and holding.geography:
                holding_exposure = {holding.geography: 1.0}
            if not holding_exposure:
                continue
            classified.append(holding)
            for geography, exposure_weight in holding_exposure.items():
                exposures[geography] = (
                    exposures.get(geography, 0.0) + holding.weight * exposure_weight
                )
        classified_weight = sum(exposures.values())
        if classified_weight == 0:
            return ProfileDimension(
                code="domestic_international_tilt",
                score=None,
                label="unknown",
                confidence=0.0,
                data_gaps=("missing.geography.classification",),
            )
        domestic = sum(
            weight
            for geography, weight in exposures.items()
            if geography.upper() == domestic_country.upper()
        )
        domestic_ratio = domestic / classified_weight
        international_ratio = 1.0 - domestic_ratio
        if domestic_ratio >= 0.70:
            label = "domestic"
        elif international_ratio >= 0.70:
            label = "international"
        elif domestic_ratio >= 0.30 and international_ratio >= 0.30:
            label = "balanced"
        else:
            label = "mixed"
        confidence = _coverage(
            sum(
                holding.weight * _evidence_quality(holding.evidence_refs)
                for holding in classified
            ),
            total_weight,
        )
        return ProfileDimension(
            code="domestic_international_tilt",
            score=_round_score(domestic_ratio * 100.0),
            label=label,
            confidence=confidence,
            evidence_refs=_evidence_ids(ref for holding in classified for ref in holding.evidence_refs),
            data_gaps=(
                ()
                if confidence >= 0.75
                else ("missing.geography.classification",)
            ),
        )

    def _sector_tilts(
        self,
        holdings: tuple[ProfileHolding, ...],
    ) -> tuple[ExposureTilt, ...]:
        totals: dict[str, float] = {}
        refs: dict[str, list[EvidenceRef]] = {}
        total_weight = sum(holding.weight for holding in holdings)
        covered_holdings: list[ProfileHolding] = []
        for holding in holdings:
            if holding.weight <= 0:
                continue
            holding_exposure = holding.sector_exposure
            if not holding_exposure and holding.sector:
                holding_exposure = {holding.sector: 1.0}
            if not holding_exposure:
                continue
            covered_holdings.append(holding)
            for sector, exposure_weight in holding_exposure.items():
                totals[sector] = totals.get(sector, 0.0) + holding.weight * exposure_weight
                refs.setdefault(sector, []).extend(holding.evidence_refs)
        confidence = _coverage(
            sum(
                holding.weight * _evidence_quality(holding.evidence_refs)
                for holding in covered_holdings
            ),
            total_weight,
        )
        return tuple(
            ExposureTilt(
                dimension="sector",
                key=name,
                weight=round(weight, 4),
                label="sector_tilt",
                confidence=confidence,
                evidence_refs=_evidence_ids(refs[name]),
            )
            for name, weight in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
            if weight > 0.30
            and name.strip().lower() not in {"other", "unknown", "broad market"}
        )

    def _theme_tilts(
        self,
        holdings: tuple[ProfileHolding, ...],
    ) -> tuple[ExposureTilt, ...]:
        totals: dict[str, float] = {}
        refs: dict[str, list[EvidenceRef]] = {}
        total_weight = sum(holding.weight for holding in holdings)
        for holding in holdings:
            if not holding.themes or holding.weight <= 0:
                continue
            split_weight = holding.weight / len(holding.themes)
            for theme in sorted(set(holding.themes)):
                totals[theme] = totals.get(theme, 0.0) + split_weight
                refs.setdefault(theme, []).extend(holding.evidence_refs)
        confidence = _coverage(
            sum(
                holding.weight * _evidence_quality(holding.evidence_refs)
                for holding in holdings
                if holding.themes and holding.weight > 0
            ),
            total_weight,
        )
        return tuple(
            ExposureTilt(
                dimension="theme",
                key=name,
                weight=round(weight, 4),
                label="theme_tilt",
                confidence=confidence,
                evidence_refs=_evidence_ids(refs[name]),
            )
            for name, weight in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
            if weight > 0.15
        )

    def _allocation_mix(self, holdings: tuple[ProfileHolding, ...]) -> AllocationMix:
        classified = [holding for holding in holdings if holding.asset_class]
        classified_weight = sum(holding.weight for holding in classified)
        if classified_weight == 0:
            return AllocationMix(
                etf_weight=None,
                passive_weight=None,
                direct_stock_weight=None,
                classified_weight=0.0,
                label="unknown",
                confidence=0.0,
            )
        etf_weight = sum(holding.weight for holding in classified if holding.is_etf)
        passive_weight = sum(holding.weight for holding in classified if holding.is_passive)
        stock_weight = sum(
            holding.weight
            for holding in classified
            if holding.asset_class.lower() in {"stock", "equity"} and not holding.is_etf
        )
        if passive_weight >= 0.70:
            label = "passive_allocator"
        elif stock_weight >= 0.70:
            label = "stock_picker"
        elif etf_weight + stock_weight >= 0.60:
            label = "mixed_active_passive"
        else:
            label = "multi_asset"
        return AllocationMix(
            etf_weight=round(etf_weight, 4),
            passive_weight=round(passive_weight, 4),
            direct_stock_weight=round(stock_weight, 4),
            classified_weight=round(classified_weight, 4),
            label=label,
            confidence=_coverage(
                sum(
                    holding.weight * _evidence_quality(holding.evidence_refs)
                    for holding in classified
                ),
                sum(holding.weight for holding in holdings),
            ),
            evidence_refs=_evidence_ids(ref for holding in classified for ref in holding.evidence_refs),
        )

    @staticmethod
    def _profile_data_gaps(
        profile_input: InvestorProfileInput,
        holdings: tuple[ProfileHolding, ...],
        factors: tuple[ProfileDimension, ...],
        risk: ProfileDimension,
        concentration: ProfileDimension,
        geography: ProfileDimension,
        allocation_mix: AllocationMix,
    ) -> tuple[str, ...]:
        gaps: set[str] = set()
        if not holdings:
            gaps.add("missing.portfolio.holdings")
        if sum(holding.weight for holding in holdings) < 0.95:
            gaps.add("missing.allocation.coverage")
        gaps.update(gap for item in factors for gap in item.data_gaps)
        gaps.update(risk.data_gaps)
        gaps.update(concentration.data_gaps)
        gaps.update(geography.data_gaps)
        if allocation_mix.classified_weight < 0.75:
            gaps.add("missing.asset_class.classification")
        if sum(
            holding.weight
            for holding in holdings
            if holding.sector or holding.sector_exposure
        ) < 0.75:
            gaps.add("missing.sector.classification")
        if profile_input.watchlist_behavior is None:
            gaps.add("optional.watchlist.behavior")
        if profile_input.stated_preferences is None:
            gaps.add("suitability.stated_inputs_missing")
        if any(ref.status == "stale" for ref in _all_evidence_refs(profile_input)):
            gaps.add("evidence.stale")
        return tuple(sorted(gaps))

    @staticmethod
    def _overall_confidence(
        factors: tuple[ProfileDimension, ...],
        risk: ProfileDimension,
        concentration: ProfileDimension,
        geography: ProfileDimension,
        allocation_mix: AllocationMix,
    ) -> float:
        factor_confidence = sum(item.confidence for item in factors) / len(factors)
        allocation_confidence = allocation_mix.confidence
        return round(
            (factor_confidence * 0.40)
            + (risk.confidence * 0.20)
            + (concentration.confidence * 0.15)
            + (geography.confidence * 0.10)
            + (allocation_confidence * 0.15),
            2,
        )

    @staticmethod
    def _archetypes(
        factors: dict[str, ProfileDimension],
        risk: ProfileDimension,
        concentration: ProfileDimension,
        allocation_mix: AllocationMix,
        confidence: float,
    ) -> tuple[str, ...]:
        if confidence < 0.35:
            return ("insufficient_data",)
        labels: set[str] = set()
        growth = factors["growth"].score
        value = factors["value"].score
        quality = factors["quality"].score
        income = factors["income"].score
        speculative = factors["speculative"].score
        if growth is not None and growth >= 65 and (value is None or growth - value >= 10):
            labels.add("growth_oriented")
        if value is not None and value >= 65 and (growth is None or value - growth >= 10):
            labels.add("value_oriented")
        if quality is not None and quality >= 70:
            labels.add("quality_focused")
        if income is not None and income >= 65:
            labels.add("income_focused")
        if speculative is not None and speculative >= 65:
            labels.add("speculative")
        if allocation_mix.label in {"passive_allocator", "stock_picker", "multi_asset"}:
            labels.add(allocation_mix.label)
        if concentration.label == "concentrated":
            labels.add("concentrated")
        available_core = [
            score
            for score in (growth, value, quality, income)
            if score is not None
        ]
        if (
            len(available_core) == 4
            and max(available_core) - min(available_core) <= 20
            and (speculative is None or speculative < 55)
            and concentration.label != "concentrated"
            and risk.label != "aggressive"
        ):
            labels.add("balanced")
        if not labels:
            labels.add("mixed_style")
        return tuple(sorted(labels))


def _factor_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 35:
        return "low"
    if score < 65:
        return "moderate"
    return "high"


def _risk_score_from_volatility(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0.10:
        return 20.0
    if value <= 0.20:
        return 45.0
    if value <= 0.30:
        return 70.0
    return 90.0


def _risk_score_from_turnover(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0.25:
        return 20.0
    if value <= 0.75:
        return 45.0
    if value <= 1.50:
        return 70.0
    return 90.0


def _mean_optional(*values: float | None) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _weighted_average(values: Iterable[tuple[float, float]]) -> float | None:
    available = list(values)
    total_weight = sum(weight for _value, weight in available)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in available) / total_weight


def _coverage(covered_weight: float, total_weight: float) -> float:
    if total_weight <= 0:
        return 0.0
    return round(min(1.0, covered_weight / total_weight), 2)


def _round_score(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _evidence_ids(refs: Iterable[EvidenceRef]) -> tuple[str, ...]:
    return tuple(sorted({ref.evidence_id for ref in refs}))


def _evidence_quality(refs: Iterable[EvidenceRef]) -> float:
    items = list(refs)
    if not items:
        return 0.0
    quality = {
        "reported": 1.0,
        "derived": 1.0,
        "estimated": 0.75,
        "proxied": 0.75,
        "stale": 0.50,
        "unsupported": 0.0,
    }
    return sum(quality[item.status] for item in items) / len(items)


def _all_evidence_refs(profile_input: InvestorProfileInput) -> tuple[EvidenceRef, ...]:
    return tuple(
        [
            *profile_input.evidence_refs,
            *(ref for holding in profile_input.holdings for ref in holding.evidence_refs),
            *(
                profile_input.watchlist_behavior.evidence_refs
                if profile_input.watchlist_behavior
                else ()
            ),
            *(
                profile_input.stated_preferences.evidence_refs
                if profile_input.stated_preferences
                else ()
            ),
        ]
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"))


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        result = {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, InvestorProfileInput):
            result["holdings"] = sorted(result["holdings"], key=lambda item: item["asset_id"])
            result["evidence_refs"] = sorted(
                result["evidence_refs"], key=lambda item: item["evidence_id"]
            )
        elif isinstance(value, ProfileHolding):
            result["themes"] = sorted(result["themes"])
        for set_like_field in ("objectives", "constraints"):
            if set_like_field in result:
                result[set_like_field] = sorted(result[set_like_field])
        if "evidence_refs" in result:
            result["evidence_refs"] = sorted(
                result["evidence_refs"], key=lambda item: item["evidence_id"]
            )
        return result
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return format(Decimal(str(value)).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN), "f")
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value
