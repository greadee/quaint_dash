"""~/db/
DuckDB connection class

- DB: simple class repr. a db connection with one method
    (connect) returning the connection.
- init_db: initializes dashboard db based on
"""

from pathlib import Path

import duckdb

from dashboard.ingestion.stock_catalog import seed_stock_catalog


class DB:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = self.connect()

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.path))


def init_db(db: DB):
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    db.conn.execute(sql)

    # Streaming is a first-class dashboard command, so fresh databases must
    # include its tables before the worker or CLI attempts to query them.
    streaming_schema = schema_path.parent / "migrations" / "live_price_streaming.sql"
    db.conn.execute(streaming_schema.read_text(encoding="utf-8"))

    benchmark_schema = schema_path.parent / "migrations" / "benchmark_indices.sql"
    db.conn.execute(benchmark_schema.read_text(encoding="utf-8"))
    business_strength_schema = schema_path.parent / "migrations" / "business_strength.sql"
    db.conn.execute(business_strength_schema.read_text(encoding="utf-8"))
    seed_stock_catalog(db.conn)
