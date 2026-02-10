"""Tests for zfs_pool plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.models import GlobalConfig, LoggingConfig, UptimeKumaConfig
from kuma_scout.plugins.zfs_pool import ZfsPoolConfig, ZfsPoolPlugin


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
    """Create zfs_pool plugin instance."""
    return ZfsPoolPlugin(global_config=global_config)


@pytest.fixture
def config():
    """Create basic zfs pool config."""
    return ZfsPoolConfig(
        name="test-pool",
        pool="tank",
        min_free_percent=10,
    )


class TestZfsPoolExecution:
    """Test zfs pool plugin execution."""

    def test_healthy_pool_success(self, plugin, config):
        """Test successful check with healthy pool."""
        mock_output = "tank\t50%\tONLINE"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "Pool 'tank' is healthy" in result.message

    def test_low_space_failure(self, plugin, config):
        """Test failure with low free space."""
        config.min_free_percent = 20
        mock_output = "tank\t95%\tONLINE"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "low on space" in result.message

    def test_unhealthy_pool_failure(self, plugin, config):
        """Test failure with unhealthy pool."""
        mock_output = "tank\t50%\tDEGRADED"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "is not healthy" in result.message

    def test_pool_not_found_failure(self, plugin, config):
        """Test failure when pool doesn't exist."""
        mock_output = "cannot open 'tank': no such pool"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", mock_output, 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message

    def test_command_execution_error(self, plugin, config):
        """Test handling of command execution errors."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.side_effect = Exception("Command failed")

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message

    def test_no_pool_configured(self, plugin):
        """Test failure when no pool is configured."""
        config = ZfsPoolConfig(name="test-no-pool", pool="")

        result = plugin.execute(config)

        assert result.status == "down"
        assert "No ZFS pool configured" in result.message

    def test_empty_output_failure(self, plugin, config):
        """Test failure with empty output from zpool."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, "", "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message

    def test_unexpected_output_format_failure(self, plugin, config):
        """Test failure with unexpected output format."""
        mock_output = "tank\t50%"  # Missing health field

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message

    def test_pool_name_mismatch_failure(self, plugin, config):
        """Test failure when pool name doesn't match."""
        mock_output = "otherpool\t50%\tONLINE"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message

    def test_invalid_capacity_format_failure(self, plugin, config):
        """Test failure when capacity cannot be parsed."""
        mock_output = "tank\tinvalid%\tONLINE"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to get status" in result.message
