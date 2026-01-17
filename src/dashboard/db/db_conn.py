"""/db/
DuckDB connection class 

- DB: simple class repr. a db connection with one method 
    (connect) returning the connection.
- init_db: initializes dashboard db based on 
"""


from dataclasses import dataclass 
from pathlib import Path 

import duckdb 

@dataclass(frozen=True)
class DB:
    path: Path

    def connect(self):
        return duckdb.connect(str(self.path))


def init_db(db: DB):
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    with db.connect() as conn:
        conn.execute(sql)