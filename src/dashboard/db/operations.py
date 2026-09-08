"""Read adapter for Operations queue diagnostics."""

from typing import Any

import duckdb


class OperationsQueueRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def status_groups(self) -> list[dict[str, Any]]:
        # One SELECT gives counts and oldest timestamps from the same snapshot.
        # Error text is classification input only and never leaves the use case.
        cursor = self._conn.execute("""
            SELECT status, domain, dataset, COUNT(*) AS count,
                   MIN(created_at) AS oldest_created_at,
                   CASE WHEN status IN ('dead_letter', 'failed') THEN LEFT(error_message, 4096) END AS error_message,
                   CASE WHEN status IN ('dead_letter', 'failed') THEN LEFT(terminal_reason, 4096) END AS terminal_reason
            FROM ingestion_job
            GROUP BY status, domain, dataset, 6, 7
        """)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
