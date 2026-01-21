"""/db/
DuckDB connection class 

- DB: simple class repr. a db connection with one method 
    (connect) returning the connection.
- init_db: initializes dashboard db based on 
"""
from pathlib import Path 

import duckdb 


class DB:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = self.connect()

    def connect(self):
        return duckdb.connect(str(self.path))
    
def init_db(db: DB):
    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    db.conn.execute(sql)