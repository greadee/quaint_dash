"""root/tests/
This test suite works on two databases (dashes), one empty and one populated.
    
    Uses pytest fixtures to pass dashboard view (db) instances, and portfolio view (open port) instances.
    Uses pytest parameterization to send collections of commands, and comparison strings for assertion.
        - commands are sent to the cli via monkeypatch, and the output of the cli is captured via sysout and asserted against the comparison string.
    Avoid booting the cli for every test by calling _cli_iter which uses the command line's handling logic/function.
"""
import pytest
from dashboard.db.db_conn import DB, init_db
from dashboard.models.storage import DashboardManager
from dashboard.models.cli_view import DashboardView, PortfolioView


def _cli_iter(view, line: str):
    """
    Simulate one iteration of cli_loop for a *single* line:
      - call view.handle_input(line)
      - if it throws, print the exception (like cli.py does) and stay in same view
      - if it returns a View, switch to it
    """
    try:
        next_view = view.handle_input(line)
    except SystemExit:
        raise
    except Exception as e:
        print(e)
        return view
    return next_view if next_view is not None else view


def _send_input(monkeypatch, inputs):
    """
    Patch builtins.input to return the given inputs in order.
    """
    cmd = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(cmd))


#####################################################################
#          DashboardView: empty dash setup / assertions                 
#####################################################################

@pytest.fixture
def empty_dash(tmp_path) -> DashboardView:
    """
    Fresh DB, schema initialized, no portfolios/txns.
    """
    db_path = tmp_path / "test_empty.db"
    db = DB(db_path)
    init_db(db)
    manager = DashboardManager(db)
    return DashboardView(manager)


# set parameters for test_help_empty_dash
@pytest.mark.parametrize("cmd, expected_substrings", [
    ("help", ["=== Dashboard ===", "Commands:"]),
    ("help list", ["usage: list"]),
    ("help create", ["usage: create"]),
    ("help open", ["usage: open"]),
    ("help import", ["usage: import"]),
    ("help quit", ["exit the program"]),
    ("help nope", ["No such command"]),
    ("nope", ["Unknown command: nope"]),
    ("list", ["[list]"]),   # missing required args 
    ("create", ["[create]"]),  
    ("import", ["[import]"]),   
    ]
)

def test_help_empty_dash(empty_dash, capsys, cmd, expected_substrings):
    """
    Test the help command on all of the valid, and some invalid arguments.
        - Inside of empty DashboardView
    """
    _cli_iter(empty_dash, cmd)
    out = capsys.readouterr().out
    for s in expected_substrings:
        assert s in out


# set parameters for test_list_empty_dash
@pytest.mark.parametrize("cmd, expected_error_fragment", [
    ("list port", "No portfolios found"),
    ("list port -n 1", "No portfolios found"),
    ("list txn", "No transactions found"),
    ("list txn -n 1", "No transactions found"),
    ("list txn --txn-type buy", "No transactions found"),
    ("list txn --asset-id AAPL", "No transactions found"),
    ("list txn --day 01-01-2026", "No transactions found"),  # parses, but empty
    ("list pos", "No positions found"),
    ("list pos --asset-id AAPL", "No positions found"),
    # ("list pos --asset-type equity", "No positions found"), # asset type / subtype 
    # ("list pos --asset-subtype etf", "No positions found"),
    ]
)

def test_list_empty_dash(empty_dash, capsys, cmd, expected_error_fragment):
    """
    Tests the list command, including all flags.
        - Inside of empty DashboardView
    """
    _cli_iter(empty_dash, cmd)
    out = capsys.readouterr().out
    assert expected_error_fragment in out


def test_open_port_empty_dash(empty_dash, capsys):
    """
    Tests error output for trying to open a non-existent portfolio.
        - Inside of empty DashboardView
    """
    _cli_iter(empty_dash, 'open "Does Not Exist"')
    out = capsys.readouterr().out
    assert "Portfolio not found" in out


def test_import_bad_filename(empty_dash, capsys):
    """
    Importer should throw an exception. We assert that it is caught by the CLI.
        - Inside of empty DashboardView
    """
    _cli_iter(empty_dash, 'import "C:/definitely/not/real.csv"')
    out = capsys.readouterr().out
    assert out.strip() != ""  # some error printed


def test_quit_exit(empty_dash, capsys):
    """
    Test both 'exit' and 'quit' commands send a SystemExit exception, and print a goodbye string. 
        - Inside of empty DashboardView
    """
    with pytest.raises(SystemExit):
        _cli_iter(empty_dash, "quit")
    out = capsys.readouterr().out
    assert "Goodbye." in out

    with pytest.raises(SystemExit):
        _cli_iter(empty_dash, "exit")
    out = capsys.readouterr().out
    assert "Goodbye." in out


