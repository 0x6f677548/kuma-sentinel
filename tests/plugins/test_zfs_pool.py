"""Tests for zfs_pool plugin."""

from unittest.mock import patch

import pytest

from kuma_scout.plugins.models import GlobalConfig
from kuma_scout.plugins.zfs_pool import ZfsPoolConfig, ZfsPoolPlugin


@pytest.fixture
def global_config():
    """Create basic global config."""
    return GlobalConfig(
        uptime_kuma={"url": "http://localhost:3001/api/push", "token": "global-token"},
        logging={"level": "INFO"},
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
        mock_output = """NAME    SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
tank    100G   50G    50G       -         -         0%     50%   1.00x    ONLINE   -"""

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "up"
            assert "Pool is healthy" in result.message
            assert "50% free space" in result.message

    def test_low_space_failure(self, plugin, config):
        """Test failure with low free space."""
        config.min_free_percent = 20
        mock_output = """NAME    SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
tank    100G   95G     5G       -         -         0%     95%   1.00x    ONLINE   -"""

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Insufficient free space" in result.message

    def test_unhealthy_pool_failure(self, plugin, config):
        """Test failure with unhealthy pool."""
        mock_output = """NAME    SIZE  ALLOC   FREE  CKPOINT  EXPANDSZ   FRAG    CAP  DEDUP    HEALTH  ALTROOT
tank    100G   50G    50G       -         -         0%     50%   1.00x    DEGRADED -"""

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (True, mock_output, "", 0)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Pool is degraded" in result.message

    def test_pool_not_found_failure(self, plugin, config):
        """Test failure when pool doesn't exist."""
        mock_output = "cannot open 'tank': no such pool"

        with patch.object(plugin, "run_command") as mock_run:
            mock_run.return_value = (False, "", mock_output, 1)

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Pool check failed" in result.message

    def test_command_execution_error(self, plugin, config):
        """Test handling of command execution errors."""
        with patch.object(plugin, "run_command") as mock_run:
            mock_run.side_effect = Exception("Command failed")

            result = plugin.execute(config)

            assert result.status == "down"
            assert "Failed to check pool status" in result.message
