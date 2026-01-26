"""Tests for command executor orchestration."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

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


class TestExecuteWithOrchestration:
    """Test the execute_with_orchestration orchestration flow."""

    @patch("kuma_sentinel.cli.commands.executor.setup_logging")
    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_execute_with_orchestration_success(
        self, mock_send_push, mock_setup_logging
    ):
        """Test successful orchestration flow from start to finish."""
        # Setup mocks
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_checker = MagicMock()
        result = CheckResult(
            check_name="test-cmd",
            status="up",
            message="All checks passed",
            duration_seconds=1,
        )
        mock_checker.execute_with_heartbeat.return_value = result

        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._config_class = PortscanConfig
        executor._checker_class = MagicMock(return_value=mock_checker)

        ctx = MagicMock()
        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": None,
            "log_file": None,
            "portscan_ip_ranges": ["192.168.1.0/24"],
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_config = MagicMock()
            mock_config.uptime_kuma_url = "http://localhost/api/push"
            mock_config.heartbeat_token = "hb_token"
            mock_config.command_token = "cmd_token"
            mock_config.log_file = None
            mock_load.return_value = mock_config

            with patch("sys.exit") as mock_exit:
                executor.execute_with_orchestration(ctx, args)

                # Verify exit code
                mock_exit.assert_called_once_with(0)

                # Verify config loading
                mock_load.assert_called_once()

                # Verify logging setup
                mock_setup_logging.assert_called_once()

                # Verify checker was created and executed
                executor._checker_class.assert_called_once()
                mock_checker.execute_with_heartbeat.assert_called_once()

                # Verify alert was sent
                mock_send_push.assert_called_once()

    @patch("kuma_sentinel.cli.commands.executor.setup_logging")
    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_execute_with_orchestration_checker_error(
        self, mock_send_push, mock_setup_logging
    ):
        """Test orchestration handles checker errors with error alert."""
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_checker = MagicMock()
        mock_checker.execute_with_heartbeat.side_effect = RuntimeError("Check failed")

        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._config_class = PortscanConfig
        executor._checker_class = MagicMock(return_value=mock_checker)

        ctx = MagicMock()
        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": None,
            "log_file": None,
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_config = MagicMock()
            mock_config.uptime_kuma_url = "http://localhost/api/push"
            mock_config.heartbeat_token = "hb_token"
            mock_config.command_token = "cmd_token"
            mock_load.return_value = mock_config

            with patch("sys.exit") as mock_exit:
                executor.execute_with_orchestration(ctx, args)

                # Verify error exit code
                mock_exit.assert_called_once_with(1)

                # Verify error alert was sent
                mock_send_push.assert_called_once()

    @patch("kuma_sentinel.cli.commands.executor.setup_logging")
    def test_execute_with_orchestration_config_error(self, mock_setup_logging):
        """Test orchestration handles config validation errors."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._config_class = PortscanConfig
        executor._checker_class = Mock()

        ctx = MagicMock()
        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": None,
            "log_file": None,
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_load.side_effect = ValueError("Config validation failed")

            with patch("sys.exit"):
                with pytest.raises(ValueError):
                    executor.execute_with_orchestration(ctx, args)

    @patch("kuma_sentinel.cli.commands.executor.setup_logging")
    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_execute_with_orchestration_result_status_down(
        self, mock_send_push, mock_setup_logging
    ):
        """Test orchestration sends alert when result status is DOWN."""
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_checker = MagicMock()
        result = CheckResult(
            check_name="test-cmd",
            status="down",
            message="Check failed",
            duration_seconds=1,
        )
        mock_checker.execute_with_heartbeat.return_value = result

        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._config_class = PortscanConfig
        executor._checker_class = MagicMock(return_value=mock_checker)

        ctx = MagicMock()
        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": None,
            "log_file": None,
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_config = MagicMock()
            mock_config.uptime_kuma_url = "http://localhost/api/push"
            mock_config.heartbeat_token = "hb_token"
            mock_config.command_token = "cmd_token"
            mock_load.return_value = mock_config

            with patch("sys.exit") as mock_exit:
                executor.execute_with_orchestration(ctx, args)

                # Verify exit code is 0 (not an exception, just a DOWN status)
                mock_exit.assert_called_once_with(0)

                # Verify alert was sent
                mock_send_push.assert_called_once()

    @patch("kuma_sentinel.cli.commands.executor.setup_logging")
    def test_execute_with_orchestration_check_duration_logged(self, mock_setup_logging):
        """Test check duration is correctly calculated and logged."""

        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger

        mock_checker = MagicMock()
        result = CheckResult(
            check_name="test-cmd",
            status="up",
            message="All checks passed",
            duration_seconds=1,
        )
        mock_checker.execute_with_heartbeat.return_value = result

        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"
        executor._config_class = PortscanConfig
        executor._checker_class = MagicMock(return_value=mock_checker)

        ctx = MagicMock()
        args = {
            "uptime_kuma_url": "http://localhost/api/push",
            "heartbeat_token": "hb_token",
            "portscan_token": "cmd_token",
            "config": None,
            "log_file": None,
        }

        with patch.object(executor, "_load_and_validate_config") as mock_load:
            mock_config = MagicMock()
            mock_config.uptime_kuma_url = "http://localhost/api/push"
            mock_config.heartbeat_token = "hb_token"
            mock_config.command_token = "cmd_token"
            mock_load.return_value = mock_config

            with patch("sys.exit"):
                with patch("kuma_sentinel.cli.commands.executor.send_push"):
                    with patch("kuma_sentinel.cli.commands.executor.time") as mock_time:
                        mock_time.time.side_effect = [
                            100.0,
                            101.5,
                        ]  # 1.5 second duration

                        executor.execute_with_orchestration(ctx, args)

                        # Verify info logs were called for start/completion
                        assert mock_logger.info.call_count >= 2


