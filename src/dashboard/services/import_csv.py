from dataclasses import dataclass
from pathlib import Path 
from dashboard.models.storage import PortfolioManager, PortfolioStore
from dashboard.db import queries as qry

REQUIRED_CSV_COLUMNS = [
    "portfolio_name",
    "time_stamp",
    "txn_type",
    "asset_id",
    "qty",
    "price",
    "ccy",
    "cash_amt",
    "fee_amt"
]

@dataclass(frozen=True)
class ImportData:
    """
    Metadata return type for TxnImporterCSV.import_csv(...)

    param: batch_id - integer sequence 
           inserted_rows - # rows appended to db
           portfolios_affected - portfolio_name for portfolios that had transactions added in the batch.
    """
    batch_id: int
    inserted_rows: int
    # tuple contents: (portfolio_id, portfolio_name, created?, batch_id)
    portfolios_affected: list[tuple[int, str, bool, int]]

class TxnImporterCSV:
    def __init__(self, store: PortfolioManager):
        self.store = store

    def get_next_batch_id(self, portfolio_id: int, batch_type: str):
        """
        Return the next batch id in sequence
        """
        conn = self.store.conn
        return conn.execute(qry.GET_NEXT_BATCH, [portfolio_id, portfolio_id, batch_type],).fetchone()[0]
        
    def validate_txn_stage(self):
        """
        Runs a suite of SQL queries on the staged txn table
        Breaks and raises a ValueError if any of the queries yield a bad result
        """
        conn = self.store.conn 
        for q in qry.VALIDATE_TXN_SUITE:
            result = conn.execute(q).fetchone()[0]
            # ideally, the validation suite should yield no results
            if result:
                raise ValueError(f"CSV validation step failed: {q}")

    def import_csv(self, csv_path: Path, delim: str = ","): 
        """
        Imports and validates a transaction batch from a csv file.
        Cash transactions may have empty columns, so they are sent to a staging table,
            set to NULL, and then added as a batch to the database.

        param: delim - what character columns are separated by in the csv file
               normalize_txn_csv - name of the sql table to stage in

        ret: ImportData object    
        """
        conn = self.store.conn
        portfolios_affected = []

        # init stage table
        conn.execute(qry.STAGE_TXN_CSV, [csv_path, delim],)

        # validate csv columns
        cols = [r[0] for r in conn.execute(f"DESCRIBE stg_txn_csv").fetchall()]
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}. Found columns: {cols}")

        # normalize stage table
        conn.execute(qry.NORMALIZE_TXN_CSV)

        # validate normalization table
        self.validate_txn_stage()
   
        portfolio_name_in_batch = list(r[0] for r in conn.execute(f"SELECT DISTINCT portfolio_name FROM norm_txn_csv").fetchall())

        n_txn_before = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]

        for p_name in portfolio_name_in_batch:
            created = self.store.upsert_portfolio(p_name)
            portfolio_obj = self.store.open_portfolio_by_name(p_name).load_portfolio()
            p_id = portfolio_obj.portfolio_id
            batch_id = self.get_next_batch_id(p_id, "csv-import")
            portfolios_affected.append((p_id, p_name, created, batch_id))

        conn.execute(qry.INSERT_TXN_BATCH, [batch_id],)
        
        n_txn_after = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
        n_rows_inserted = n_txn_after - n_txn_before

        return ImportData(batch_id, n_rows_inserted, portfolios_affected)