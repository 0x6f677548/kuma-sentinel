"""Tests for cmdcheck plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.cmdcheck import CmdCheckConfig, CmdCheckPlugin
from kuma_scout.plugins.models import GlobalConfig


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma={"url": "http://localhost:3001/api/push", "token": "global-token"},
        logging={"level": "INFO"},
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

    def test_success_exit_code_zero(self, plugin, config):
        """Test successful command with exit code 0."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "file exists\n", "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "Exit code 0" in result.message

    def test_failure_exit_code_nonzero(self, plugin, config):
        """Test failed command with non-zero exit code."""
        config.expect_exit_code = 1
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", "file not found", 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Exit code 1" in result.message

    def test_success_pattern_match(self, plugin, config):
        """Test success when output matches success pattern."""
        config.success_pattern = r"Status: healthy"
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "Status: healthy", "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "Success pattern matched" in result.message

    def test_failure_pattern_match(self, plugin, config):
        """Test failure when output matches failure pattern."""
        config.failure_pattern = r"ERROR:"
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "ERROR: connection refused", "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failure pattern matched" in result.message

    def test_command_execution_error(self, plugin, config):
        """Test handling of command execution errors."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.side_effect = Exception("Command failed")

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Command execution failed" in result.message

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
