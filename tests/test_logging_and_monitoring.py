"""Tests for logging enhancements (Issue #7)."""

import logging
from unittest.mock import MagicMock

import pytest

from kuma_sentinel.core.checkers.base import Checker
from kuma_sentinel.core.config.base import ConfigBase
from kuma_sentinel.core.models import CheckResult


class SimpleTestConfig(ConfigBase):
    """Simple test config class for testing base functionality."""

    def get_summary(self, mask_tokens: bool = True) -> dict:
        """Get configuration summary."""
        return {
            "uptime_kuma_url": self._mask_token(self.uptime_kuma_url, mask_tokens),
            "heartbeat_token": self._mask_token(self.heartbeat_token, mask_tokens),
            "command_token": self._mask_token(self.command_token, mask_tokens),
        }


class MockChecker(Checker):
    """Mock checker for testing."""

    name = "test"
    description = "Test checker"

    def execute(self) -> CheckResult:
        """Return a mock result."""
        return CheckResult(
            check_name="test",
            status="up",
            message="Test passed",
            duration_seconds=0,
            details={},
        )


class TestConfigBaseLogging:
    """Tests for ConfigBase logging enhancements."""

    def test_validate_logs_url_not_provided(self):
        """Test that URL validation failure is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure tokens to pass
        config.heartbeat_token = "test_token"
        config.command_token = "test_token"

        # Leave URL empty to trigger error
        config.uptime_kuma_url = None

        with pytest.raises(ValueError):
            config.validate()

        # Verify warning was logged
        logger.warning.assert_called_with("⚠️  Uptime Kuma URL not provided")

    def test_validate_logs_invalid_url(self):
        """Test that invalid URL is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure tokens to pass
        config.heartbeat_token = "test_token"
        config.command_token = "test_token"

        # Set invalid URL
        config.uptime_kuma_url = "invalid_url"

        with pytest.raises(ValueError):
            config.validate()

        # Verify error was logged
        assert any(
            "Invalid Uptime Kuma URL" in str(call)
            for call in logger.error.call_args_list
        )

    def test_validate_logs_url_success(self):
        """Test that valid URL validation is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure valid values
        config.uptime_kuma_url = "http://example.com"
        config.heartbeat_token = "test_token"
        config.command_token = "test_token"

        config.validate()

        # Verify debug log was called for URL success
        logger.debug.assert_any_call("✅ Uptime Kuma URL validation passed")

    def test_validate_logs_missing_heartbeat_token(self):
        """Test that missing heartbeat token is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure URL to pass
        config.uptime_kuma_url = "http://example.com"

        # Leave heartbeat token empty
        config.heartbeat_token = None
        config.command_token = "test_token"

        with pytest.raises(ValueError):
            config.validate()

        # Verify warning was logged
        logger.warning.assert_called_with("⚠️  Heartbeat push token not provided")

    def test_validate_logs_missing_command_token(self):
        """Test that missing command token is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure URL to pass
        config.uptime_kuma_url = "http://example.com"
        config.heartbeat_token = "test_token"

        # Leave command token empty
        config.command_token = None

        with pytest.raises(ValueError):
            config.validate()

        # Verify warning was logged
        logger.warning.assert_called_with("⚠️  Command push token not provided")

    def test_validate_logs_all_errors(self):
        """Test that all validation errors are logged with error count."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Configure no valid values
        config.uptime_kuma_url = None
        config.heartbeat_token = None
        config.command_token = None

        with pytest.raises(ValueError):
            config.validate()

        # Verify error log was called with count
        error_calls = logger.error.call_args_list
        assert len(error_calls) >= 1
        call_args_str = str(error_calls)
        assert "3 error(s)" in call_args_str

    def test_load_from_yaml_logs_debug_messages(self):
        """Test that YAML loading logs debug messages."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Create a minimal YAML file for testing
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
logging:
  log_file: /var/log/test.log
  log_level: DEBUG
""")
            f.flush()

            try:
                config.load_from_yaml(f.name)

                # Verify debug logs were called
                assert any(
                    "Loading YAML" in str(call) for call in logger.debug.call_args_list
                )
                assert any(
                    "Successfully parsed" in str(call)
                    for call in logger.debug.call_args_list
                )
            finally:
                os.unlink(f.name)

    def test_load_from_yaml_logs_file_not_found(self):
        """Test that file not found error is logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        with pytest.raises(FileNotFoundError):
            config.load_from_yaml("/nonexistent/file.yaml")

        # Verify error was logged
        logger.error.assert_called_once()
        assert "Configuration file not found" in str(logger.error.call_args)

    def test_load_from_env_logs_loaded_variables(self):
        """Test that loaded environment variables are logged."""
        config = SimpleTestConfig()
        logger = MagicMock(spec=logging.Logger)
        config.logger = logger

        # Set an environment variable
        import os

        os.environ["KUMA_SENTINEL_HEARTBEAT_TOKEN"] = "test_env_token"
        try:
            config.load_from_env()

            # Verify debug log was called
            logger.debug.assert_called()
            call_args = str(logger.debug.call_args_list)
            assert "environment variables" in call_args
        finally:
            del os.environ["KUMA_SENTINEL_HEARTBEAT_TOKEN"]


class TestCheckerHeartbeatLogging:
    """Tests for Checker heartbeat initialization logging."""

    def test_heartbeat_disabled_logged(self):
        """Test that disabled heartbeat is logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = False
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://example.com"

        MockChecker(logger, config)

        # Verify debug log was called for disabled heartbeat
        logger.debug.assert_called()
        assert any(
            "disabled" in str(call).lower() for call in logger.debug.call_args_list
        )

    def test_heartbeat_missing_token_logged(self):
        """Test that missing heartbeat token is logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = True
        config.heartbeat_token = None  # Missing token
        config.uptime_kuma_url = "http://example.com"

        MockChecker(logger, config)

        # Verify warning was logged
        logger.warning.assert_called()
        assert any(
            "token missing" in str(call).lower()
            for call in logger.warning.call_args_list
        )

    def test_heartbeat_missing_url_logged(self):
        """Test that missing Uptime Kuma URL is logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = None  # Missing URL

        MockChecker(logger, config)

        # Verify warning was logged
        logger.warning.assert_called()
        # Get the calls and check if any contain "URL"
        warning_calls = str(logger.warning.call_args_list)
        assert "missing" in warning_calls.lower()

    def test_heartbeat_initialized_logged(self):
        """Test that successful heartbeat initialization is logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = True
        config.heartbeat_token = "token"
        config.uptime_kuma_url = "http://example.com"
        config.heartbeat_interval = 300

        MockChecker(logger, config)

        # Verify debug log was called for successful initialization
        logger.debug.assert_called()
        assert any(
            "initialized" in str(call).lower() and "heartbeat" in str(call).lower()
            for call in logger.debug.call_args_list
        )


class TestCheckerExecutionLogging:
    """Tests for Checker execution logging."""

    def test_execute_with_heartbeat_logs_execution_messages(self):
        """Test that execution is logged with start/completion messages."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = False

        checker = MockChecker(logger, config)
        result = checker.execute_with_heartbeat()

        # Verify execution logs
        logger.info.assert_called()
        assert any(
            "completed" in str(call).lower() and "check" in str(call).lower()
            for call in logger.info.call_args_list
        )
        assert result.status == "up"

    def test_execute_logs_timeout_error(self):
        """Test that timeout errors are logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = False

        # Create a checker that raises TimeoutError
        class TimeoutChecker(Checker):
            name = "timeout_test"
            description = "Test timeout"

            def execute(self) -> CheckResult:
                raise TimeoutError("Operation timed out")

        checker = TimeoutChecker(logger, config)

        with pytest.raises(TimeoutError):
            checker.execute_with_heartbeat()

        # Verify timeout error was logged
        logger.error.assert_called()
        assert any(
            "timed out" in str(call).lower() for call in logger.error.call_args_list
        )

    def test_execute_logs_unexpected_error(self):
        """Test that unexpected errors are logged."""
        logger = MagicMock(spec=logging.Logger)
        config = SimpleTestConfig()
        config.logger = MagicMock()
        config.heartbeat_enabled = False

        # Create a checker that raises an unexpected error
        class FailChecker(Checker):
            name = "fail_test"
            description = "Test failure"

            def execute(self) -> CheckResult:
                raise RuntimeError("Unexpected error")

        checker = FailChecker(logger, config)

        with pytest.raises(RuntimeError):
            checker.execute_with_heartbeat()

        # Verify error was logged
        logger.error.assert_called()
        assert any(
            "unexpected error" in str(call).lower()
            for call in logger.error.call_args_list
        )


class TestLoggingIntegration:
    """Integration tests for logging across config and checker."""

    def test_full_logging_flow_success(self):
        """Test full logging flow for successful execution."""
        # Create a real logger that captures output
        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

        logger = logging.getLogger("test_logger_success")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)

        # Create config with logger
        config = SimpleTestConfig(logger=logger)
        config.uptime_kuma_url = "http://example.com"
        config.heartbeat_token = "token"
        config.command_token = "token"

        # Validate should log success
        config.validate()

        log_output = log_stream.getvalue()
        assert "URL validation passed" in log_output
        assert "token configured" in log_output

    def test_full_logging_flow_failure(self):
        """Test full logging flow for validation failure."""
        # Create a real logger that captures output
        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

        logger = logging.getLogger("test_logger_failure")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)

        # Create config with logger
        config = SimpleTestConfig(logger=logger)
        config.uptime_kuma_url = None
        config.heartbeat_token = None
        config.command_token = None

        # Validate should log all errors
        with pytest.raises(ValueError):
            config.validate()

        log_output = log_stream.getvalue()
        assert "URL not provided" in log_output
        assert "token not provided" in log_output
        assert "3 error(s)" in log_output
