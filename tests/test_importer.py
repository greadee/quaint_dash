"""root/tests/
Tests the TxnImporter run() procedure for subclasses TxnImporterCSV and TxnImporterManual
Tests are built in a sequential order, and all operate on the same DB.
"""
from pathlib import Path
from datetime import datetime
import pytest
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.services.importer import TxnImporterCSV, TxnImporterManual, tTestTxn

TMP_FOLDER = "tests/tmp/"
TEST_IMPORTER_DB = "test_importer.db"

@pytest.fixture(scope="module")
def test_manager(test_db_path: Path = Path(TMP_FOLDER + TEST_IMPORTER_DB)):
    """
    Create a fresh DB inside the temp folder and initialize schema
    Return a PortfolioManager object for access by other tests via attribute test_manager
    Pytest fixture to return PortfolioManager instance to test functions
    """
    if test_db_path.exists():
        test_db_path.unlink()

    db = DB(test_db_path)
    init_db(db)
    manager =  DashboardManager(db)

    try: 
        yield manager
    finally: 
        try:
            manager.conn.close()
        except Exception:
            pass
        try: 
            if test_db_path.exists():
                test_db_path.unlink()
        except Exception:
            pass

def test_import_one_port_batch(test_manager: DashboardManager):
    """
    CSV batch import (single portfolio):
    Enforces: - importer instance has sequential batch id 
              - # of portfolios in db reflects ImportData object
              - ImportData/PortfolioImportData object is filled properly
              - txn table is filled properly, and inserted txn has sequential txn id
    """
    csv_path = Path(TMP_FOLDER + "test_import_one_batch.csv")
    csv_path.write_text("\n".join(["portfolio_name,time_stamp,txn_type,asset_id,qty,price,ccy,cash_amt,fee_amt",
                "test 1,2026-01-01 09:30:00,buy,BN.TO,10,63.57,CAD,0,0",
                "test 1,2026-01-02 12:00:00,contribution,,,,CAD,500,0",]),encoding="utf-8",)
    
    importer = TxnImporterCSV(test_manager, csv_path)

    import_data = importer.run()

    # importer object assertion
    assert importer.batch_id == 1

    # ImportData assertions
    assert import_data.batch_id == importer.batch_id
    assert import_data.inserted_rows == 2
    
    portfolios_aff = import_data.portfolios_affected
    assert len(portfolios_aff) == 1
    n_port = test_manager.conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
    assert n_port == len(portfolios_aff)

    # PorfolioImportData assertions
    p_aff = portfolios_aff[0]
    assert p_aff.portfolio_name == "test 1"
    assert p_aff.batch_id == import_data.batch_id

    # db: txn count and seq. id assertions
    n_txn = test_manager.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    assert n_txn == import_data.inserted_rows

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn


def test_import_mul_port_batch(test_manager: DashboardManager):
    """
    CSV batch import (multiple portfolio):
    Enforces: - importer instance has sequential batch id 
              - # of portfolios in db reflects ImportData object
              - ImportData/PortfolioImportData object is filled properly
              - txn table is filled properly, and inserted txn has sequential txn id
              - txn table succesfully normalizes null and float fields
    """
    csv_path = Path(TMP_FOLDER + "test_import_mul_port_batch.csv")
    csv_path.write_text("\n".join(["portfolio_name,time_stamp,txn_type,asset_id,qty,price,ccy,cash_amt,fee_amt",
                "test 1,2026-01-03 10:00:00,buy,AVUV,5,600,USD,,",
                "test 2,2026-01-03 11:00:00,buy,MSFT,3,400,USD,,1",
                "test 1,2026-01-04 09:00:00,dividend,MSFT,3,1,USD,,1",
                "test 2,2026-01-04 09:27:27,withdrawal,,,,CAD,1919,1,"]), encoding="utf-8",)
    
    importer = TxnImporterCSV(test_manager, csv_path)

    import_data = importer.run()

    # importer object assertions
    assert importer.batch_id == 2

    portfolios_aff = import_data.portfolios_affected

    # ImportData assertions
    assert import_data.batch_id == importer.batch_id
    assert import_data.inserted_rows == 4

    assert len(portfolios_aff) == 2
    n_port = test_manager.conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
    assert n_port == len(portfolios_aff)

    for p_aff in portfolios_aff:
        assert p_aff.batch_id == import_data.batch_id
        assert p_aff.portfolio_name in ["test 1", "test 2"]
        if p_aff.created:
            assert p_aff.portfolio_name != "test 1"

    # db: txn count and seq. id assertions
    n_txn = test_manager.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    assert n_txn == import_data.inserted_rows+2

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: txn null and float field assertions
    # asset txn
    amt_tuple = test_manager.conn.execute(
        """SELECT cash_amt, fee_amt 
        FROM txn t 
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id 
        WHERE portfolio_name = ? AND asset_id = ?""", 
        ["test 1", "AVUV"],).fetchone()
    for amt in amt_tuple:
        assert not amt # amt's should be normalized to NoneTypes

    qty_price_tuple = test_manager.conn.execute( 
        """SELECT qty, price 
        FROM txn t 
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND asset_id = ?""", 
        ["test 1", "AVUV"],).fetchone()
    for val in qty_price_tuple:
        assert type(val) is float
    
    # cash txn
    qty_price_tuple = test_manager.conn.execute( 
        """SELECT qty, price 
        FROM txn t 
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND cash_amt = ?""", 
        ["test 2", 1919.0],).fetchone()
    for val in qty_price_tuple:
        assert not val # qty, price should be normalized to NoneTypes

    amt_tuple = test_manager.conn.execute(
        """SELECT cash_amt, fee_amt 
        FROM txn t 
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id 
        WHERE portfolio_name = ? AND cash_amt = ?""", 
        ["test 2", 1919.0],).fetchone()
    for amt in amt_tuple: 
        assert type(amt) is float
    