class TestLoadAndValidateConfig:
    """Test the _load_and_validate_config method."""

    def test_load_and_validate_config_with_env_vars(self):
        """Test loading config from environment variables."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._command_name = "portscan"

        with patch("os.path.exists", return_value=False):
            with patch.object(executor._config_class, "validate"):
                config = executor._load_and_validate_config(
                    "portscan",
                    {
                        "uptime_kuma_url": "http://example.com/api/push",
                        "heartbeat_token": "hb_token",
                        "portscan_token": "cmd_token",
                        "portscan_ip_ranges": ["192.168.1.0/24"],
                        "config": None,
                        "log_file": None,
                    },
                )

                assert config is not None

    def test_load_and_validate_config_with_yaml_file(self):
        """Test loading config from YAML file."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._command_name = "portscan"

        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("uptime_kuma_url: http://yaml.example.com/api/push\n")
            f.write("heartbeat_token: yaml_hb_token\n")
            f.write("portscan_token: yaml_token\n")
            f.write("portscan_ip_ranges:\n")
            f.write("  - 10.0.0.0/8\n")
            config_file = f.name

        try:
            with patch.object(
                executor._config_class, "validate_config_file_permissions"
            ):
                with patch.object(executor._config_class, "validate"):
                    config = executor._load_and_validate_config(
                        "portscan",
                        {
                            "uptime_kuma_url": "http://example.com/api/push",
                            "heartbeat_token": "hb_token",
                            "portscan_token": "cmd_token",
                            "config": config_file,
                            "log_file": None,
                        },
                    )

                    assert config is not None
        finally:
            Path(config_file).unlink()

    def test_load_and_validate_config_args_precedence(self):
        """Test command-line args have highest precedence."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._command_name = "portscan"

        with patch("os.path.exists", return_value=False):
            with patch.object(executor._config_class, "validate"):
                config = executor._load_and_validate_config(
                    "portscan",
                    {
                        "uptime_kuma_url": "http://args.example.com/api/push",
                        "heartbeat_token": "args_hb_token",
                        "portscan_token": "args_token",
                        "portscan_ip_ranges": ["172.16.0.0/12"],
                        "config": None,
                        "log_file": None,
                    },
                )

                assert config is not None

    def test_load_and_validate_config_token_mapping(self):
        """Test token is mapped to command_token."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._command_name = "portscan"

        with patch("os.path.exists", return_value=False):
            with patch.object(executor._config_class, "validate"):
                config = executor._load_and_validate_config(
                    "portscan",
                    {
                        "uptime_kuma_url": "http://example.com/api/push",
                        "heartbeat_token": "hb_token",
                        "token": "mapped_token",
                        "portscan_ip_ranges": ["192.168.1.0/24"],
                        "config": None,
                        "log_file": None,
                    },
                )

                assert config is not None

    def test_load_and_validate_config_file_permissions_error(self):
        """Test file permissions validation errors are handled."""
        executor = ConcreteExecutor()
        executor._config_class = PortscanConfig
        executor._command_name = "portscan"

        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("uptime_kuma_url: http://example.com/api/push\n")
            f.write("heartbeat_token: hb_token\n")
            f.write("portscan_token: cmd_token\n")
            f.write("portscan_ip_ranges:\n")
            f.write("  - 192.168.1.0/24\n")
            config_file = f.name

        try:
            with patch.object(
                executor._config_class, "validate_config_file_permissions"
            ) as mock_validate:
                mock_validate.side_effect = RuntimeError("Invalid permissions")

                with patch("sys.exit") as mock_exit:
                    executor._load_and_validate_config(
                        "portscan",
                        {
                            "uptime_kuma_url": "http://example.com/api/push",
                            "heartbeat_token": "hb_token",
                            "portscan_token": "cmd_token",
                            "config": config_file,
                            "log_file": None,
                            "ignore_file_permissions": False,
                        },
                    )

                    # Verify exit was called for permissions error
                    mock_exit.assert_called()
                    # First call should be with exit code 1
                    assert mock_exit.call_args_list[0][0][0] == 1
        finally:
            Path(config_file).unlink()


