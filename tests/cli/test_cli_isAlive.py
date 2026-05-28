"""root/tests/
cli smoke test
"""

from dashboard.cli import cli_loop

def test_cli_isAlive(monkeypatch, capsys):
    '''
    test_cli_isAlive: test that the CLI starts and exits properly.
    Uses monkeypatch to simulate user input, and capsys to capture stdout. 
    Verfifies that the startup banner and exit message are printed.
    '''
    inputs = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    
    try:
        cli_loop()
    except SystemExit: # allow for reading sys.out after SystemExit
        pass

    out = capsys.readouterr().out

    assert "=== Dashboard ===" in out 
    assert "Goodbye." in out