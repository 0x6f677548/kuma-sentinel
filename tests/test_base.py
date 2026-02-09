"""Tests for base plugin functionality."""

from unittest.mock import Mock, patch

import pytest

from kuma_scout.core.models import CheckResult
from kuma_scout.plugins.base import CheckConfig, Plugin, execute_with_timing
from kuma_scout.plugins.models import (
    GlobalConfig,
    HeartbeatConfig,
    RetryConfig,
    SSHConfig,
    UptimeKumaConfig,
)


class TestCheckConfig:
    """Test CheckConfig model."""

    def test_check_config_defaults(self):
        """Test CheckConfig with default values."""
        config = CheckConfig(name="test-check")
        assert config.name == "test-check"
        assert config.timeout == 30
        assert config.retry.attempts == 0
        assert config.retry.delay_seconds == 5  # Default is 5 seconds
        assert config.uptime_kuma is None
        assert config.ssh is None

    def test_check_config_with_values(self):
        """Test CheckConfig with custom values."""
        retry_config = RetryConfig(attempts=2, delay_seconds=5)
        uptime_config = UptimeKumaConfig(url="http://test.com", token="test-token")
        ssh_config = SSHConfig(host="example.com", user="testuser")

        config = CheckConfig(
            name="test-check",
            timeout=60,
            retry=retry_config,
            uptime_kuma=uptime_config,
            ssh=ssh_config,
        )

        assert config.name == "test-check"
        assert config.timeout == 60
        assert config.retry.attempts == 2
        assert config.retry.delay_seconds == 5
        assert config.uptime_kuma is not None
        assert config.uptime_kuma.url == "http://test.com"
        assert config.ssh is not None
        assert config.ssh.host == "example.com"


class MockPlugin(Plugin):
    """Mock plugin for testing."""

    name = "mock"
    description = "Mock plugin for testing"
    config_class = CheckConfig

    @execute_with_timing
    def execute(self, config: CheckConfig) -> CheckResult:
        """Mock execute method."""
        return CheckResult(
            check_name=config.name,
            status="up",
            message="Mock check passed",
            duration_seconds=1,
        )