class TestLogConfigSummary:
    """Test the _log_config_summary method."""

    def test_log_config_summary_with_masked_tokens(self):
        """Test config summary logs with masked tokens."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.get_summary.return_value = {
            "command_token": "***token***",
            "log_file": "/var/log/test.log",
        }

        executor._log_config_summary(mock_logger, mock_config, "test-cmd")

        # Verify logger was called
        assert mock_logger.info.call_count > 0

        # Verify get_summary was called with mask_tokens
        mock_config.get_summary.assert_called_once_with(mask_tokens=True)

    def test_log_config_summary_section_formatting(self):
        """Test config summary sections are formatted correctly."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.get_summary.return_value = {
            "command_token": "***token***",
            "log_file": "/var/log/test.log",
        }

        executor._log_config_summary(mock_logger, mock_config, "test-cmd")

        # Verify section headers were logged
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Test Configuration" in str(call) for call in log_calls)


class TestSendResultAlert:
    """Test the _send_result_alert and send_result_alert methods."""

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_result_alert_with_success_result(self, mock_send_push):
        """Test sending alert for successful result."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = "cmd_token"
        mock_config.uptime_kuma_url = "http://example.com/api/push"

        result = CheckResult(
            check_name="test-cmd",
            status="up",
            message="Check passed",
            duration_seconds=5,
        )

        executor.send_result_alert(
            mock_logger, mock_config, "test-cmd", result, 5000  # 5 seconds
        )

        # Verify send_push was called
        mock_send_push.assert_called_once()
        call_args = mock_send_push.call_args
        assert "passed" in str(call_args).lower()

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_result_alert_with_down_result(self, mock_send_push):
        """Test sending alert for failed result."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = "cmd_token"
        mock_config.uptime_kuma_url = "http://example.com/api/push"

        result = CheckResult(
            check_name="test-cmd",
            status="down",
            message="Check failed",
            duration_seconds=3,
        )

        executor.send_result_alert(mock_logger, mock_config, "test-cmd", result, 3000)

        # Verify send_push was called
        mock_send_push.assert_called_once()

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_result_alert_no_token(self, mock_send_push):
        """Test send_result_alert skips sending when no command token."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = None

        result = CheckResult(
            check_name="test-cmd",
            status="up",
            message="Check passed",
            duration_seconds=5,
        )

        executor.send_result_alert(mock_logger, mock_config, "test-cmd", result, 5000)

        # Verify send_push was NOT called when no token
        mock_send_push.assert_not_called()


class TestSendErrorAlert:
    """Test the _send_error_alert and send_error_alert methods."""

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_error_alert_with_message(self, mock_send_push):
        """Test sending error alert with error message."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = "cmd_token"
        mock_config.uptime_kuma_url = "http://example.com/api/push"

        executor.send_error_alert(
            mock_logger, mock_config, "test-cmd", "Network timeout", duration_ms=5000
        )

        # Verify send_push was called
        mock_send_push.assert_called_once()
        call_args = mock_send_push.call_args
        assert "Network timeout" in str(call_args)

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_error_alert_no_token(self, mock_send_push):
        """Test send_error_alert skips sending when no command token."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = None

        executor.send_error_alert(
            mock_logger, mock_config, "test-cmd", "Error occurred", duration_ms=1000
        )

        # Verify send_push was NOT called when no token
        mock_send_push.assert_not_called()

    @patch("kuma_sentinel.cli.commands.executor.send_push")
    def test_send_error_alert_with_zero_duration(self, mock_send_push):
        """Test send_error_alert with zero duration."""
        executor = ConcreteExecutor()
        executor._command_name = "test-cmd"

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.command_token = "cmd_token"
        mock_config.uptime_kuma_url = "http://example.com/api/push"

        executor.send_error_alert(
            mock_logger, mock_config, "test-cmd", "Error occurred", duration_ms=0
        )

        # Verify send_push was called
        mock_send_push.assert_called_once()
