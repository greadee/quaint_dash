"""Transaction importers for manual and CSV portfolio ledger entries."""
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
    """Template for staging, validating, and committing transaction imports."""
    manager: DashboardManager
    batch_id: int | None = field(default=None, init=False)
    import_time: datetime | None = field(default=None, init=False)

    def run(self):
        """Run the import pipeline and return a summary of affected portfolios."""
        self.batch_id, self.import_time = self._append_batch_table()
        self._stage_import()
        self._normalize_txn_stage()
        self._validate_txn_stage()
        self._initialize_imported_assets()
        import_data = self._handle_import()
        self.manager.update_positions()
        self._ingest_imported_asset_metadata()

        return import_data
    
    def _normalize_txn_stage(self):
        """Normalize staged string fields into database-ready transaction columns."""
        conn = self.manager.conn
        conn.execute(qry.NORMALIZE_TXN)

    def _validate_txn_stage(self):
        """Run validation queries and fail before committing invalid staged rows."""
        conn = self.manager.conn 
        for q in qry.VALIDATE_TXN_SUITE:
            result = conn.execute(q).fetchone()[0] 
            # ideally, each query in the validation suite should yield a count of 0
            if result:
                self._handle_validation_fail(q)

    def _initialize_imported_assets(self):
        """Create referenced assets and metadata sync rows before inserting txns."""
        conn = self.manager.conn
        conn.execute(qry.INITIALIZE_IMPORTED_ASSETS)
        conn.execute(qry.INITIALIZE_IMPORTED_ASSET_METADATA_SYNC)

    def _ingest_imported_asset_metadata(self):
        """Best-effort metadata refresh for assets referenced by the import."""
        try:
            from dashboard.services.asset_importer import AssetImporter

            asset_importer = AssetImporter(self.manager)
            asset_importer.import_stage_assets()

        except Exception:
            # intentionally swallow — ingestion is best-effort
            pass
            
    def _handle_validation_fail(self, query_failure):
        """Remove the import batch marker and surface the validation failure."""
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
    """Import one manually entered transaction through the shared staging path."""
    txn: tTestTxn
    create_portfolio: bool | None = None
    batch_type: str = "manual-entry"

    def _append_batch_table(self):
        """Create an import batch row and return its id and timestamp."""
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type],).fetchone()
        return (row[0], row[1])

    def _stage_import(self):
        """Stage the manual transaction for normalization and validation."""
        self.manager.conn.execute(qry.STAGE_TXN_MANUAL, list(vars(self.txn).values())[1:],)
      
    def _handle_import(self):
        """Commit the validated manual transaction batch."""
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
    """Import a CSV transaction batch through the shared staging path."""
    csv_path: Path
    delim: str = ","
    batch_type: str = "csv-import"

    def _append_batch_table(self):
        """Create an import batch row and return its id and timestamp."""
        row = self.manager.conn.execute(qry.INSERT_IMPORT_BATCH, [self.batch_type],).fetchone()
        return (row[0], row[1])

    def _validate_csv_cols(self):
        """Ensure the staged CSV has every required transaction column."""
        conn = self.manager.conn
        cols = [r[0] for r in conn.execute("DESCRIBE stg_txn").fetchall()]
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}. Found columns: {cols}")

    def _stage_import(self):
        """Load the CSV into staging, then validate its columns."""
        conn = self.manager.conn
        conn.execute(qry.STAGE_TXN_CSV, [str(self.csv_path), self.delim],)
        self._validate_csv_cols()

    def _handle_import(self): 
        """Commit the validated CSV transaction batch."""
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



    
