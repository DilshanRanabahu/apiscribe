from typer.testing import CliRunner

from apiscribe.cli import app

runner = CliRunner()


def test_help_lists_gen_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "gen" in result.output
