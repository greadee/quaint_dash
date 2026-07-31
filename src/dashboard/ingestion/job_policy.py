"""Shared ingestion job retry and failure policy."""

from __future__ import annotations

import os
import socket
from threading import get_ident

MAX_INGESTION_JOB_ATTEMPTS = 3
INGESTION_JOB_LEASE_SECONDS = 300

_PERMANENT_FAILURE_MARKERS = (
    "http error 402",
    "plan does not include",
)


def is_permanent_ingestion_failure(error_message: str | None) -> bool:
    """Return whether an ingestion failure should not be retried automatically."""
    normalized = (error_message or "").strip().lower()
    return any(marker in normalized for marker in _PERMANENT_FAILURE_MARKERS)


def ingestion_worker_id() -> str:
    """Return a bounded owner identifier for durable job leases."""
    return f"{socket.gethostname()}:{os.getpid()}:{get_ident()}"[:128]
