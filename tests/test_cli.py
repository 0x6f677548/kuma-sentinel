"""Tests for CLI application."""

from typer.testing import CliRunner

from kuma_scout.cli.app import app

runner = CliRunner()


def test_cli_version():
    """Test CLI version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output
