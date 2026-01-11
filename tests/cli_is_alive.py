from dashboard.cli import cli_loop

def test_cli_is_alive(monkeypatch, capsys):
    inputs = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cli_loop()

    out = capsys.readouterr().out

    assert "Portfolio Dashboard" in out 
    assert "Goodbye." in out