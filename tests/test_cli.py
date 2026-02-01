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
    """Test that subcommands have all common options available."""
    result = runner.invoke(app, ["portscan", "--help"])
    assert result.exit_code == 0
    # Check for various common options that should appear in help
    assert "--config" in result.output
    assert "--log-file" in result.output
    assert "--log-level" in result.output
    assert "--uptime-kuma-url" in result.output
    assert "--heartbeat-token" in result.output
    assert "--token" in result.output
    assert "--retry-count" in result.output
    assert "--retry-delay" in result.output
    # Note: Some options may be truncated in long help output, so we check the key ones
