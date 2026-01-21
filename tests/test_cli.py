"""Tests for CLI application."""

from click.testing import CliRunner

from kuma_sentinel.cli.app import cli


def test_cli_version():
    """Test CLI version flag."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output
