"""~/db/
DuckDB connection class

- DB: simple class repr. a db connection with one method
    (connect) returning the connection.
- init_db: initializes dashboard db based on
"""

from pathlib import Path
from queue import LifoQueue
from threading import Lock

import duckdb

from dashboard.ingestion.stock_catalog import seed_stock_catalog

_CONNECT_LOCK = Lock()


class DatabaseConnectionPool:
    """Bounded pool of reusable DuckDB connections for concurrent API requests."""

    def __init__(
        self,
        path: str | Path,
        size: int,
    ):
        self.path = Path(path)
        self.size = max(1, size)
        self._available: LifoQueue[duckdb.DuckDBPyConnection] = LifoQueue(self.size)
        for _ in range(self.size):
            self._available.put(connect_database(self.path))

    def acquire(self) -> duckdb.DuckDBPyConnection:
        return self._available.get()

    def release(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._available.put(connection)

    def close(self) -> None:
        for _ in range(self.size):
            self._available.get().close()


class DB:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = self.connect()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return connect_database(self.path)


def connect_database(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection without racing another in-process open call."""
    with _CONNECT_LOCK:
        return duckdb.connect(str(path))


def init_db(db: DB):
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    db.conn.execute(sql)
    _reconcile_ingestion_job_sequence(db.conn)

    # Streaming is a first-class dashboard command, so fresh databases must
    # include its tables before the worker or CLI attempts to query them.
    streaming_schema = schema_path.parent / "migrations" / "live_price_streaming.sql"
    db.conn.execute(streaming_schema.read_text(encoding="utf-8"))

    benchmark_schema = schema_path.parent / "migrations" / "benchmark_indices.sql"
    db.conn.execute(benchmark_schema.read_text(encoding="utf-8"))
    business_strength_schema = schema_path.parent / "migrations" / "business_strength.sql"
    db.conn.execute(business_strength_schema.read_text(encoding="utf-8"))
    financial_news_schema = schema_path.parent / "migrations" / "financial_news.sql"
    db.conn.execute(financial_news_schema.read_text(encoding="utf-8"))
    ingestion_job_schema = schema_path.parent / "migrations" / "ingestion_job_recovery.sql"
    db.conn.execute(ingestion_job_schema.read_text(encoding="utf-8"))
    seed_stock_catalog(db.conn)


def _reconcile_ingestion_job_sequence(conn) -> None:
    """Keep the shared ingestion job sequence ahead of every persisted job id."""
    max_job_id = int(
        conn.execute("SELECT COALESCE(MAX(job_id), 0) FROM ingestion_job").fetchone()[0]
    )
    sequence = conn.execute(
        """
        SELECT start_value, increment_by, last_value
        FROM duckdb_sequences()
        WHERE sequence_name = 'seq_ingestion_job_id'
        """
    ).fetchone()
    if sequence is None:
        raise RuntimeError("seq_ingestion_job_id is missing")

    start_value, increment_by, last_value = sequence
    next_job_id = int(start_value if last_value is None else last_value + increment_by)
    if next_job_id > max_job_id:
        return

    restart_at = max_job_id + 1
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute("ALTER TABLE ingestion_job ALTER COLUMN job_id DROP DEFAULT")
        conn.execute("DROP SEQUENCE seq_ingestion_job_id")
        conn.execute(f"CREATE SEQUENCE seq_ingestion_job_id START {restart_at}")
        conn.execute(
            """
            ALTER TABLE ingestion_job
            ALTER COLUMN job_id SET DEFAULT nextval('seq_ingestion_job_id')
            """
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