class TestPluginBase:
    """Test Plugin base class."""

    @pytest.fixture
    def global_config(self):
        """Create a global config for testing."""
        return GlobalConfig(
            uptime_kuma=UptimeKumaConfig(url="http://test.com", token="test-token"),
            heartbeat=HeartbeatConfig(
                enabled=True, token="heartbeat-token", interval=60
            ),
            ssh=SSHConfig(host="example.com", user="testuser"),
        )

    @pytest.fixture
    def mock_output_handler(self):
        """Create a mock output handler."""
        return Mock()

    def test_plugin_initialization_success(self, global_config, mock_output_handler):
        """Test successful plugin initialization."""
        with patch.object(MockPlugin, "_initialize_heartbeat"), patch.object(
            MockPlugin, "_initialize_ssh"
        ):
            plugin = MockPlugin(global_config, output_handler=mock_output_handler)

            assert plugin.name == "mock"
            assert plugin.description == "Mock plugin for testing"
            assert plugin.global_config == global_config
            assert plugin.output_handler == mock_output_handler

    @patch("kuma_scout.plugins.base.HeartbeatService")
    def test_initialize_heartbeat_enabled(
        self, mock_heartbeat_service, global_config, mock_output_handler
    ):
        """Test heartbeat initialization when enabled."""
        plugin = MockPlugin.__new__(MockPlugin)  # Create without calling __init__
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        plugin._initialize_heartbeat()

        mock_heartbeat_service.assert_called_once_with(
            mock_output_handler,
            "http://test.com",
            "heartbeat-token",
            60,
            check_name="mock",
        )
        assert plugin.heartbeat is not None

    def test_initialize_heartbeat_disabled(self, global_config, mock_output_handler):
        """Test heartbeat initialization when disabled."""
        global_config.heartbeat.enabled = False
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.heartbeat = None

        plugin._initialize_heartbeat()

        mock_output_handler.debug.assert_called_once_with(
            "Heartbeat disabled (heartbeat.enabled=false)", echo=False
        )
        assert plugin.heartbeat is None

    def test_initialize_heartbeat_missing_token(
        self, global_config, mock_output_handler
    ):
        """Test heartbeat initialization with missing token."""
        global_config.heartbeat.token = None
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.heartbeat = None

        plugin._initialize_heartbeat()

        mock_output_handler.warning.assert_called_once_with(
            "Heartbeat enabled but token missing - check will run without heartbeat notifications",
            echo=False,
        )
        assert plugin.heartbeat is None

    def test_initialize_heartbeat_missing_url(self, global_config, mock_output_handler):
        """Test heartbeat initialization with missing URL."""
        global_config.uptime_kuma = None
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.heartbeat = None

        plugin._initialize_heartbeat()

        mock_output_handler.warning.assert_called_once_with(
            "Heartbeat enabled but Uptime Kuma URL missing - check will run without heartbeat notifications",
            echo=False,
        )
        assert plugin.heartbeat is None

    @patch("kuma_scout.plugins.base.SSHRunner")
    def test_initialize_ssh(self, mock_ssh_runner, global_config, mock_output_handler):
        """Test SSH initialization."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler

        plugin._initialize_ssh()

        mock_ssh_runner.assert_called_once_with(
            host="example.com",
            user="testuser",
            port=22,
            key_file=None,
            password=None,
            strict_host_key_checking=True,
        )
        assert plugin.ssh_runner is not None

    def test_initialize_ssh_none(self, mock_output_handler):
        """Test SSH initialization when no SSH config."""
        global_config = GlobalConfig()
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.ssh_runner = None

        plugin._initialize_ssh()

        assert plugin.ssh_runner is None

    @patch("kuma_scout.plugins.base.time.sleep")
    def test_execute_with_retry_success(
        self, mock_sleep, global_config, mock_output_handler
    ):
        """Test successful execution with retry."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        config = CheckConfig(
            name="test-check", retry=RetryConfig(attempts=1, delay_seconds=1)
        )

        result = plugin._execute_with_retry(config)

        assert result.status == "up"
        assert result.check_name == "test-check"
        mock_sleep.assert_not_called()

    @patch("kuma_scout.plugins.base.time.sleep")
    def test_execute_with_retry_failure_then_success(
        self, mock_sleep, global_config, mock_output_handler
    ):
        """Test execution that fails then succeeds on retry."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        # Mock execute to fail first, succeed second
        call_count = 0

        def mock_execute(config):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CheckResult(
                    check_name=config.name,
                    status="down",
                    message="Failed",
                    duration_seconds=1,
                )
            return CheckResult(
                check_name=config.name,
                status="up",
                message="Success",
                duration_seconds=1,
            )

        plugin.execute = mock_execute
        config = CheckConfig(
            name="test-check", retry=RetryConfig(attempts=1, delay_seconds=2)
        )

        result = plugin._execute_with_retry(config)

        assert result.status == "up"
        mock_sleep.assert_called_once_with(2)

    def test_start_heartbeat(self, global_config, mock_output_handler):
        """Test starting heartbeat."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        mock_heartbeat = Mock()
        plugin.heartbeat = mock_heartbeat

        plugin._start_heartbeat()

        mock_heartbeat.send_message.assert_called_once_with("mock check starting...")
        mock_heartbeat.start.assert_called_once()

    def test_start_heartbeat_none(self, global_config, mock_output_handler):
        """Test starting heartbeat when none configured."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.heartbeat = None

        # Should not raise
        plugin._start_heartbeat()

    def test_send_heartbeat_completion(self, global_config, mock_output_handler):
        """Test sending heartbeat completion."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        mock_heartbeat = Mock()
        plugin.heartbeat = mock_heartbeat

        result = CheckResult(
            check_name="test",
            status="up",
            message="Success",
            duration_seconds=5,
        )

        plugin._send_heartbeat_completion(result)

        mock_heartbeat.send_message.assert_called_once_with(
            "mock completed in 5s (status: up)"
        )

    def test_stop_heartbeat(self, global_config, mock_output_handler):
        """Test stopping heartbeat."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.name = "mock"

        mock_heartbeat = Mock()
        plugin.heartbeat = mock_heartbeat

        plugin._stop_heartbeat()

        mock_heartbeat.stop.assert_called_once()

    @patch("kuma_scout.plugins.base.subprocess.run")
    def test_run_command_local_success(
        self, mock_subprocess_run, global_config, mock_output_handler
    ):
        """Test running command locally successfully."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.ssh_runner = None  # No SSH

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = "error"
        mock_subprocess_run.return_value = mock_result

        success, stdout, stderr, exit_code = plugin.run_command(["echo", "test"])

        assert success is True
        assert stdout == "output"
        assert stderr == "error"
        assert exit_code == 0
        mock_subprocess_run.assert_called_once()

    @patch("kuma_scout.plugins.base.subprocess.run")
    def test_run_command_local_timeout(
        self, mock_subprocess_run, global_config, mock_output_handler
    ):
        """Test running command locally with timeout."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.ssh_runner = None

        from subprocess import TimeoutExpired

        mock_subprocess_run.side_effect = TimeoutExpired(["sleep", "10"], 30)

        success, stdout, stderr, exit_code = plugin.run_command(
            ["sleep", "10"], timeout=30
        )

        assert success is False
        assert stdout == ""
        assert stderr == "Command timed out after 30s"
        assert exit_code == -1

    @patch("kuma_scout.plugins.base.subprocess.run")
    def test_run_command_local_file_not_found(
        self, mock_subprocess_run, global_config, mock_output_handler
    ):
        """Test running command locally when command not found."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler
        plugin.ssh_runner = None

        mock_subprocess_run.side_effect = FileNotFoundError("Command not found")

        success, stdout, stderr, exit_code = plugin.run_command(["nonexistent"])

        assert success is False
        assert stdout == ""
        assert "Command not found: nonexistent" in stderr
        assert exit_code == -1

    @patch("kuma_scout.plugins.base.SSHRunner")
    def test_run_command_ssh_success(
        self, mock_ssh_runner_class, global_config, mock_output_handler
    ):
        """Test running command via SSH successfully."""
        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler

        mock_ssh_runner = Mock()
        mock_ssh_runner.run.return_value = (True, "ssh_output", "ssh_error", 0)
        plugin.ssh_runner = mock_ssh_runner

        success, stdout, stderr, exit_code = plugin.run_command(["ls", "-la"])

        assert success is True
        assert stdout == "ssh_output"
        assert stderr == "ssh_error"
        assert exit_code == 0
        mock_ssh_runner.run.assert_called_once_with(["ls", "-la"], 30)

    @patch("kuma_scout.plugins.base.SSHRunner")
    def test_run_command_ssh_connection_error(
        self, mock_ssh_runner_class, global_config, mock_output_handler
    ):
        """Test running command via SSH with connection error."""
        from kuma_scout.core.utils.ssh_runner import SSHConnectionError

        plugin = MockPlugin.__new__(MockPlugin)
        plugin.global_config = global_config
        plugin.output_handler = mock_output_handler

        mock_ssh_runner = Mock()
        mock_ssh_runner.run.side_effect = SSHConnectionError("Connection failed")
        plugin.ssh_runner = mock_ssh_runner

        success, stdout, stderr, exit_code = plugin.run_command(["ls"])

        assert success is False
        assert stdout == ""
        assert stderr == "SSH connection failed: Connection failed"
        assert exit_code == -1
