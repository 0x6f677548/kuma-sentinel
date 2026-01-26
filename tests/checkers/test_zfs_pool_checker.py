"""Tests for ZfsPoolStatusChecker."""

import subprocess
from unittest.mock import MagicMock, patch

from kuma_sentinel.core.checkers.zfs_pool_checker import (
    ZfsPoolStatusChecker,
    _get_pool_status,
)
from kuma_sentinel.core.config.zfs_pool_config import ZfsPoolStatusConfig


class TestZfsPoolStatusChecker:
    """Test ZfsPoolStatusChecker class."""

    @staticmethod
    def create_config(pools=None, default_threshold=10) -> ZfsPoolStatusConfig:
        """Helper to create a config instance for testing."""
        config = ZfsPoolStatusConfig()
        config.uptime_kuma_url = "http://localhost:3001"
        config.heartbeat_enabled = False
        config.command_token = "test-token"

        if pools is None:
            config.zfspoolstatus_pools = []
        else:
            config.zfspoolstatus_pools = pools

        config.zfspoolstatus_free_space_percent_default = default_threshold
        return config

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_all_pools_healthy(self, mock_status):
        """Test successful execution with all pools healthy and sufficient space."""
        mock_status.side_effect = [
            ("ONLINE", 25.0),  # tank: 25% free
            ("ONLINE", 50.0),  # backup: 50% free
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
                {"name": "backup", "free_space_percent_min": 15},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert "All pools healthy" in result.message
        assert result.details["pool_details"]["tank"]["status"] == "ONLINE"
        assert result.details["pool_details"]["tank"]["free_percent"] == 25.0
        assert result.details["pool_details"]["backup"]["free_percent"] == 50.0

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_per_pool_threshold_override(self, mock_status):
        """Test per-pool threshold overrides global default."""
        mock_status.side_effect = [
            ("ONLINE", 12.0),  # tank: 12% free, within per-pool threshold of 10%
            ("ONLINE", 30.0),  # backup: 30% free, within per-pool threshold of 25%
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
                {"name": "backup", "free_space_percent_min": 25},
            ],
            default_threshold=50,  # Global default is much higher
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert "All pools healthy" in result.message

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_per_pool_uses_global_default(self, mock_status):
        """Test pool without explicit threshold uses global default."""
        mock_status.side_effect = [
            (
                "ONLINE",
                12.0,
            ),  # tank: 12% free (no explicit threshold, uses default 10%)
        ]

        config = self.create_config(
            pools=[
                {"name": "tank"},  # No free_space_percent_min specified
            ],
            default_threshold=10,
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "up"
        assert "All pools healthy" in result.message
        assert result.details["pool_details"]["tank"]["threshold"] == 10

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_unhealthy_pool_online_but_low_space(self, mock_status):
        """Test detection of low free space."""
        mock_status.side_effect = [
            ("ONLINE", 8.0),  # Below 10% threshold
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Low free space" in result.message
        assert "tank: 8.0% < 10%" in result.message
        assert result.details["low_space_pools"] == [("tank", 8.0, 10)]

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_unhealthy_pool_degraded_status(self, mock_status):
        """Test that non-ONLINE status triggers DOWN."""
        mock_status.side_effect = [
            ("DEGRADED", 25.0),  # Degraded but has space
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Unhealthy pools" in result.message
        assert "tank" in result.message
        assert result.details["unhealthy_pools"] == ["tank"]

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_unhealthy_pool_faulted_status(self, mock_status):
        """Test FAULTED pool status triggers DOWN."""
        mock_status.side_effect = [
            ("FAULTED", 50.0),  # Even with space, FAULTED is down
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Unhealthy pools" in result.message
        assert "tank" in result.message

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_unhealthy_pool_offline_status(self, mock_status):
        """Test OFFLINE pool status triggers DOWN."""
        mock_status.side_effect = [
            ("OFFLINE", 100.0),  # OFFLINE triggers DOWN
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Unhealthy pools" in result.message

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_multiple_pools_one_unhealthy(self, mock_status):
        """Test with multiple pools where one is unhealthy."""
        mock_status.side_effect = [
            ("ONLINE", 25.0),  # tank is OK
            ("FAULTED", 40.0),  # backup is faulted
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
                {"name": "backup", "free_space_percent_min": 15},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Unhealthy pools" in result.message
        assert "backup" in result.message
        assert result.details["unhealthy_pools"] == ["backup"]

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_multiple_pools_multiple_issues(self, mock_status):
        """Test priority: unhealthy pools reported before low space."""
        mock_status.side_effect = [
            ("FAULTED", 25.0),  # Unhealthy pool (should be reported first)
            ("ONLINE", 5.0),  # Low space pool
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
                {"name": "backup", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        # Unhealthy pools are reported with higher priority
        assert "Unhealthy pools" in result.message
        assert "tank" in result.message

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_pool_status_retrieval_fails(self, mock_status):
        """Test when pool status cannot be retrieved."""
        mock_status.side_effect = [
            (None, None),  # Pool not found or error
        ]

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "Failed to check pools" in result.message
        assert "tank" in result.message
        assert result.details["failed_pools"] == ["tank"]

    def test_execute_no_pools_configured(self):
        """Test execution with no pools configured."""
        config = self.create_config(pools=[])

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.status == "down"
        assert "No ZFS pools configured" in result.message
        assert result.details["error"] == "no_pools"

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_exception_handling(self, mock_status):
        """Test that unexpected exceptions are caught and reported."""
        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)

        # Mock the internal function to raise an exception
        mock_status.side_effect = RuntimeError("Unexpected error during zpool check")

        result = checker.execute()

        assert result.status == "down"
        assert "error" in result.message.lower()

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_result_duration(self, mock_status):
        """Test that result duration is tracked."""
        mock_status.return_value = ("ONLINE", 25.0)

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.duration_seconds >= 0
        assert isinstance(result.duration_seconds, int)

    @patch("kuma_sentinel.core.checkers.zfs_pool_checker._get_pool_status")
    def test_execute_checker_name_and_metadata(self, mock_status):
        """Test that result has correct checker name and metadata."""
        mock_status.return_value = ("ONLINE", 25.0)

        config = self.create_config(
            pools=[
                {"name": "tank", "free_space_percent_min": 10},
            ]
        )

        logger = MagicMock()
        checker = ZfsPoolStatusChecker(config=config, logger=logger)
        result = checker.execute()

        assert result.check_name == "zfspoolstatus"
        assert "pool_details" in result.details
        assert "tank" in result.details["pool_details"]


# Tests for _get_pool_status function
class TestGetPoolStatus:
    """Test _get_pool_status internal function."""

    @patch("subprocess.run")
    def test_get_pool_status_success_online(self, mock_run):
        """Test successful pool status retrieval with ONLINE status."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55%\tONLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "ONLINE"
        assert free_percent == 45.0  # 100 - 55

    @patch("subprocess.run")
    def test_get_pool_status_success_degraded(self, mock_run):
        """Test successful pool status retrieval with DEGRADED status."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t75%\tDEGRADED\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "DEGRADED"
        assert free_percent == 25.0  # 100 - 75

    @patch("subprocess.run")
    def test_get_pool_status_success_faulted(self, mock_run):
        """Test successful pool status retrieval with FAULTED status."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t90%\tFAULTED\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "FAULTED"
        assert free_percent == 10.0  # 100 - 90

    @patch("subprocess.run")
    def test_get_pool_status_empty_output(self, mock_run):
        """Test when pool command returns empty output."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.warning.assert_called()

    @patch("subprocess.run")
    def test_get_pool_status_insufficient_fields(self, mock_run):
        """Test when zpool output has fewer than expected fields."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\n",  # Only 3 fields instead of 6
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.warning.assert_called()

    @patch("subprocess.run")
    def test_get_pool_status_invalid_capacity_format(self, mock_run):
        """Test when capacity field cannot be parsed."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\tINVALID\tONLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.warning.assert_called()

    @patch("subprocess.run")
    def test_get_pool_status_decimal_capacity(self, mock_run):
        """Test capacity parsing with decimal percentage."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55.5%\tONLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "ONLINE"
        assert free_percent == 44.5  # 100 - 55.5

    @patch("subprocess.run")
    def test_get_pool_status_timeout(self, mock_run):
        """Test timeout during zpool command execution."""
        logger = MagicMock()
        mock_run.side_effect = subprocess.TimeoutExpired("zpool", 30)

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.error.assert_called()
        assert "timeout" in logger.error.call_args[0][0].lower()

    @patch("subprocess.run")
    def test_get_pool_status_called_process_error(self, mock_run):
        """Test CalledProcessError from zpool command."""
        logger = MagicMock()
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "zpool", stderr="no such pool"
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.error.assert_called()
        assert "zpool list failed" in logger.error.call_args[0][0]

    @patch("subprocess.run")
    def test_get_pool_status_file_not_found(self, mock_run):
        """Test FileNotFoundError when zpool command not found."""
        logger = MagicMock()
        mock_run.side_effect = FileNotFoundError("zpool not found")

        health, free_percent = _get_pool_status(logger, "tank")

        assert health is None
        assert free_percent is None
        logger.error.assert_called()
        assert "zpool command not found" in logger.error.call_args[0][0]
        assert "ZFS installed" in logger.error.call_args[0][0]

    @patch("subprocess.run")
    def test_get_pool_status_subprocess_call(self, mock_run):
        """Test that subprocess.run is called with correct arguments."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55%\tONLINE\n",
            returncode=0,
        )

        _get_pool_status(logger, "tank")

        # Verify subprocess.run was called with correct args
        call_args = mock_run.call_args
        assert call_args[0][0] == [
            "zpool",
            "list",
            "-H",
            "-o",
            "name,size,alloc,free,cap,health",
            "tank",
        ]
        assert call_args[1]["timeout"] == 30
        assert call_args[1]["check"] is True

    @patch("subprocess.run")
    def test_get_pool_status_multiple_pools_different_values(self, mock_run):
        """Test querying multiple pools returns different values."""
        logger = MagicMock()

        # First call
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55%\tONLINE\n",
            returncode=0,
        )
        health1, free1 = _get_pool_status(logger, "tank")

        # Second call
        mock_run.return_value = MagicMock(
            stdout="backup\t2.0T\t1.5T\t500G\t75%\tONLINE\n",
            returncode=0,
        )
        health2, free2 = _get_pool_status(logger, "backup")

        assert health1 == "ONLINE"
        assert free1 == 45.0
        assert health2 == "ONLINE"
        assert free2 == 25.0

    @patch("subprocess.run")
    def test_get_pool_status_edge_case_0_percent_capacity(self, mock_run):
        """Test pool with 0% capacity (100% free)."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t0\t1.81T\t0%\tONLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "ONLINE"
        assert free_percent == 100.0

    @patch("subprocess.run")
    def test_get_pool_status_edge_case_100_percent_capacity(self, mock_run):
        """Test pool with 100% capacity (0% free)."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.81T\t0\t100%\tONLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "ONLINE"
        assert free_percent == 0.0

    @patch("subprocess.run")
    def test_get_pool_status_whitespace_handling(self, mock_run):
        """Test proper handling of whitespace in output."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="  tank  \t  1.81T  \t  1.00T  \t  828G  \t  55%  \t  ONLINE  \n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "ONLINE"
        assert free_percent == 45.0

    @patch("subprocess.run")
    def test_get_pool_status_offline_status(self, mock_run):
        """Test pool with OFFLINE status."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55%\tOFFLINE\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "OFFLINE"
        assert free_percent == 45.0

    @patch("subprocess.run")
    def test_get_pool_status_unavail_status(self, mock_run):
        """Test pool with UNAVAIL status."""
        logger = MagicMock()
        mock_run.return_value = MagicMock(
            stdout="tank\t1.81T\t1.00T\t828G\t55%\tUNAVAIL\n",
            returncode=0,
        )

        health, free_percent = _get_pool_status(logger, "tank")

        assert health == "UNAVAIL"
        assert free_percent == 45.0
