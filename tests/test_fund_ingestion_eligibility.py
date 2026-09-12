"""Regression matrix for liquid Canadian and US fixed-income/cash instruments."""

import pytest
from types import SimpleNamespace

from dashboard.assets.funds import fund_type, reconcile_fund_assets
from dashboard.ingestion.corporate_calendar.worker import CorporateCalendarWorker
from dashboard.ingestion.ticker_universe import TickerUniverseRepository
from dashboard.db.db_conn import DB, init_db
from dashboard.services.asset_importer import AssetImporter
from dashboard.brokers.portfolio import BrokerPortfolioIntegrationService

# Explicit fixture, deliberately independent of the implementation's symbol set.
FUNDS = """
XSH.TO TCSH.TO CASH.TO HSAV.TO CBIL.TO UBIL.U.TO PSA.TO PSU.U.TO
CSAV.TO HISA.NE
CMR.TO ZMMK.TO ZUCM.TO ZST.TO XBB.TO XSB.TO XCB.TO XGB.TO XLB.TO XRB.TO
ZAG.TO ZDB.TO ZFL.TO ZPL.TO VAB.TO VSB.TO VCB.TO VLB.TO
BND BNDX BSV BIV BLV VGSH VGIT VGLT VCSH VCIT VCLT VTIP VBIL
AGG BIL SGOV SHV SHY IEF TLT TIP LQD HYG USFR TFLO GOVT MINT JPST
SPAXX FDRXX FZFXX VMFXX VUSXX VMRXX SWVXX SNSXX SNOXX
""".split()


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db = DB(tmp_path_factory.mktemp("fund-eligibility") / "test.db")
    init_db(db)
    yield db.conn
    db.conn.close()


@pytest.mark.parametrize("symbol", FUNDS)
def test_mislabeled_fund_cannot_schedule_or_fetch_earnings(conn, symbol):
    importer = AssetImporter(SimpleNamespace(conn=None), api_key="test")
    assert importer._map_profile_to_asset_fields(symbol, {"isEtf": False})["asset_type"] in {
        "etf", "mutual_fund"
    }
    conn.execute("INSERT INTO asset(asset_id, symbol, asset_type, ccy) VALUES (?, ?, 'stock', 'USD')",
                 [symbol, symbol])
    conn.execute("INSERT INTO watchlist_ticker(asset_id, is_active) VALUES (?, TRUE)", [symbol])
    universe = TickerUniverseRepository(conn)
    assert symbol in universe.ingestible_asset_ids()
    assert symbol not in universe.ingestible_asset_ids(asset_types=("stock", "adr"))
    assert symbol not in universe.earnings_asset_ids()

    class NoCalls:
        def __getattr__(self, method):
            pytest.fail(f"Fund {symbol} reached provider method {method}")

    for dataset in ("earnings_actuals", "financial_statements"):
        job_id = conn.execute("""
            INSERT INTO ingestion_job(asset_id, domain, job_type, dataset, status)
            VALUES (?, 'corporate', 'refresh', ?, 'pending') RETURNING job_id
        """, [symbol, dataset]).fetchone()[0]
        assert CorporateCalendarWorker(conn, NoCalls()).run_once()
        assert conn.execute("SELECT status FROM ingestion_job WHERE job_id = ?", [job_id]).fetchone() == ("unsupported",)


@pytest.mark.parametrize("symbol", ["CASH", "TD", "BMO", "BLK", "AAPL", "MSFT"])
def test_operating_companies_are_not_classified_by_symbol_fragments(symbol):
    assert fund_type(asset_id=symbol, asset_type="stock") is None


@pytest.mark.parametrize("metadata", [
    {"asset_type": "ETF"}, {"asset_type": "mutual_fund"},
    {"name": "New Canadian Bond ETF", "asset_type": "stock"},
    {"name": "New Treasury Money Market Fund"},
    {"asset_subtype": "money_market"},
])
def test_new_funds_are_recognized_without_symbol_allowlist(metadata):
    assert fund_type(asset_id="NEW-FUND", **metadata) is not None


def test_reconciliation_corrects_labels_and_preserves_prices(conn):
    conn.execute("""
        INSERT INTO asset(asset_id, symbol, asset_type, ccy)
        VALUES ('XSH.TO', 'XSH.TO', 'stock', 'CAD'), ('TCSH.TO', 'TCSH.TO', 'stock', 'CAD')
        ON CONFLICT (asset_id) DO NOTHING
    """)
    conn.execute("UPDATE asset SET asset_type = 'stock' WHERE asset_id IN ('XSH.TO', 'TCSH.TO')")
    conn.execute("INSERT INTO asset_quote_daily(asset_id, date, close, ing_source) VALUES ('XSH.TO', DATE '2026-01-01', 20, 'test')")
    reconcile_fund_assets(conn)
    assert conn.execute("SELECT DISTINCT asset_type FROM asset WHERE asset_id IN ('XSH.TO', 'TCSH.TO')").fetchall() == [("etf",)]
    assert conn.execute("SELECT close FROM asset_quote_daily WHERE asset_id = 'XSH.TO'").fetchone() == (20.0,)


def test_broker_import_labels_funds_on_arrival(tmp_path):
    db = DB(tmp_path / "broker-funds.db")
    init_db(db)
    service = BrokerPortfolioIntegrationService(db.conn)
    service._ensure_asset(SimpleNamespace(asset_id="XSH.TO", ccy="CAD"))
    service._ensure_position_asset(SimpleNamespace(
        asset_id="TCSH.TO", currency="CAD", description="TD Cash Management ETF"
    ))
    assert db.conn.execute("SELECT asset_id, asset_type FROM asset ORDER BY asset_id").fetchall() == [
        ("TCSH.TO", "etf"), ("XSH.TO", "etf")
    ]
    db.conn.close()
