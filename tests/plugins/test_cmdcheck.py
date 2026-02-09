"""Tests for cmdcheck plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.cmdcheck import CmdCheckConfig, CmdCheckPlugin
from kuma_scout.plugins.models import GlobalConfig, LoggingConfig, UptimeKumaConfig


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma=UptimeKumaConfig(
            url="http://localhost:3001/api/push", token="global-token"
        ),
        logging=LoggingConfig(level="INFO"),
    )


@pytest.fixture
def plugin(global_config):
    """Create cmdcheck plugin instance."""
    return CmdCheckPlugin(global_config=global_config)


@pytest.fixture
def config():
    """Create basic cmdcheck config."""
    return CmdCheckConfig(
        name="test-cmd",
        command="test -f /tmp/file",
        expect_exit_code=0,
    )


class TestCmdCheckExecution:
    """Test cmdcheck plugin execution."""

    def test_success_message_includes_stdout(self, plugin, config):
        """Test successful command message includes stdout."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "file exists\n", "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert result.details["exit_code"] == 0
            assert "stdout: file exists" in result.message

    def test_failure_message_includes_stderr(self, plugin, config):
        """Test failed command message includes stderr."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", "file not found", 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert result.details["exit_code"] == 1
            assert "stderr: file not found" in result.message

    def test_success_pattern_match(self, plugin, config):
        """Test success when output matches success pattern."""
        config.success_pattern = r"Status: healthy"
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "Status: healthy", "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "stdout: Status: healthy" in result.message

    def test_failure_pattern_match(self, plugin, config):
        """Test failure when output matches failure pattern."""
        config.failure_pattern = r"ERROR:"
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "ERROR: connection refused", "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "stdout: ERROR: connection refused" in result.message

    def test_command_execution_error(self, plugin, config):
        """Test handling of command execution errors."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.side_effect = Exception("Command failed")

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Check execution failed" in result.message

    def test_output_sanitization(self, plugin, config):
        """Test that output is sanitized when enabled."""
        config.sanitize_output = True
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "password: secret123", "", 0)

            result = plugin.execute(config)

            # Assuming DataSanitizer replaces sensitive data
            assert "secret123" not in result.message

    def test_output_not_sanitized(self, plugin, config):
        """Test that output is not sanitized when disabled."""
        config.sanitize_output = False
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "password: secret123", "", 0)

            result = plugin.execute(config)

            assert "secret123" in result.message
