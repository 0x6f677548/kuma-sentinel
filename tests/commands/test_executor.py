"""Tests for command executor orchestration."""

from unittest.mock import MagicMock, Mock, patch, call
import os
import sys
import yaml
import tempfile

import click
import pytest

from kuma_sentinel.cli.commands.executor import CommandExecutor
from kuma_sentinel.core.config.kopia_snapshot_config import KopiaSnapshotConfig
from kuma_sentinel.core.config.portscan_config import PortscanConfig
from kuma_sentinel.core.models import CheckResult


class ConcreteExecutor(CommandExecutor):
    """Concrete implementation of CommandExecutor for testing."""

    def get_builtin_command(self, base_command):
        """Return the base command as-is for testing."""
        return base_command

    def get_summary_fields(self):
        """Return summary fields for testing."""
        return {
            "Test Configuration": {
                "Command Token": "command_token",
                "Log File": "log_file",
            }
        }


class TestCommandExecutor:
    """Test the CommandExecutor orchestration logic."""

    def test_add_common_arguments(self):
        """Test adding common arguments to a Click command."""
        executor = ConcreteExecutor()

        @click.command()
        def dummy_cmd(**kwargs):
            pass

        decorated = executor._add_common_arguments(dummy_cmd)

        # Check that the command has the expected parameters
        param_names = {p.name for p in decorated.params}
        assert "uptime_kuma_url" in param_names
        assert "heartbeat_token" in param_names
        assert "token" in param_names

    def test_add_common_options(self):
        """Test adding common options to a Click command."""
        executor = ConcreteExecutor()

        @click.command()
        def dummy_cmd(**kwargs):
            pass

        decorated = executor._add_common_options(dummy_cmd)

        # Check that the command has the expected parameters
        param_names = {p.name for p in decorated.params}
        assert "config" in param_names
        assert "log_file" in param_names

    def test_register_command_creates_click_command(self):
        """Test register_command returns a valid Click command."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._help_text = "Test command help"
        executor._config_class = PortscanConfig
        executor._checker_class = Mock()

        cmd = executor.register_command()

        assert cmd.name == "test-cmd"
        assert cmd.help == "Test command help"

    def test_execute_with_invalid_config_file(self):
        """Test execute_with_orchestration handles missing config file."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._checker_class = Mock()

        ctx = MagicMock()
        ctx.obj = {}

        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": "/nonexistent/config.yaml",
            "log_file": None,
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_load.side_effect = FileNotFoundError("Config file not found")

            with pytest.raises(FileNotFoundError):
                executor.execute_with_orchestration(ctx, args)

    def test_config_attribute_mapping_portscan(self):
        """Test config attributes are correctly mapped for portscan command."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig

        config = PortscanConfig()

        # Verify PortscanConfig has the expected attributes
        assert hasattr(config, "command_token")
        assert hasattr(config, "heartbeat_token")
        assert hasattr(config, "uptime_kuma_url")

    def test_config_attribute_mapping_kopia(self):
        """Test config attributes are correctly mapped for kopia command."""
        executor = ConcreteExecutor()
        executor._config_class = KopiaSnapshotConfig

        config = KopiaSnapshotConfig()

        # Verify KopiaSnapshotConfig has the expected attributes
        assert hasattr(config, "command_token")
        assert hasattr(config, "heartbeat_token")
        assert hasattr(config, "uptime_kuma_url")

    def test_send_result_alert_success(self):
        """Test send_result_alert method exists."""
        executor = ConcreteExecutor()
        assert hasattr(executor, "send_result_alert")
        assert callable(executor.send_result_alert)

    def test_send_error_alert_success(self):
        """Test send_error_alert method exists."""
        executor = ConcreteExecutor()
        assert hasattr(executor, "send_error_alert")
        assert callable(executor.send_error_alert)
