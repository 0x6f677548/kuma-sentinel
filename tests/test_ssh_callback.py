"""Tests for CLI SSH callback validation."""

import click
import pytest
import typer

from kuma_scout.cli.commands.executor import ssh_config_callback


class TestSSHCallback:
    """Test SSH connection string callback validation."""

    def test_valid_ssh_connection_strings(self):
        """Test that valid SSH connection strings are accepted."""
        valid_strings = [
            "host",
            "user@host",
            "host:22",
            "user@host:22",
            "ssh://user@host:22",
        ]

        for conn_str in valid_strings:
            # Create a minimal Click command for the context
            cmd = click.Command("test")
            param = typer.Option("--test")
            ctx = typer.Context(cmd)
            result = ssh_config_callback(ctx, param, conn_str)
            assert result == conn_str

    def test_invalid_ssh_connection_strings(self):
        """Test that invalid SSH connection strings raise BadParameter."""
        # These strings result in empty/missing host and should raise BadParameter
        invalid_strings = [
            "user@",  # Missing host
            "user@:22",  # Empty host
            ":22",  # Missing host
            "@:22",  # Missing user and host
        ]

        for conn_str in invalid_strings:
            # Create a minimal Click command for the context
            cmd = click.Command("test")
            param = typer.Option("--test")
            ctx = typer.Context(cmd)
            with pytest.raises(typer.BadParameter):
                ssh_config_callback(ctx, param, conn_str)

    def test_none_value_passthrough(self):
        """Test that None values are passed through unchanged."""
        # Create a minimal Click command for the context
        cmd = click.Command("test")
        param = typer.Option("--test")
        ctx = typer.Context(cmd)
        result = ssh_config_callback(ctx, param, None)
        assert result is None


def test_ssh_config_callback():
    """Test the ssh_config_callback with a valid value."""
    cmd = click.Command("test")
    ctx = typer.Context(cmd)
    param = typer.Option("--test")
    value = "test_param"
    result = ssh_config_callback(ctx, param, value)
    assert result == value
