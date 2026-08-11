"""Provider-neutral contracts for deterministic investor-profile inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite


INVESTOR_PROFILE_SCHEMA_VERSION = "investor-profile.v1"
INVESTOR_PROFILE_METHODOLOGY_VERSION = "investor-profile.deterministic.v1"

EVIDENCE_STATUSES = {
    "reported",
    "derived",
    "estimated",
    "proxied",
    "stale",
    "unsupported",
}


def _validate_ratio(name: str, value: float | None) -> None:
    if value is None:
        return
    if not isfinite(value) or value < 0 or value > 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _validate_score(name: str, value: float | None) -> None:
    if value is None:
        return
    if not isfinite(value) or value < 0 or value > 100:
        raise ValueError(f"{name} must be between 0 and 100")


def _validate_nonnegative(name: str, value: float | None) -> None:
    if value is not None and (not isfinite(value) or value < 0):
        raise ValueError(f"{name} must be nonnegative")


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source: str
    source_schema_version: str
    as_of: datetime
    payload_hash: str
    status: str = "reported"

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.source or not self.source_schema_version:
            raise ValueError("evidence identity, source, and schema version are required")
        prefix, separator, digest = self.evidence_id.partition(":")
        if (
            prefix != "evidence"
            or separator != ":"
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("evidence_id must use evidence:<lowercase SHA-256>")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("evidence as_of must be timezone-aware")
        if len(self.payload_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.payload_hash
        ):
            raise ValueError("payload_hash must be a lowercase SHA-256 hex digest")
        if self.status not in EVIDENCE_STATUSES:
            raise ValueError(f"unsupported evidence status: {self.status}")


@dataclass(frozen=True)
class ProfileHolding:
    asset_id: str
    weight: float
    asset_class: str | None = None
    sector: str | None = None
    geography: str | None = None
    sector_exposure: dict[str, float] = field(default_factory=dict)
    geography_exposure: dict[str, float] = field(default_factory=dict)
    themes: tuple[str, ...] = ()
    market_cap_band: str | None = None
    is_etf: bool | None = None
    is_passive: bool | None = None
    look_through_holding_count: int | None = None
    annualized_volatility: float | None = None
    dividend_yield: float | None = None
    growth_score: float | None = None
    value_score: float | None = None
    quality_score: float | None = None
    income_score: float | None = None
    speculative_score: float | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id is required")
        _validate_ratio("weight", self.weight)
        _validate_nonnegative("annualized_volatility", self.annualized_volatility)
        _validate_nonnegative("dividend_yield", self.dividend_yield)
        for name in (
            "growth_score",
            "value_score",
            "quality_score",
            "income_score",
            "speculative_score",
        ):
            _validate_score(name, getattr(self, name))
        if self.look_through_holding_count is not None and self.look_through_holding_count < 1:
            raise ValueError("look_through_holding_count must be positive")
        for exposure_name, exposure in (
            ("sector_exposure", self.sector_exposure),
            ("geography_exposure", self.geography_exposure),
        ):
            for key, value in exposure.items():
                if not key:
                    raise ValueError(f"{exposure_name} keys cannot be empty")
                _validate_ratio(f"{exposure_name} {key}", value)
            if sum(exposure.values()) > 1.00000001:
                raise ValueError(f"{exposure_name} cannot exceed 100%")
        if self.weight > 0 and not self.evidence_refs:
            raise ValueError("positive-weight holdings require evidence")
        if len({item.evidence_id for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("holding evidence IDs must be unique")


@dataclass(frozen=True)
class WatchlistBehavior:
    direct_stock_ratio: float | None = None
    speculative_ratio: float | None = None
    theme_weights: dict[str, float] = field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        _validate_ratio("direct_stock_ratio", self.direct_stock_ratio)
        _validate_ratio("speculative_ratio", self.speculative_ratio)
        for theme, weight in self.theme_weights.items():
            if not theme:
                raise ValueError("watchlist theme names cannot be empty")
            _validate_ratio(f"theme weight {theme}", weight)
        if (
            self.direct_stock_ratio is not None
            or self.speculative_ratio is not None
            or self.theme_weights
        ) and not self.evidence_refs:
            raise ValueError("watchlist behavior requires evidence")


@dataclass(frozen=True)
class StatedPreferences:
    risk_tolerance: str | None = None
    time_horizon_years: int | None = None
    liquidity_need: str | None = None
    objectives: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if self.time_horizon_years is not None and self.time_horizon_years < 0:
            raise ValueError("time_horizon_years must be nonnegative")
        if (
            self.risk_tolerance is not None
            or self.time_horizon_years is not None
            or self.liquidity_need is not None
            or self.objectives
            or self.constraints
        ) and not self.evidence_refs:
            raise ValueError("stated preferences require evidence")


@dataclass(frozen=True)
class InvestorProfileInput:
    portfolio_id: str
    as_of: datetime
    domestic_country: str
    holdings: tuple[ProfileHolding, ...]
    portfolio_volatility: float | None = None
    turnover_rate: float | None = None
    watchlist_behavior: WatchlistBehavior | None = None
    stated_preferences: StatedPreferences | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    source_schema_version: str = "portfolio-profile-input.v1"

    def __post_init__(self) -> None:
        if not self.portfolio_id or not self.domestic_country or not self.source_schema_version:
            raise ValueError("portfolio, domestic country, and source schema are required")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("profile as_of must be timezone-aware")
        _validate_nonnegative("portfolio_volatility", self.portfolio_volatility)
        _validate_nonnegative("turnover_rate", self.turnover_rate)
        if len({holding.asset_id for holding in self.holdings}) != len(self.holdings):
            raise ValueError("profile holdings must have unique asset IDs")
        if sum(holding.weight for holding in self.holdings) > 1.00000001:
            raise ValueError("holding weights cannot exceed 100%")
        if (
            self.portfolio_volatility is not None or self.turnover_rate is not None
        ) and not self.evidence_refs:
            raise ValueError("portfolio risk and turnover metrics require evidence")
        all_refs = [
            *self.evidence_refs,
            *(ref for holding in self.holdings for ref in holding.evidence_refs),
            *(self.watchlist_behavior.evidence_refs if self.watchlist_behavior else ()),
            *(self.stated_preferences.evidence_refs if self.stated_preferences else ()),
        ]
        canonical_refs: dict[str, EvidenceRef] = {}
        for ref in all_refs:
            if ref.as_of > self.as_of:
                raise ValueError("evidence cannot be newer than profile as_of")
            existing = canonical_refs.get(ref.evidence_id)
            if existing is not None and existing != ref:
                raise ValueError("duplicate evidence IDs must identify the same evidence")
            canonical_refs[ref.evidence_id] = ref


@dataclass(frozen=True)
class ProfileDimension:
    code: str
    score: float | None
    label: str
    confidence: float
    evidence_refs: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExposureTilt:
    dimension: str
    key: str
    weight: float
    label: str
    confidence: float
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AllocationMix:
    etf_weight: float | None
    passive_weight: float | None
    direct_stock_weight: float | None
    classified_weight: float
    label: str
    confidence: float
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class InvestorProfile:
    profile_id: str
    portfolio_id: str
    as_of: datetime
    schema_version: str
    methodology_version: str
    input_snapshot_hash: str
    inference_scope: str
    suitability_status: str
    archetype_labels: tuple[str, ...]
    factor_scores: tuple[ProfileDimension, ...]
    observed_risk_posture: ProfileDimension
    concentration_profile: ProfileDimension
    geography_tilt: ProfileDimension
    sector_tilts: tuple[ExposureTilt, ...]
    theme_tilts: tuple[ExposureTilt, ...]
    allocation_mix: AllocationMix
    confidence: float
    evidence_refs: tuple[str, ...]
    data_gaps: tuple[str, ...]
