"""~/services/

dispatch for import csv or manual transaction

    tTestTxn: Txn object without the batch_id attribute for testing, and validation prior to database storage.
    TxnImporter: Abstract parent class for importing transactions into the database.
    TxnImporterManual: Abstract child class for importing manual entries from the user in the CLI.
    TxnImporterCSV: Abstract child class for importing batches of transactions from csv files.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path 
from dashboard.models.domain import ImportData, PortfolioImportData
from dashboard.models.storage import DashboardManager
from dashboard.services.table_formatter import PortfolioImportDataTableFormatter, ImportDataTableFormatter
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

@dataclass    
class tTestTxn:
    portfolio_id: int
    portfolio_name: str  
    time_stamp: datetime
    txn_type: str 

    asset_id: str | None
    qty: float | None
    price: float | None

    ccy: str 
    cash_amt: float | None
    fee_amt: float | None


@dataclass
class TxnImporter(ABC):
    """
    Transaction import parent class

    attr:     manager                       - DashboardManager object (for DashboardManager.conn)

              batch_id                     - None on instantiation, insertion to the import_batch table sets the batch_id

              import_time                  - None on instantiation, insertion to the import_batch table sets the datetime object

    methods:  run()                     - the only function that is accesible to use in CLI; runs all other functions 

              _get_batch_id_for_stage() - gets the next batch_id in seq. without incrementing the seq.

     abstract _stage_import()           - implemented by both child classes w/ their unique staging logic     

              _normalize_txn_stage()    - normalizes valid and invalid fields in the staged txn table

              _validate_txn_stage()     - runs an validation query suite on the normalized txn table

     abstract _handle_import()          - inserts the validated normalized table into the txn table
                                          returns a ImportData object detailing the import batch
    """
    manager: DashboardManager
    batch_id: int | None = field(default=None, init=False)
    import_time: datetime | None = field(default=None, init=False)

    def run(self):
        """
        Runs all importer functions as an atomic operation
        Returns an ImportData object if succesful
        """
        self.batch_id, self.import_time = self._append_batch_table()
        self._stage_import()
        self._normalize_txn_stage()
        self._validate_txn_stage()
        return self._handle_import()
    

    def _normalize_txn_stage(self):
        """
        Normalizes transaction field types
        Casts column fields as intended types
        Handles which columns can be left blank and what that means
        Normalizes errors to a sentinel value for the validation suite
        """
        conn = self.manager.conn
        conn.execute(qry.NORMALIZE_TXN)

    def _validate_txn_stage(self):
        """
        Runs a suite of SQL queries on the staged txn table
        Breaks and raises a ValueError if any of the queries yield a bad result
        """
        conn = self.manager.conn 
        for q in qry.VALIDATE_TXN_SUITE:
            result = conn.execute(q).fetchone()[0] 
            # ideally, each query in the validation suite should yield a count of 0
            if result:
                self._handle_validation_fail(q)
            
    def _handle_validation_fail(self, query_failure):
        """
        Called upon a failure in the validation query suite
        Removes the bad entry in import_batch table
        Raises a ValueError
        """
        self.manager.conn.execute("DELETE FROM import_batch WHERE batch_id = ?", [self.batch_id],)
        raise ValueError(f"Transaction validation failed: {query_failure}")
    
    @abstractmethod
    def _append_batch_table(self):
        pass

    @abstractmethod
    def _stage_import(self):
        pass

    @abstractmethod 
    def _handle_import(self):
        pass

@dataclass
class TxnImporterManual(TxnImporter): 
    """
    Manual child class of TxnImporter

    param: txn                          - Txn object

           create_portfolio             - Whether or not this transaction belongs to an existing portfolio

           create_portfolio_name        - If this transaction is for a new portfolio, what is the name? Else, None

           batch_type                   - Batch type field for appending to import batch table

    methods:  abstract _stage_import()  - Populates staging table

              abstract _handle_import() - inserts the validated normalized table into the txn table
                                          returns a ImportData object detailing the import batch
    """
    txn: tTestTxn
    create_portfolio: bool | None = None
    batch_type: str = "manual-entry"

    def _append_batch_table(self):
        """
        Appends import batch to database and returns tuple (batch_id, import_time)
        """
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type],).fetchone()
        return (row[0], row[1])

    def _stage_import(self):
        """
        Insert transaction values into staging table as strings for normalization and type casting in database
        """
        self.manager.conn.execute(qry.STAGE_TXN_MANUAL, list(vars(self.txn).values())[1:],)
      
    def _handle_import(self):
        """
        Docstring for _handle_import
        
        :param self: Description
        """
        conn = self.manager.conn

        p_id = self.txn.portfolio_id
        p_name = self.txn.portfolio_name
        created = self.create_portfolio
        batch_id = self.batch_id

        self.manager._upsert_portfolio_import(p_id, p_name, self.import_time, self.import_time)

        conn.execute(qry.INSERT_TXN_BATCH, [batch_id],)

        p_imp = PortfolioImportData(p_id, p_name, created, batch_id)   
        import_data = ImportData(batch_id, "manual-entry", 1, [p_imp]) 

        ImportDataTableFormatter.header()
        ImportDataTableFormatter(import_data).entry()
        
        PortfolioImportDataTableFormatter.header()
        PortfolioImportDataTableFormatter(p_imp).entry()

        return import_data

@dataclass
class TxnImporterCSV(TxnImporter):
    """
    Manual child class of TxnImporter

    param: csv_path                - Path object for the intended csv to import

           delim                   - String representing what delimeter columns are seperated by in the csv file

           batch_type              - Batch type field for appending to import batch table
    
    methods:  _validate_csv_cols() - Validate that the imported csv contains all of the required columns by looking at the staged table

     abstract _stage_import()      - Populates staging table and validates csv file was valid by running _validate_csv_cols()
              
     abstract _handle_import()     - inserts the validated normalized table into the txn table
                                     returns a ImportData object detailing the import batch
    """
    csv_path: Path
    delim: str = ","
    batch_type: str = "csv-import"

    def _append_batch_table(self):
        """
        Appends import batch to database and returns tuple (batch_id, import_time)
        """
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type],).fetchone()
        return (row[0], row[1])

    def _validate_csv_cols(self):
        """
        Ensures that the staged transaction table derived from the csv file has all required columns
        """
        conn = self.manager.conn
        cols = [r[0] for r in conn.execute("DESCRIBE stg_txn").fetchall()]
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}. Found columns: {cols}")

    def _stage_import(self):
        """
        Insert transaction csv columns into staging table as strings for normalization and type casting in database
        """
        conn = self.manager.conn
        conn.execute(qry.STAGE_TXN_CSV, [str(self.csv_path), self.delim],)
        self._validate_csv_cols()

    def _handle_import(self): 
        """
        Docstring for _handle_import
        
        :param self: Description
        """
        conn = self.manager.conn
        p_aff = []

        portfolios_aff = list(r[0] for r in conn.execute("SELECT DISTINCT portfolio_name FROM norm_stg_txn").fetchall())

        n_txn_before = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]

        for p_name in portfolios_aff:
            
            batch_id = self.batch_id

            p_id, create = self.manager.check_new_portfolio_id(p_name)
            self.manager._upsert_portfolio_import(p_id, p_name, self.import_time, self.import_time)

            p_imp = PortfolioImportData(p_id, p_name, create, batch_id)
            p_aff.append(p_imp)
            

        conn.execute(qry.INSERT_TXN_BATCH, [self.batch_id],)
        
        n_txn_after = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
        inserted_rows  = n_txn_after - n_txn_before
        
        import_data = ImportData(batch_id, self.batch_type, inserted_rows, p_aff)

        ImportDataTableFormatter.header()
        ImportDataTableFormatter(import_data).entry()
        
        PortfolioImportDataTableFormatter.header()
        for p_impData in p_aff:
            PortfolioImportDataTableFormatter(p_impData).entry()

        return import_data



    