"""Tests for CLI application."""

import os
from unittest.mock import Mock

from typer.testing import CliRunner

from kuma_scout.cli.app import app
from kuma_scout.cli.generator import CLIGenerator
from kuma_scout.plugins.models import GlobalConfig

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
    assert "--retry-attempts" in result.output
    assert "--retry-delay-seconds" in result.output
    # Check for plugin-specific options
    assert "TAR" in result.output
    assert "--ports" in result.output


def test_apply_command_line_overrides_expands_tokens():
    """Test that _apply_command_line_overrides expands environment variables in tokens."""
    generator = CLIGenerator()
    config = GlobalConfig()
    logger = Mock()

    # Set environment variable
    os.environ['TEST_TOKEN'] = 'expanded_token_value'
    os.environ['TEST_HEARTBEAT_TOKEN'] = 'expanded_heartbeat_value'

    try:
        generator._apply_command_line_overrides(
            global_config=config,
            uptime_kuma_url='http://example.com',
            token='$TEST_TOKEN',
            heartbeat_token='$TEST_HEARTBEAT_TOKEN',
            timeout=300,
            logger=logger,
        )

        assert config.uptime_kuma.token == 'expanded_token_value'
        assert config.heartbeat.token == 'expanded_heartbeat_value'
    finally:
        # Clean up environment variables
        del os.environ['TEST_TOKEN']
        del os.environ['TEST_HEARTBEAT_TOKEN']


def test_setup_ssh_config_expands_password():
    """Test that _setup_ssh_config expands environment variables in ssh_password."""
    generator = CLIGenerator()
    config = GlobalConfig()
    logger = Mock()

    # Set environment variable
    os.environ['TEST_SSH_PASSWORD'] = 'expanded_password_value'

    try:
        generator._setup_ssh_config(
            global_config=config,
            ssh='user@host',
            ssh_key_file=None,
            ssh_password='$TEST_SSH_PASSWORD',
            ssh_strict_host_key_checking=True,
            ssh_no_strict_host_key_checking=False,
            logger=logger,
        )

        assert config.ssh.password == 'expanded_password_value'
    finally:
        # Clean up environment variable
        del os.environ['TEST_SSH_PASSWORD']
