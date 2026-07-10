import asyncio

from dashboard.application.operations import OperationsStatusQueries, OperationsWorkerCommands


class FakeWorker:
    def __init__(self, status):
        self._status = status
        self.enabled_calls = 0
        self.disabled_calls = 0
        self.tick_calls = 0

    def status(self):
        return self._status

    def enable(self):
        self.enabled_calls += 1
        self._status = {**self._status, "enabled": True}

    async def disable(self):
        self.disabled_calls += 1
        self._status = {**self._status, "enabled": False}

    async def tick(self):
        self.tick_calls += 1
        return {"ticks": self.tick_calls, "kind": self._status["kind"]}


def test_operations_status_queries_return_worker_snapshots() -> None:
    queries = OperationsStatusQueries(
        ingestion_background_worker=FakeWorker({"enabled": False, "kind": "ingestion"}),
        market_freshness_worker=FakeWorker({"enabled": True, "kind": "market"}),
        data_readiness_worker=FakeWorker({"enabled": False, "kind": "readiness"}),
    )

    assert queries.ingestion_background_status() == {"enabled": False, "kind": "ingestion"}
    assert queries.market_freshness_status() == {"enabled": True, "kind": "market"}
    assert queries.data_readiness_status() == {"enabled": False, "kind": "readiness"}


def test_operations_status_queries_return_copies() -> None:
    source = {"enabled": True}
    queries = OperationsStatusQueries(
        ingestion_background_worker=FakeWorker(source),
        market_freshness_worker=FakeWorker(source),
        data_readiness_worker=FakeWorker(source),
    )

    result = queries.market_freshness_status()
    result["enabled"] = False

    assert source == {"enabled": True}


def test_operations_worker_commands_toggle_workers_and_return_status() -> None:
    ingestion = FakeWorker({"enabled": False, "kind": "ingestion"})
    market = FakeWorker({"enabled": False, "kind": "market"})
    readiness = FakeWorker({"enabled": True, "kind": "readiness"})
    commands = OperationsWorkerCommands(
        ingestion_background_worker=ingestion,
        market_freshness_worker=market,
        data_readiness_worker=readiness,
    )

    assert commands.start_ingestion_background() == {"enabled": True, "kind": "ingestion"}
    assert asyncio.run(commands.stop_data_readiness()) == {"enabled": False, "kind": "readiness"}
    assert ingestion.enabled_calls == 1
    assert readiness.disabled_calls == 1


def test_operations_worker_commands_run_bounded_ticks() -> None:
    ingestion = FakeWorker({"enabled": True, "kind": "ingestion"})
    market = FakeWorker({"enabled": True, "kind": "market"})
    readiness = FakeWorker({"enabled": True, "kind": "readiness"})
    commands = OperationsWorkerCommands(
        ingestion_background_worker=ingestion,
        market_freshness_worker=market,
        data_readiness_worker=readiness,
    )

    assert asyncio.run(commands.tick_ingestion_background()) == {"ticks": 1, "kind": "ingestion"}
    assert asyncio.run(commands.tick_market_freshness()) == {"ticks": 1, "kind": "market"}
    assert asyncio.run(commands.tick_data_readiness()) == {"ticks": 1, "kind": "readiness"}
