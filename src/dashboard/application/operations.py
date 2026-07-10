"""Operations/Data Quality application queries."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class WorkerStatusSource(Protocol):
    """Minimal interface for workers that expose process-local status."""

    def status(self) -> Mapping[str, Any]:
        """Return the worker's current status snapshot."""


class OperationsStatusQueries:
    """Read-only Operations status use cases.

    API routes depend on this facade instead of reaching into worker
    implementations directly. Worker command behavior remains owned by the
    existing worker classes until the command migration slice.
    """

    def __init__(
        self,
        ingestion_background_worker: WorkerStatusSource,
        market_freshness_worker: WorkerStatusSource,
        data_readiness_worker: WorkerStatusSource,
    ) -> None:
        self._ingestion_background_worker = ingestion_background_worker
        self._market_freshness_worker = market_freshness_worker
        self._data_readiness_worker = data_readiness_worker

    def ingestion_background_status(self) -> dict[str, Any]:
        return dict(self._ingestion_background_worker.status())

    def market_freshness_status(self) -> dict[str, Any]:
        return dict(self._market_freshness_worker.status())

    def data_readiness_status(self) -> dict[str, Any]:
        return dict(self._data_readiness_worker.status())

