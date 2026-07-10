"""Operations/Data Quality application use cases."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class WorkerStatusSource(Protocol):
    """Minimal interface for workers that expose process-local status."""

    def status(self) -> Mapping[str, Any]:
        """Return the worker's current status snapshot."""


class WorkerCommandSource(WorkerStatusSource, Protocol):
    """Minimal interface for controllable process-local workers."""

    def enable(self) -> None:
        """Enable the worker for this process."""

    async def disable(self) -> None:
        """Disable and stop the worker for this process."""

    async def tick(self) -> Mapping[str, Any]:
        """Run one bounded work cycle."""


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


class OperationsWorkerCommands:
    """Operations worker command use cases."""

    def __init__(
        self,
        ingestion_background_worker: WorkerCommandSource,
        market_freshness_worker: WorkerCommandSource,
        data_readiness_worker: WorkerCommandSource,
    ) -> None:
        self._ingestion_background_worker = ingestion_background_worker
        self._market_freshness_worker = market_freshness_worker
        self._data_readiness_worker = data_readiness_worker

    def start_ingestion_background(self) -> dict[str, Any]:
        self._ingestion_background_worker.enable()
        return dict(self._ingestion_background_worker.status())

    async def stop_ingestion_background(self) -> dict[str, Any]:
        await self._ingestion_background_worker.disable()
        return dict(self._ingestion_background_worker.status())

    async def tick_ingestion_background(self) -> dict[str, Any]:
        return dict(await self._ingestion_background_worker.tick())

    def start_market_freshness(self) -> dict[str, Any]:
        self._market_freshness_worker.enable()
        return dict(self._market_freshness_worker.status())

    async def stop_market_freshness(self) -> dict[str, Any]:
        await self._market_freshness_worker.disable()
        return dict(self._market_freshness_worker.status())

    async def tick_market_freshness(self) -> dict[str, Any]:
        return dict(await self._market_freshness_worker.tick())

    def start_data_readiness(self) -> dict[str, Any]:
        self._data_readiness_worker.enable()
        return dict(self._data_readiness_worker.status())

    async def stop_data_readiness(self) -> dict[str, Any]:
        await self._data_readiness_worker.disable()
        return dict(self._data_readiness_worker.status())

    async def tick_data_readiness(self) -> dict[str, Any]:
        return dict(await self._data_readiness_worker.tick())
