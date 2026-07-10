from dashboard.application.operations import OperationsStatusQueries


class FakeWorker:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


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

