from dashboard.cli import cli_loop

CSV_PATH = "tests/data/sample.csv"

def test_csv_import(monkeypatch, capsys):
    inputs = iter([
    f"import {CSV_PATH}",
    "show",
    "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cli_loop()

    out = capsys.readouterr().out

    assert "Portfolio Dashboard" in out 
    assert "BN.TO  qty: 30" in out
    assert "Goodbye." in out