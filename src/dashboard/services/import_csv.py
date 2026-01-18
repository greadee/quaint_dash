from dataclasses import dataclass
from pathlib import Path 
from dashboard.models.storage import PortfolioStore
from dashboard.db import queries as qry

REQUIRED_COLUMNS = [
    "portfolio_id",
    "time_stamp",
    "txn_type",
    "asset_id",
    "qty",
    "price",
    "ccy",
    "cash_amt",
    "fee_amt",
    "ext_ref",
]

@dataclass(frozen=True)
class ImportData:
    """
    Metadata return type for TxnImporterCSV.import_csv(...)

    param: staged_rows - # rows entered in staging table
           inserted_rows - # rows appended to db
           skipped_rows - # rows not appended to db
           portfolios_affected -  portfolio_id's for portfolios that had transactions added in the batch.
    """
    staged_rows: int 
    inserted_rows: int
    skipped_rows: int 
    portfolios_affected: list[str]

class TxnImporterCSV:
    def __init__(self, store: PortfolioStore):
        self.store = store

    def import_csv(self, csv_path: Path, delim: str = ",", staging_table: str = "stg_txn_import"): 
        """
        Imports and validates a transaction batch from a csv file.
        Cash transactions may have empty columns, so they are sent to a staging table,
            set to NULL, and then added as a batch to the database.

        param: delim - what character columns are separated by in the csv file
               staging_table - name of the sql table to stage in

        ret: ImportData object    
        """
        conn = self.store.conn

        # init stage table
        conn.execute(f"DROP TABLE IF EXISTS {staging_table}")
        conn.execute(f"""
            CREATE TEMP TABLE {staging_table} AS
            SELECT * FROM read_csv_auto(
                ?,
                delim=?,
                header=true,
                ignore_errors=false
            );"""
            , [csv_path, delim],)
        
        # validate csv columns
        cols = [r[0] for r in conn.execute(f"DESCRIBE {staging_table}").fetchall()]
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}. Found columns: {cols}")
        
        conn.execute(f"""
            UPDATE {staging_table} 
            SET 
                asset_id = NULLIF(asset_id, ''),
                qty = NULLIF(qty, ''),
                price = NULLIF(price, '');      
            """)

        n_rows_staged = conn.execute(f"SELECT COUNT(*) FROM {staging_table}").fetchone()[0]

        portfolios_affected = list(r[0] for r in conn.execute(f"SELECT DISTINCT portfolio_id FROM {staging_table}").fetchall())

        n_txn_before = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]

        conn.execute(qry.INSERT_TXN_BATCH)
        
        n_txn_after = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
        n_rows_inserted = n_txn_after - n_txn_before
        n_rows_skipped = n_rows_staged - n_rows_inserted

        return ImportData(n_rows_staged, n_rows_inserted, n_rows_skipped, portfolios_affected)