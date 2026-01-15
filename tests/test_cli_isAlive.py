from dashboard.cli import cli_loop

def test_cli_isAlive(monkeypatch, capsys):
    '''
    test_cli_isAlive: test that the CLI starts and exits properly.
    Uses monkeypatch to simulate user input, and capsys to capture stdout. 
    Verfifies that the startup banner and exit message are printed.
    '''
    inputs = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    cli_loop()

    out = capsys.readouterr().out

    assert "Portfolio Dashboard" in out 
    assert "Goodbye." in out