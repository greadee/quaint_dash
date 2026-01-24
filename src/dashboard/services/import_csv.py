from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path 
from dashboard.models.storage import PortfolioManager
from dashboard.models.domain import Txn
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
class PortfolioImportData:
    """
    Metadata return type per portfolio for transaction batch import

    param: portfolio_id - self expl.
           portfolio_name - self expl.
           created - whether the portfolio was updated or created
           batch_id - sequential id
    """
    portfolio_id: int 
    portfolio_name: str 
    created: bool
    batch_id: int


@dataclass(frozen=True)
class ImportData:
    """
    Metadata return type for transaction batch import

    param: batch_id - sequential id 
           inserted_rows - # rows appended to db
           portfolios_affected - portfolio_name for portfolios that had transactions added in the batch.
    """
    batch_id: int
    batch_type: str
    inserted_rows: int
    portfolios_affected: list[PortfolioImportData]


@dataclass
class TxnImporter(ABC):
    """
    Transaction import parent class

    attr: manager                       - PortfolioManager object (for PortfolioManager.conn)

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
    manager: PortfolioManager
    batch_id: int | None
    import_time: datetime | None

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
    txn: Txn
    create_portfolio: bool
    create_portfolio_name: str | None
    batch_type: str = "manual-entry"


    def _append_batch_table(self):
        """
        Appends import batch to database and returns tuple (batch_id, import_time)
        """
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type]).fetchall()
        return (row['batch_id'], row['import_time'])

    def _stage_import(self):
        """
        Insert transaction values into staging table as strings for normalization and type casting in database
        """
        self.manager.conn.execute(qry.STAGE_TXN_MANUAL)
      
    def _handle_import(self):
        """
        Docstring for _handle_import
        
        :param self: Description
        """
        conn = self.manager.conn
        p_imp = PortfolioImportData

        p_imp.batch_id = self.batch_id
        fields = list(vars(self.txn).values()).append(self.batch_id)
        conn.execute(qry.INSERT_TXN_BATCH, fields,)

        p_imp.portfolio_id = Txn.portfolio_id

        if not self.create_portfolio:
            row = conn.execute(qry.GET_PORTFOLIO_BY_ID, [p_imp.portfolio_id],).fetchone()[0]
            p_imp.portfolio_name = row['portfolio_name'] 
            p_imp.created = False
            conn.execute(qry.UPSERT_PORTFOLIO, [p_imp.portfolio_id, p_imp.portfolio_name, self.import_time],)

        else: 
            p_imp.portfolio_name = self.create_portfolio_name
            p_imp.created = True
            conn.execute(qry.UPSERT_PORTFOLIO, [p_imp.portfolio_id, p_imp.portfolio_name, self.import_time, self.import_time],)

        return ImportData(p_imp.batch_id, "manual-entry", 1, [p_imp])
        

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
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type]).fetchall()
        return (row['batch_id'], row['import_time'])

    def _validate_csv_cols(self):
        """
        Ensures that the staged transaction table derived from the csv file has all required columns
        """
        conn = self.manager.conn
        cols = [r[0] for r in conn.execute(f"DESCRIBE stg_txn").fetchall()]
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}. Found columns: {cols}")

    def _stage_import(self):
        """
        Insert transaction csv columns into staging table as strings for normalization and type casting in database
        """
        conn = self.manager.conn
        conn.execute(qry.STAGE_TXN_CSV, [self.csv_path, self.delim],)
        self._validate_csv_cols()

    def _handle_import(self): 
        """
        Docstring for _handle_import
        
        :param self: Description
        """
        conn = self.manager.conn
        imp = ImportData
   
        portfolio_name_in_batch = list(r[0] for r in conn.execute(f"SELECT DISTINCT portfolio_name FROM norm_txn_csv").fetchall())

        n_txn_before = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]

        for p_name in portfolio_name_in_batch:
            p_imp = PortfolioImportData
            p_imp.portfolio_name = p_name
            p_imp.created = self.store.upsert_portfolio(p_name)

            portfolio_obj = self.store.open_portfolio_by_name(p_name).load_portfolio()
            p_imp.portfolio_id = portfolio_obj.portfolio_id
            batch_id = self._get_batch_id_for_stage
            
            p_imp.batch_id = batch_id
            imp.portfolios_affected.append(p_imp)
            
            if not p_imp.created:
                conn.execute(qry.UPSERT_PORTFOLIO, [p_imp.portfolio_id, p_imp.portfolio_name, self.import_time],)
            else:
                conn.execute(qry.UPSERT_PORTFOLIO, [p_imp.portfolio_id, p_imp.portfolio_name, self.import_time, self.import_time],)

        conn.execute(qry.INSERT_TXN_BATCH, [self.batch_id],)
        
        n_txn_after = conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
        imp.inserted_rows  = n_txn_after - n_txn_before
    
        return imp