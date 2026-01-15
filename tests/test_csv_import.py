from dashboard.cli import cli_loop

CSV_PATH = "tests/data/sample.csv"

def test_csv_import_position(monkeypatch, capsys):
    '''
    test_csv_import: test that the CLI imports and displays position, portfolio and portfolio_weight data.
    Uses monkeypatch to simulate user input, and capsys to capture stdout. 
    !!!!!!!!!!!!!!!!!!!!!!!
    '''
    inputs = iter([
    f"import {CSV_PATH}",
    "show",
    "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cli_loop()

    out = capsys.readouterr().out

    assert "Portfolio Dashboard" in out 
    assert "BN.TO  qty: 30" in out # import positions, show positions. 
    assert "Portfolios: " in out # import positions 
    assert "Goodbye." in out