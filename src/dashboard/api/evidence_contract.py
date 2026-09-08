"""Read-only policy for presenting evidence quality in API responses.

The evaluator derives display metadata from existing source facts. It never recalculates a
financial value, changes an ingestion decision, or persists a result.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from types import MappingProxyType
from typing import Any


EVIDENCE_DISPLAY_SCHEMA_VERSION = "evidence-display.v1"

SOURCE_KINDS = frozenset({"real", "proxy", "fixture", "inferred", "unknown"})
SOURCE_HEALTH_STATES = frozenset({"healthy", "degraded", "blocked", "unknown"})
FRESHNESS_STATES = frozenset({"current", "warning", "stale", "blocked", "unknown"})
COVERAGE_STATES = frozenset({"complete", "partial", "missing", "unsupported", "unknown"})
ACTION_ELIGIBILITY_STATES = frozenset({"eligible", "caution", "blocked"})
EVIDENCE_TYPES = frozenset(
    {"price", "news", "financial_statement", "benchmark", "monthly_signal"}
)


@dataclass(frozen=True)
class FreshnessWindow:
    """Elapsed-time thresholds used only for display state."""

    current_for: timedelta
    warning_for: timedelta

    def __post_init__(self) -> None:
        if self.current_for <= timedelta(0):
            raise ValueError("current_for must be positive")
        if self.warning_for <= self.current_for:
            raise ValueError("warning_for must be greater than current_for")


EVIDENCE_FRESHNESS_POLICIES: Mapping[str, FreshnessWindow] = MappingProxyType({
    "price": FreshnessWindow(timedelta(hours=36), timedelta(hours=96)),
    "news": FreshnessWindow(timedelta(hours=24), timedelta(hours=72)),
    "financial_statement": FreshnessWindow(timedelta(days=150), timedelta(days=240)),
    "benchmark": FreshnessWindow(timedelta(hours=36), timedelta(hours=96)),
    "monthly_signal": FreshnessWindow(timedelta(days=45), timedelta(days=75)),
})


@dataclass(frozen=True)
class EvidencePolicyInput:
    """Existing source metadata supplied to the display-only policy."""

    evidence_type: str
    source_kind: str
    source_name: str | None
    source_health: str
    observed_at: date | datetime | None
    retrieved_at: datetime | None = None
    missing_inputs: tuple[str, ...] = ()
    essential_missing_inputs: tuple[str, ...] = ()
    coverage_supported: bool = True
    confidence: float | None = None
    effectiveness_sample_size: int | None = None

    def __post_init__(self) -> None:
        _require_member("evidence_type", self.evidence_type, EVIDENCE_TYPES)
        _require_member("source_kind", self.source_kind, SOURCE_KINDS)
        _require_member("source_health", self.source_health, SOURCE_HEALTH_STATES)
        _validate_public_label("source_name", self.source_name)
        _validate_labels("missing_inputs", self.missing_inputs)
        _validate_labels("essential_missing_inputs", self.essential_missing_inputs)
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        if self.effectiveness_sample_size is not None and (
            isinstance(self.effectiveness_sample_size, bool)
            or self.effectiveness_sample_size < 0
        ):
            raise ValueError("effectiveness_sample_size must be non-negative")


@dataclass(frozen=True)
class EvidenceDisplayState:
    """Display-only quality state attached to an existing API result.

    `reason_codes` are machine-stable, lowercase dotted codes. Human-readable copy belongs to
    the route/UI layer so it can be tailored without changing the evidence state.
    """

    source_kind: str
    freshness_state: str
    coverage_state: str
    action_eligibility: str
    reason_codes: tuple[str, ...] = ()
    schema_version: str = EVIDENCE_DISPLAY_SCHEMA_VERSION
    evidence_type: str | None = None
    source_name: str | None = None
    source_health: str = "healthy"
    observed_at: datetime | None = None
    retrieved_at: datetime | None = None
    missing_inputs: tuple[str, ...] = ()
    confidence: float | None = None
    effectiveness_sample_size: int | None = None

    def __post_init__(self) -> None:
        _require_member("source_kind", self.source_kind, SOURCE_KINDS)
        _require_member("source_health", self.source_health, SOURCE_HEALTH_STATES)
        _validate_public_label("source_name", self.source_name)
        _validate_labels("missing_inputs", self.missing_inputs)
        if self.evidence_type is not None:
            _require_member("evidence_type", self.evidence_type, EVIDENCE_TYPES)
        _require_member("freshness_state", self.freshness_state, FRESHNESS_STATES)
        _require_member("coverage_state", self.coverage_state, COVERAGE_STATES)
        _require_member(
            "action_eligibility",
            self.action_eligibility,
            ACTION_ELIGIBILITY_STATES,
        )
        if self.schema_version != EVIDENCE_DISPLAY_SCHEMA_VERSION:
            raise ValueError("unsupported evidence display schema version")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        if self.effectiveness_sample_size is not None and (
            isinstance(self.effectiveness_sample_size, bool)
            or self.effectiveness_sample_size < 0
        ):
            raise ValueError("effectiveness_sample_size must be non-negative")
        for timestamp in (self.observed_at, self.retrieved_at):
            if timestamp is not None and timestamp.utcoffset() != timedelta(0):
                raise ValueError("display timestamps must be UTC-aware")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must be unique")
        for code in self.reason_codes:
            _validate_reason_code(code)
        if _requires_reason(self) and not self.reason_codes:
            raise ValueError("non-current evidence display state requires a reason code")
        _validate_precedence(self)

    def to_public_dict(self) -> dict[str, Any]:
        """Return the compact API-safe representation used by compatibility adapters."""
        return {
            "schema_version": self.schema_version,
            "evidence_type": self.evidence_type,
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "source_health": self.source_health,
            "observed_at": self.observed_at,
            "retrieved_at": self.retrieved_at,
            "freshness_state": self.freshness_state,
            "coverage_state": self.coverage_state,
            "missing_inputs": list(self.missing_inputs),
            "confidence": self.confidence,
            "effectiveness_sample_size": self.effectiveness_sample_size,
            "action_eligibility": self.action_eligibility,
            "reason_codes": list(self.reason_codes),
        }


def evaluate_evidence(
    item: EvidencePolicyInput,
    *,
    clock: Callable[[], datetime] | None = None,
    policies: Mapping[str, FreshnessWindow] = EVIDENCE_FRESHNESS_POLICIES,
) -> EvidenceDisplayState:
    """Derive a deterministic display state without changing the supplied result."""
    now = _utc_datetime((clock or (lambda: datetime.now(timezone.utc)))())
    observed_at = _utc_observation(item.observed_at)
    retrieved_at = _utc_datetime(item.retrieved_at) if item.retrieved_at else None
    reasons: list[str] = []

    if item.source_health != "healthy":
        reasons.append(f"evidence.source_health.{item.source_health}")
    if item.source_kind != "real":
        reasons.append(f"evidence.source_kind.{item.source_kind}")
    if item.source_name is None:
        reasons.append("evidence.source_name.missing")

    freshness_state = _freshness_state(
        item,
        now=now,
        observed_at=observed_at,
        policies=policies,
        reasons=reasons,
    )
    if retrieved_at is not None and retrieved_at > now:
        reasons.append("evidence.retrieved_at.future")

    all_missing = tuple(dict.fromkeys((*item.missing_inputs, *item.essential_missing_inputs)))
    if not item.coverage_supported:
        coverage_state = "unsupported"
        reasons.append("evidence.coverage.unsupported")
    elif item.essential_missing_inputs:
        coverage_state = "missing"
        reasons.append("evidence.coverage.essential_missing")
    elif all_missing:
        coverage_state = "partial"
        reasons.append("evidence.coverage.partial")
    else:
        coverage_state = "complete"

    blocked = any(
        (
            item.source_health == "blocked",
            item.source_kind in {"fixture", "proxy", "unknown"},
            item.source_name is None,
            freshness_state in {"stale", "blocked", "unknown"},
            coverage_state in {"missing", "unsupported", "unknown"},
            retrieved_at is not None and retrieved_at > now,
        )
    )
    caution = any(
        (
            item.source_health in {"degraded", "unknown"},
            item.source_kind == "inferred",
            freshness_state == "warning",
            coverage_state == "partial",
            item.effectiveness_sample_size == 0,
        )
    )
    if item.effectiveness_sample_size == 0:
        reasons.append("evidence.effectiveness.no_sample")
    action_eligibility = "blocked" if blocked else "caution" if caution else "eligible"

    return EvidenceDisplayState(
        evidence_type=item.evidence_type,
        source_kind=item.source_kind,
        source_name=item.source_name,
        source_health=item.source_health,
        observed_at=observed_at,
        retrieved_at=retrieved_at,
        freshness_state=freshness_state,
        coverage_state=coverage_state,
        missing_inputs=all_missing,
        confidence=item.confidence,
        effectiveness_sample_size=item.effectiveness_sample_size,
        action_eligibility=action_eligibility,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def attach_evidence_display(
    public_payload: Mapping[str, Any],
    evidence: EvidenceDisplayState,
) -> dict[str, Any]:
    """Add evidence to an already-public payload and reject known sensitive structures."""
    if "evidence" in public_payload:
        raise ValueError("public payload already contains an evidence field")
    _reject_sensitive_keys(public_payload)
    result = deepcopy(dict(public_payload))
    result["evidence"] = evidence.to_public_dict()
    return result


def select_public_fields_with_evidence(
    payload: Mapping[str, Any],
    public_fields: Iterable[str],
    evidence: EvidenceDisplayState,
) -> dict[str, Any]:
    """Allowlist legacy fields before attaching the shared evidence contract."""
    fields = tuple(dict.fromkeys(public_fields))
    missing = [field for field in fields if field not in payload]
    if missing:
        raise KeyError(f"public fields not present in payload: {', '.join(missing)}")
    return attach_evidence_display({field: payload[field] for field in fields}, evidence)


def _freshness_state(
    item: EvidencePolicyInput,
    *,
    now: datetime,
    observed_at: datetime | None,
    policies: Mapping[str, FreshnessWindow],
    reasons: list[str],
) -> str:
    if item.source_health == "blocked":
        return "blocked"
    if observed_at is None:
        reasons.append("evidence.observed_at.missing")
        return "unknown"
    if observed_at > now:
        reasons.append("evidence.observed_at.future")
        return "unknown"
    try:
        policy = policies[item.evidence_type]
    except KeyError as exc:
        raise ValueError(f"missing freshness policy for {item.evidence_type}") from exc
    age = now - observed_at
    if age <= policy.current_for:
        return "current"
    if age <= policy.warning_for:
        reasons.append(f"evidence.freshness.{item.evidence_type}.warning")
        return "warning"
    reasons.append(f"evidence.freshness.{item.evidence_type}.stale")
    return "stale"


def _utc_observation(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc_datetime(value)
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


def _utc_datetime(value: datetime) -> datetime:
    # DuckDB stores these timestamps as UTC-naive values.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _validate_public_label(name: str, value: str | None) -> None:
    if value is None:
        return
    if not value.strip() or len(value) > 120 or any(character in value for character in "\r\n\0"):
        raise ValueError(f"{name} must be a compact display label")


def _validate_labels(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    for value in values:
        _validate_public_label(name, value)


_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "credentials",
        "password",
        "provider_payload",
        "raw_payload",
        "refresh_token",
        "secret",
        "token",
        "access_token",
    }
)


def _reject_sensitive_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            compact = "".join(character for character in lowered if character.isalnum())
            sensitive_marker = any(
                marker in compact
                for marker in (
                    "apikey",
                    "accesstoken",
                    "authorization",
                    "bearertoken",
                    "credential",
                    "password",
                    "providerpayload",
                    "rawpayload",
                    "refreshtoken",
                    "secret",
                )
            )
            if lowered in _SENSITIVE_KEYS or sensitive_marker:
                raise ValueError("public payload contains a sensitive or raw-provider field")
            _reject_sensitive_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_sensitive_keys(nested)


def _require_member(name: str, value: str, allowed: frozenset[str]) -> None:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"unknown {name}: {value!r}; expected one of {allowed_values}")


def _validate_reason_code(value: str) -> None:
    parts = value.split(".")
    if (
        len(parts) < 2
        or any(not part for part in parts)
        or any(not part.replace("_", "").replace("-", "").isalnum() for part in parts)
        or any(part != part.lower() for part in parts)
    ):
        raise ValueError("reason_codes must be lowercase dotted codes")


def _requires_reason(state: EvidenceDisplayState) -> bool:
    return any(
        (
            state.source_kind != "real",
            state.source_health != "healthy",
            state.freshness_state != "current",
            state.coverage_state != "complete",
            state.action_eligibility != "eligible",
            state.source_name is None and state.evidence_type is not None,
            bool(state.missing_inputs),
            state.effectiveness_sample_size == 0,
        )
    )


def _validate_precedence(state: EvidenceDisplayState) -> None:
    must_block = any(
        (
            state.source_health == "blocked",
            state.source_kind in {"fixture", "proxy", "unknown"},
            state.source_name is None and state.evidence_type is not None,
            state.freshness_state in {"stale", "blocked", "unknown"},
            state.coverage_state in {"missing", "unsupported", "unknown"},
        )
    )
    must_caution = any(
        (
            state.source_health in {"degraded", "unknown"},
            state.source_kind == "inferred",
            state.freshness_state == "warning",
            state.coverage_state == "partial",
            state.effectiveness_sample_size == 0,
        )
    )
    if must_block and state.action_eligibility != "blocked":
        raise ValueError("blocking evidence must have blocked action eligibility")
    if not must_block and must_caution and state.action_eligibility == "eligible":
        raise ValueError("limited evidence cannot have eligible action eligibility")