def test_manual_txn_create(test_manager: DashboardManager):
    """
    Manual add (create):
    Enforces: - importer instance has sequential batch id 
              - ImportData object is filled properly
              - txn table is filled properly, and inserted txn has sequential txn id
              - txn table succesfully normalizes str fields
              - portfolio table both created_at and updated_at is changed to import time
    """
    p_id = 3
    txn = tTestTxn(
        portfolio_id = p_id,
        portfolio_name="test 3",
        time_stamp=datetime.now(),
        txn_type="contribution", 
        asset_id=None,     
        qty=None,
        price=None,
        ccy="CAD",
        cash_amt=500.0,
        fee_amt=0.0,                      
    )
    
    importer = TxnImporterManual(test_manager, txn)

    import_data = importer.run()

    # importer object assertion
    assert importer.batch_id == 3

    # ImportData assertion
    assert len(import_data.portfolios_affected) == 1

    # db: txn count and seq. id assertions
    n_txn = test_manager.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    assert n_txn == import_data.inserted_rows+(2+4)

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: portfolio create assertion
    time_tuple = test_manager.conn.execute(
        "SELECT created_at, updated_at FROM portfolio WHERE portfolio_id = ?", [p_id],
        ).fetchone()
    assert importer.import_time == time_tuple[0]
    assert importer.import_time == time_tuple[1]

def test_manual_txn_upd(test_manager: DashboardManager):
    """
    Manual add (update):
    Enforces: - importer instance has sequential batch id 
              - ImportData object is filled properly
              - txn table is filled properly, and inserted txn has sequential txn id
              - txn table succesfully normalizes str fields
              - portfolio table only updated_at is changed to import time
    """
    p_id = 3
    txn = tTestTxn(
        portfolio_id = p_id,
        portfolio_name = "test 3",
        time_stamp=datetime.now(),
        txn_type=" BUY ", # deliberate test TRIM(), and test LOWER()
        asset_id=" tsm ", # delberate test TRIM(), and test UPPER()      
        qty=2.0,
        price=150.0,
        ccy="usd", # deliberate test UPPER()
        cash_amt=None,
        fee_amt=None,                     
    )
    
    importer = TxnImporterManual(test_manager, txn)

    import_data = importer.run()

    # importer object assertion
    assert importer.batch_id == 4

    # ImportData object assertion
    assert len(import_data.portfolios_affected) == 1

    # db: txn count and seq. id assertions
    n_txn = test_manager.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    assert n_txn == import_data.inserted_rows+(2+4+1)

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: txn str field normalization assertions 
    txn_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    row = test_manager.conn.execute(
        "SELECT portfolio_id, txn_type, asset_id, ccy, batch_id FROM txn WHERE txn_id = ?",
        [txn_id],
    ).fetchone()

    assert row[0] == p_id
    assert row[1] == "buy"
    assert row[2] == "TSM"
    assert row[3] == "USD"
    assert row[4] == importer.batch_id

    # db: portfolio update assertion
    time_tuple = test_manager.conn.execute(
        "SELECT created_at, updated_at FROM portfolio WHERE portfolio_id = ?", [p_id],
        ).fetchone()
    assert importer.import_time != time_tuple[0]
    assert importer.import_time == time_tuple[1]

