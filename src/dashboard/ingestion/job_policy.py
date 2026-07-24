"""Shared ingestion job retry and failure policy."""

from __future__ import annotations

MAX_INGESTION_JOB_ATTEMPTS = 3

_PERMANENT_FAILURE_MARKERS = (
    "http error 402",
    "plan does not include",
    "call budget exhausted",
)


def is_permanent_ingestion_failure(error_message: str | None) -> bool:
    """Return whether an ingestion failure should not be retried automatically."""
    normalized = (error_message or "").strip().lower()
    return any(marker in normalized for marker in _PERMANENT_FAILURE_MARKERS)