#####################################################################
#        DashboardView: populated dash setup / assertions                 
#####################################################################


@pytest.fixture
def popl_dash(tmp_path) -> DashboardView:
    """
    Populate db with 2 portfolios, Alpha and Beta each having: 
    several txns across different days/types/assets via TxnImporterManual.
    """
    # not used elsewhere
    from dashboard.services.importer import TxnImporterManual
    from dashboard.services.importer import tTestTxn 

    db_path = tmp_path / "test_popl.db"
    db = DB(db_path)
    init_db(db)
    manager = DashboardManager(db)

    def _add_manual(portfolio_name: str, time_stamp: str, txn_type: str, asset_id=None, qty=None, price=None, ccy="CAD", cash_amt=None, fee_amt=None):
        """
        Helper for ensuring transaction input shape is maintained when adding a transaction to the test db.
        """
        p_id, created = manager.check_new_portfolio_id(portfolio_name)
        txn = tTestTxn(
            portfolio_id=p_id,
            portfolio_name=portfolio_name,
            time_stamp=time_stamp,
            txn_type=txn_type,
            asset_id=asset_id,
            qty=qty,
            price=price,
            ccy=ccy,
            cash_amt=cash_amt,
            fee_amt=fee_amt,
        )
        importer = TxnImporterManual(manager, txn)
       
        if hasattr(importer, "create_portfolio"):
            importer.create_portfolio = created
        importer.run()

    _add_manual("Alpha", "2026-01-01 10:00:00", "contribution", asset_id=None, qty=None, price=None, cash_amt="1000", fee_amt="0")
    _add_manual("Alpha", "2026-01-02 10:00:00", "buy", asset_id="AAPL", qty="2", price="100", cash_amt=None, fee_amt="1")
    _add_manual("Alpha", "2026-01-02 12:00:00", "buy", asset_id="MSFT", qty="1", price="200", cash_amt=None, fee_amt="1")

    _add_manual("Beta", "2026-01-03 09:00:00", "contribution", asset_id=None, qty=None, price=None, cash_amt="500", fee_amt="0")
    _add_manual("Beta", "2026-01-03 10:00:00", "buy", asset_id="AAPL", qty="1", price="110", cash_amt=None, fee_amt="1")

    return DashboardView(manager)


# set parameters for test_list_popl_dash
@pytest.mark.parametrize("cmd, must_contain", [
    ("list port", "PORTFOLIO"),   # header from formatter
    ("list port -n 1", "PORTFOLIO"),
    ("list txn", "TRANSACTION"),    # header from formatter
    ("list txn -n 1", "TRANSACTION"),
    ("list txn --txn-type buy", "buy"),
    ("list txn --asset-id AAPL", "AAPL"),
    ("list txn --day 01-02-2026", "TRANSACTION"), # manager expects MM-DD-YYYY or MM/DD/YYYY `
    ]
)

def test_list_popl_dash(popl_dash, capsys, cmd, must_contain):
    """
    Tests the list function on good inputs for each possible argument.
        - Inside of populated DashboardView
    """
    _cli_iter(popl_dash, cmd)
    out = capsys.readouterr().out
    assert must_contain in out


def test_create_and_open_port(popl_dash, capsys):
    """
    Create a new portfolio 'Epsilon' and open it.
        - Inside of populated DashboardView
    """
    _cli_iter(popl_dash, 'create "Epsilon"')
    out = capsys.readouterr().out
    assert "Upserted portfolio" in out

    # open Epsilon
    next_view = _cli_iter(popl_dash, 'open "Epsilon"')
    out = capsys.readouterr().out
    assert isinstance(next_view, PortfolioView)


def test_bad_date_filter(popl_dash, capsys):
    """
    Tests the list command, including all flags on an empty dashboard.
        - Inside of populated DashboardView
    """
    _cli_iter(popl_dash, "list txn --day 2026-01-02")  # YYYY-MM-DD when MM-DD-YYYY expected
    out = capsys.readouterr().out
    assert "Date" in out and "invalid" in out


#####################################################################
#        PortfolioView: populated dash setup / assertions                 
#####################################################################


def test_list_empty_port(popl_dash, capsys):
    """
    Test list command on an empty PortfolioView instance.
    """
    _cli_iter(popl_dash, 'create "Epsilon"')
    out = capsys.readouterr().out
    assert "Upserted portfolio" in out

    view = _cli_iter(popl_dash, 'open "Epsilon"')
    capsys.readouterr()
    assert isinstance(view, PortfolioView)

    _cli_iter(view, "list txn")
    out = capsys.readouterr().out
    assert "No transactions in portfolio" in out

    _cli_iter(view, "list pos")
    out = capsys.readouterr().out
    assert "No positions in portfolio" in out


