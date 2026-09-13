"""Canonical serialization and identities for candidate-engine contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

DECIMAL_QUANTUM = Decimal("0.00000001")
VOLATILE_HASH_FIELDS = frozenset(
    {
        "created_at",
        "output_hash",
        "request_id",
        "runtime_ms",
    }
)

_SEQUENCE_IDENTITIES: dict[str, tuple[str, ...]] = {
    "candidate_reviews": ("candidate_id",),
    "components": ("component_code",),
    "evidence_refs": ("evidence_id",),
    "highlights": ("category", "highlight_code"),
    "missing_metrics": ("metric_code",),
    "reason_codes": (),
    "source_matches": ("source_family", "reason_code", "source_methodology_version"),
    "source_watermarks": ("source_domain",),
    "warnings": ("warning_code",),
}


def canonical_json(value: Any, *, for_hash: bool = False) -> str:
    """Return canonical UTF-8-compatible JSON text for a contract value."""

    return json.dumps(
        _canonical_value(value, for_hash=for_hash),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_hash(value: Any) -> str:
    """Hash material contract fields while excluding documented volatile fields."""

    payload = canonical_json(value, for_hash=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_run_id(methodology_version: str, input_snapshot_hash: str) -> str:
    return _typed_hash("candidate-run", methodology_version, input_snapshot_hash)


def candidate_id(asset_id: str) -> str:
    return _typed_hash("candidate", asset_id)


def candidate_review_id(run_id: str, stable_candidate_id: str) -> str:
    return _typed_hash("candidate-review", run_id, stable_candidate_id)


def candidate_evidence_id(
    *,
    source_domain: str,
    source_schema_version: str,
    source_record_id: str,
    as_of: datetime,
    payload_hash: str,
) -> str:
    return _typed_hash(
        "candidate-evidence",
        source_domain,
        source_schema_version,
        source_record_id,
        _canonical_timestamp(as_of),
        payload_hash,
    )


def is_typed_hash(value: str, prefix: str) -> bool:
    actual_prefix, separator, digest = value.partition(":")
    return (
        actual_prefix == prefix
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def normalize_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical decimals must be finite")
    return format(value.quantize(DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN), "f")


def _typed_hash(prefix: str, *parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(material).hexdigest()}"


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_value(value: Any, *, for_hash: bool) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, Any] = {}
        for contract_field in fields(value):
            if for_hash and contract_field.name in VOLATILE_HASH_FIELDS:
                continue
            field_value = getattr(value, contract_field.name)
            result[contract_field.name] = _canonical_field(
                contract_field.name,
                field_value,
                for_hash=for_hash,
            )
        return result
    if isinstance(value, datetime):
        return _canonical_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return normalize_decimal(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item, for_hash=for_hash)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, for_hash=for_hash) for item in value]
    return value


def _canonical_field(name: str, value: Any, *, for_hash: bool) -> Any:
    if name not in _SEQUENCE_IDENTITIES or not isinstance(value, (list, tuple)):
        return _canonical_value(value, for_hash=for_hash)
    canonical_items = [_canonical_value(item, for_hash=for_hash) for item in value]
    identity_fields = _SEQUENCE_IDENTITIES[name]
    if not identity_fields:
        return sorted(canonical_items)
    return sorted(canonical_items, key=lambda item: _identity_key(item, identity_fields))


def _identity_key(item: Any, identity_fields: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(item, dict):
        raise TypeError("identity-sorted contract sequences must contain dataclasses")
    return tuple(str(item.get(field_name, "")) for field_name in identity_fields)
