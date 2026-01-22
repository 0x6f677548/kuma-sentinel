"""Tests for ZfsPoolStatusChecker."""

from unittest.mock import MagicMock, patch

from kuma_sentinel.core.checkers.zfs_pool_checker import ZfsPoolStatusChecker
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
