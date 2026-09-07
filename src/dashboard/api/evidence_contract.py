"""Read-only vocabulary for presenting evidence quality in API responses.

This module intentionally does not evaluate freshness, calculate financial values, or persist
anything. It gives later API/read-model slices one validated language for describing the quality
of the evidence behind an existing result.
"""

from __future__ import annotations

from dataclasses import dataclass


EVIDENCE_DISPLAY_SCHEMA_VERSION = "evidence-display.v1"

SOURCE_KINDS = frozenset({"real", "proxy", "fixture", "inferred", "unknown"})
FRESHNESS_STATES = frozenset({"current", "warning", "stale", "blocked", "unknown"})
COVERAGE_STATES = frozenset({"complete", "partial", "missing", "unsupported", "unknown"})
ACTION_ELIGIBILITY_STATES = frozenset({"eligible", "caution", "blocked"})


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

    def __post_init__(self) -> None:
        _require_member("source_kind", self.source_kind, SOURCE_KINDS)
        _require_member("freshness_state", self.freshness_state, FRESHNESS_STATES)
        _require_member("coverage_state", self.coverage_state, COVERAGE_STATES)
        _require_member(
            "action_eligibility",
            self.action_eligibility,
            ACTION_ELIGIBILITY_STATES,
        )
        if self.schema_version != EVIDENCE_DISPLAY_SCHEMA_VERSION:
            raise ValueError("unsupported evidence display schema version")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must be unique")
        for code in self.reason_codes:
            _validate_reason_code(code)
        if _requires_reason(self) and not self.reason_codes:
            raise ValueError("non-current evidence display state requires a reason code")


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
            state.freshness_state != "current",
            state.coverage_state != "complete",
            state.action_eligibility != "eligible",
        )
    )
