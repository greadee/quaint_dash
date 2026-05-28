"""
root/tests/
Tests the TxnImporter run() procedure for subclasses TxnImporterCSV and TxnImporterManual.
Tests are built in a sequential order, and all operate on the same DB.
"""
from pathlib import Path
from datetime import datetime
import pytest
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.services.txn_importer import TxnImporterCSV, TxnImporterManual, tTestTxn

TEST_DB_FOLDER = "data/test/"
TEST_IMPORTER_DB = "test_importer.db"
TMP_FOLDER = "tests/tmp/"


@pytest.fixture(autouse=True)
def ensure_test_dir():
    Path("data/test").mkdir(parents=True, exist_ok=True)
    Path("tests/tmp").mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def test_manager(test_db_path: Path = Path(TEST_DB_FOLDER + TEST_IMPORTER_DB)):
    """
    Create a fresh DB inside the temp folder and initialize schema.
    Return a DashboardManager object for access by other tests.
    """
    if test_db_path.exists():
        test_db_path.unlink()

    db = DB(test_db_path)
    init_db(db)
    manager = DashboardManager(db)

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
    CSV batch import (single portfolio).

    Enforces:
      - importer instance has sequential batch id
      - number of portfolios in db reflects ImportData object
      - ImportData/PortfolioImportData object is filled properly
      - txn table is filled properly, and inserted txn has sequential txn id
      - initialization stage inserts staged asset ids into asset table
      - cash transactions do not create asset rows
    """
    csv_path = Path(TMP_FOLDER + "test_import_one_batch.csv")
    csv_path.write_text(
        "\n".join([
            "portfolio_name,time_stamp,txn_type,asset_id,qty,price,ccy,cash_amt,fee_amt",
            "test 1,2026-01-01 09:30:00,buy,BN.TO,10,63.57,CAD,0,0",
            "test 1,2026-01-02 12:00:00,contribution,,,,CAD,500,0",
        ]),
        encoding="utf-8",
    )

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

    # PortfolioImportData assertions
    p_aff = portfolios_aff[0]
    assert p_aff.portfolio_name == "test 1"
    assert p_aff.batch_id == import_data.batch_id

    # db: txn count and seq. id assertions
    n_txn = test_manager.conn.execute("SELECT COUNT(*) FROM txn").fetchone()[0]
    assert n_txn == import_data.inserted_rows

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: initialization stage asset assertions
    asset_rows = test_manager.conn.execute(
        "SELECT asset_id, asset_type, ccy FROM asset ORDER BY asset_id"
    ).fetchall()
    assert len(asset_rows) == 1
    assert asset_rows[0][0] == "BN.TO"
    assert asset_rows[0][1] == "stock"
    assert asset_rows[0][2] == "CAD"

    # cash contribution should not create an asset row
    cash_asset_count = test_manager.conn.execute(
        """
        SELECT COUNT(*)
        FROM asset
        WHERE asset_id IS NULL
        """
    ).fetchone()[0]
    assert cash_asset_count == 0


def test_import_mul_port_batch(test_manager: DashboardManager):
    """
    CSV batch import (multiple portfolio).

    Enforces:
      - importer instance has sequential batch id
      - number of portfolios in db reflects ImportData object
      - ImportData/PortfolioImportData object is filled properly
      - txn table is filled properly, and inserted txn has sequential txn id
      - txn table successfully normalizes null and float fields
      - initialization stage inserts new distinct asset ids only once
    """
    csv_path = Path(TMP_FOLDER + "test_import_mul_port_batch.csv")
    csv_path.write_text(
        "\n".join([
            "portfolio_name,time_stamp,txn_type,asset_id,qty,price,ccy,cash_amt,fee_amt",
            "test 1,2026-01-03 10:00:00,buy,AVUV,5,600,USD,,",
            "test 2,2026-01-03 11:00:00,buy,MSFT,3,400,USD,,1",
            "test 1,2026-01-04 09:00:00,dividend,MSFT,3,1,USD,,1",
            "test 2,2026-01-04 09:27:27,withdrawal,,,,CAD,1919,1",
        ]),
        encoding="utf-8",
    )

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
    assert n_txn == import_data.inserted_rows + 2

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: txn null and float field assertions
    # asset txn
    amt_tuple = test_manager.conn.execute(
        """
        SELECT cash_amt, fee_amt
        FROM txn t
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND asset_id = ?
        """,
        ["test 1", "AVUV"],
    ).fetchone()
    for amt in amt_tuple:
        assert not amt  # amounts should be normalized to None/falsey

    qty_price_tuple = test_manager.conn.execute(
        """
        SELECT qty, price
        FROM txn t
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND asset_id = ?
        """,
        ["test 1", "AVUV"],
    ).fetchone()
    for val in qty_price_tuple:
        assert type(val) is float

    # cash txn
    qty_price_tuple = test_manager.conn.execute(
        """
        SELECT qty, price
        FROM txn t
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND cash_amt = ?
        """,
        ["test 2", 1919.0],
    ).fetchone()
    for val in qty_price_tuple:
        assert not val

    amt_tuple = test_manager.conn.execute(
        """
        SELECT cash_amt, fee_amt
        FROM txn t
        JOIN portfolio p ON p.portfolio_id = t.portfolio_id
        WHERE portfolio_name = ? AND cash_amt = ?
        """,
        ["test 2", 1919.0],
    ).fetchone()
    for amt in amt_tuple:
        assert type(amt) is float

    # db: initialization stage asset assertions
    asset_ids = [
        row[0]
        for row in test_manager.conn.execute(
            "SELECT asset_id FROM asset ORDER BY asset_id"
        ).fetchall()
    ]
    assert asset_ids == ["AVUV", "BN.TO", "MSFT"]

    # MSFT appeared twice in staged txns but should only be initialized once
    msft_count = test_manager.conn.execute(
        "SELECT COUNT(*) FROM asset WHERE asset_id = 'MSFT'"
    ).fetchone()[0]
    assert msft_count == 1


def test_manual_txn_create(test_manager: DashboardManager):
    """
    Manual add (create).

    Enforces:
      - importer instance has sequential batch id
      - ImportData object is filled properly
      - txn table is filled properly, and inserted txn has sequential txn id
      - portfolio table both created_at and updated_at is changed to import time
      - cash-only manual imports do not create asset rows
    """
    p_id = 3
    txn = tTestTxn(
        portfolio_id=p_id,
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
    assert n_txn == import_data.inserted_rows + (2 + 4)

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: portfolio create assertion
    time_tuple = test_manager.conn.execute(
        "SELECT created_at, updated_at FROM portfolio WHERE portfolio_id = ?",
        [p_id],
    ).fetchone()
    assert importer.import_time == time_tuple[0]
    assert importer.import_time == time_tuple[1]

    # db: initialization stage asset assertion
    # contribution has no asset_id, so asset table should be unchanged
    asset_ids = [
        row[0]
        for row in test_manager.conn.execute(
            "SELECT asset_id FROM asset ORDER BY asset_id"
        ).fetchall()
    ]
    assert asset_ids == ["AVUV", "BN.TO", "MSFT"]


def test_manual_txn_upd(test_manager: DashboardManager):
    """
    Manual add (update).

    Enforces:
      - importer instance has sequential batch id
      - ImportData object is filled properly
      - txn table is filled properly, and inserted txn has sequential txn id
      - txn table successfully normalizes string fields
      - portfolio table only updated_at is changed to import time
      - initialization stage inserts normalized manual asset id into asset table
    """
    p_id = 3
    txn = tTestTxn(
        portfolio_id=p_id,
        portfolio_name="test 3",
        time_stamp=datetime.now(),
        txn_type=" BUY ",
        asset_id=" tsm ",
        qty=2.0,
        price=150.0,
        ccy="usd",
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
    assert n_txn == import_data.inserted_rows + (2 + 4 + 1)

    max_id = test_manager.conn.execute("SELECT MAX(txn_id) FROM txn").fetchone()[0]
    assert max_id == n_txn

    # db: txn string field normalization assertions
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

    # db: initialization stage asset assertion
    asset_row = test_manager.conn.execute(
        "SELECT asset_id, asset_type, ccy FROM asset WHERE asset_id = 'TSM'"
    ).fetchone()
    assert asset_row is not None
    assert asset_row[0] == "TSM"
    assert asset_row[1] == "stock"
    assert asset_row[2] == "USD"

    # db: portfolio update assertion
    time_tuple = test_manager.conn.execute(
        "SELECT created_at, updated_at FROM portfolio WHERE portfolio_id = ?",
        [p_id],
    ).fetchone()
    assert importer.import_time != time_tuple[0]
    assert importer.import_time == time_tuple[1]
