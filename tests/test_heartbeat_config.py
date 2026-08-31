"""Tests for heartbeat configuration and URL inheritance logic."""

from unittest.mock import MagicMock

from kuma_scout.plugins.base import Plugin
from kuma_scout.plugins.models import GlobalConfig, HeartbeatConfig, UptimeKumaConfig


class TestHeartbeatURLInheritance:
    """Test heartbeat URL inheritance from global uptime_kuma config."""

    def test_heartbeat_url_from_heartbeat_config(self):
        """Test heartbeat uses its own URL when set."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=UptimeKumaConfig(
                    url="http://heartbeat-kuma:3001/api/push",
                    token="heartbeat_token",
                ),
            ),
        )

        # Create a minimal mock plugin to test _initialize_heartbeat
        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"

        # Call the actual method
        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should be initialized with heartbeat-specific URL
        assert plugin.heartbeat is not None
        assert plugin.heartbeat.uptime_kuma_url == "http://heartbeat-kuma:3001/api/push"
        assert plugin.heartbeat.heartbeat_token == "heartbeat_token"

    def test_heartbeat_url_from_global_uptime_kuma(self):
        """Test heartbeat inherits URL from global uptime_kuma when not set."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=UptimeKumaConfig(
                    token="heartbeat_token",
                    # url is None, should inherit from global
                ),
            ),
        )

        # Create a minimal mock plugin to test _initialize_heartbeat
        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"

        # Call the actual method
        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should inherit URL from global uptime_kuma
        assert plugin.heartbeat is not None
        assert plugin.heartbeat.uptime_kuma_url == "http://global-kuma:3001/api/push"
        assert plugin.heartbeat.heartbeat_token == "heartbeat_token"

    def test_heartbeat_token_only_no_url(self):
        """Test heartbeat with token-only config when global URL exists."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=UptimeKumaConfig(
                    token="heartbeat_token",
                ),
            ),
        )

        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"

        Plugin._initialize_heartbeat(plugin)

        assert plugin.heartbeat is not None
        assert plugin.heartbeat.uptime_kuma_url == "http://global-kuma:3001/api/push"
        assert plugin.heartbeat.heartbeat_token == "heartbeat_token"

    def test_heartbeat_disabled(self):
        """Test heartbeat is not initialized when disabled."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=False,
                uptime_kuma=UptimeKumaConfig(
                    token="heartbeat_token",
                ),
            ),
        )

        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"
        plugin.heartbeat = None

        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should not be initialized
        assert plugin.heartbeat is None

    def test_heartbeat_missing_token(self):
        """Test heartbeat skips with warning when token is missing."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=None,  # No uptime_kuma config, no token
            ),
        )

        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"
        plugin.heartbeat = None

        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should not be initialized
        assert plugin.heartbeat is None
        output_handler.warning.assert_called()

    def test_heartbeat_missing_url(self):
        """Test heartbeat skips with warning when URL is missing."""
        global_config = GlobalConfig(
            uptime_kuma=None,  # No global uptime_kuma
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=UptimeKumaConfig(
                    token="heartbeat_token",
                    # url is None
                ),
            ),
        )

        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"
        plugin.heartbeat = None

        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should not be initialized
        assert plugin.heartbeat is None
        output_handler.warning.assert_called()

    def test_heartbeat_empty_config(self):
        """Test heartbeat with no uptime_kuma config when global exists."""
        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
                token="global_token",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=None,  # Empty heartbeat config
            ),
        )

        output_handler = MagicMock()
        plugin = MagicMock(spec=Plugin)
        plugin.global_config = global_config
        plugin.output_handler = output_handler
        plugin.name = "test"
        plugin.heartbeat = None

        Plugin._initialize_heartbeat(plugin)

        # Heartbeat should not initialize - token is required
        assert plugin.heartbeat is None
        output_handler.warning.assert_called()

    def test_heartbeat_cli_override_existing_config(self):
        """Test CLI override adds token to existing heartbeat config."""
        from kuma_scout.cli.config_merger import ConfigMerger

        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=UptimeKumaConfig(
                    url="http://custom-heartbeat:3001/api/push",
                ),
            ),
        )

        ConfigMerger.apply_cli_to_global_config(
            global_config=global_config,
            uptime_kuma_url=None,
            token=None,
            heartbeat_token="cli_token",
            timeout=300,
            log_file=None,
            log_level=None,
        )

        # Token should be added, URL should remain
        assert global_config.heartbeat.uptime_kuma is not None
        assert global_config.heartbeat.uptime_kuma.token == "cli_token"
        assert (
            global_config.heartbeat.uptime_kuma.url
            == "http://custom-heartbeat:3001/api/push"
        )

    def test_heartbeat_cli_override_empty_config(self):
        """Test CLI override creates heartbeat config when none exists."""
        from kuma_scout.cli.config_merger import ConfigMerger

        global_config = GlobalConfig(
            uptime_kuma=UptimeKumaConfig(
                url="http://global-kuma:3001/api/push",
            ),
            heartbeat=HeartbeatConfig(
                enabled=True,
                uptime_kuma=None,
            ),
        )

        ConfigMerger.apply_cli_to_global_config(
            global_config=global_config,
            uptime_kuma_url=None,
            token=None,
            heartbeat_token="cli_token",
            timeout=300,
            log_file=None,
            log_level=None,
        )

        # Config should be created with token
        assert global_config.heartbeat.uptime_kuma is not None
        assert global_config.heartbeat.uptime_kuma.token == "cli_token"
        assert global_config.heartbeat.uptime_kuma.url is None
