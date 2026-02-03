"""Tests for CLI application."""

from typer.testing import CliRunner

from kuma_scout.cli.app import app

runner = CliRunner()


def test_cli_version():
    """Test CLI version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output


def test_subcommand_common_options():
    """Test that check subcommands have all common options available."""
    result = runner.invoke(app, ["portscan", "--help"])
    assert result.exit_code == 0
    # Check for common options that should appear in check subcommands
    assert "--log-file" in result.output
    assert "--log-level" in result.output
    assert "--uptime-kuma-url" in result.output
    assert "--token" in result.output
    # Check for plugin-specific options
    assert "--targets" in result.output
    assert "--ports" in result.output