@pytest.fixture
def popl_port_view(popl_dash):
    """
    Open existing portfolio and return it as a fixture for tests on populated PortfolioView.
    """
    view = _cli_iter(popl_dash, 'open "Alpha"')
    assert isinstance(view, PortfolioView)
    return view


def test_back_returns_DashboardView(popl_port_view, capsys):
    """
    Tests that the back command exits PortfolioView, returns DashboardView and nothing else.
    """
    view = _cli_iter(popl_port_view, "back")
    out = capsys.readouterr().out
    assert out == ""  # assert no print or error print
    assert isinstance(view, DashboardView)


# set parameters for test_help_in_port
@pytest.mark.parametrize("cmd, expected_substrings", [
    ("help", ["=== Portfolio ===", "Commands:"]),
    ("help list", ["usage: list"]),
    ("help add-transaction", ["interactively enter"]),
    ("help back", ["return to dashboard"]),
    ("help quit", ["exit the program"]),
    ("help nope", ["No such command"]),
    ("nope", ["Unknown command: nope"]),
    ("list", ["[list]"]),
    ]
)

def test_help_in_port(popl_port_view, capsys, cmd, expected_substrings):
    """
    Test the help command on all of the valid, and some invalid arguments.
        - Inside of populated PortfolioView
    """
    _cli_iter(popl_port_view, cmd)
    out = capsys.readouterr().out
    for s in expected_substrings:
        assert s in out


# set parameters for test_list_in_port
@pytest.mark.parametrize("cmd, must_contain", [
    ("list txn", "TRANSACTION"),
    ("list txn -n 1", "TRANSACTION"),
    ("list txn --txn-type buy", "buy"),
    ("list txn --asset-id AAPL", "AAPL"),
    ("list txn --day 01-02-2026", "TRANSACTION"),
    ]
)

def test_list_in_port(popl_port_view, capsys, cmd, must_contain):
    """
    Tests the list function on good inputs for each possible argument does not throw an error.
        - Inside of populated PortfolioView
    """
    _cli_iter(popl_port_view, cmd)
    out = capsys.readouterr().out
    assert must_contain in out


def test_bad_date_filter_in_port(popl_port_view, capsys):
    """
    Tests the list function with a bad date format for the day filter does not throw an error.
        - Inside of populated PortfolioView
    """
    _cli_iter(popl_port_view, "list txn --day 2026-01-02")  # wrong format
    out = capsys.readouterr().out
    assert "Date 2026-01-02 invalid" in out 


def test_quit_exit_in_port(popl_port_view, capsys):
    """
    Test both 'exit' and 'quit' commands send a SystemExit exception, and print a goodbye string. 
        - Inside of populated PortfolioView
    """
    with pytest.raises(SystemExit):
        _cli_iter(popl_port_view, "quit")
    out = capsys.readouterr().out
    assert "Goodbye" in out

    with pytest.raises(SystemExit):
        _cli_iter(popl_port_view, "exit")
    out = capsys.readouterr().out
    assert "Goodbye" in out


def test_add_txn_cancel(popl_port_view, monkeypatch, capsys):
    """
    Test that cancelling an add-transaction command mid-prompt does not kill the CLI.
        - Inside of populated PortfolioView
    """
    # User hits enter immediately for time_stamp => cancel path
    _send_input(monkeypatch, [""])
    _cli_iter(popl_port_view, "add-transaction")
    out = capsys.readouterr().out
    assert "Enter transaction fields" in out
    assert "Cancelled." in out


def test_bad_field_add_txn(monkeypatch, popl_port_view, capsys):
    """
    Test fields that should fail validation/normalization in importer
    _cli_iter should catch and print an error instead of crashing.
        - Inside of populated PortfolioView
    """
    bad_inputs = [
        "2026-01-05 10:00:00",  # time_stamp
        "buy",                  # txn_type
        "AAPL",                 # asset_id
        "not-a-number",         # qty (invalid)
        "100",                  # price
        "CAD",                  # ccy
        "lambda",               # cash_amt
        "blambda",              # fee_amt
    ]
    _send_input(monkeypatch, bad_inputs)
    _cli_iter(popl_port_view, "add-transaction")
    out = capsys.readouterr().out
    assert "Enter transaction fields" in out
    assert out.strip() != "" # something, anything printed

