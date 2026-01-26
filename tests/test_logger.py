"""Comprehensive tests for logger module."""

import logging
import logging.handlers
import sys
from unittest.mock import MagicMock, patch

from kuma_sentinel.core.logger import (
    _add_console_handler,
    _add_file_handler,
    _add_syslog_handler,
    get_logger,
    log_security_event,
    setup_default_logging,
    setup_logging,
)


class TestAddConsoleHandler:
    """Tests for _add_console_handler function."""

    def test_add_console_handler_adds_handler(self):
        """Test that console handler is added to logger."""
        logger = logging.getLogger("test_console")
        logger.handlers.clear()

        _add_console_handler(logger)

        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_add_console_handler_sets_formatter(self):
        """Test that console handler has correct formatter."""
        logger = logging.getLogger("test_console_format")
        logger.handlers.clear()

        _add_console_handler(logger)

        handler = logger.handlers[0]
        assert handler.formatter is not None
        assert "[%(asctime)s]" in handler.formatter._fmt
        assert "%(message)s" in handler.formatter._fmt

    def test_add_console_handler_uses_stdout(self):
        """Test that console handler uses stdout stream."""
        logger = logging.getLogger("test_console_stdout")
        logger.handlers.clear()

        _add_console_handler(logger)

        handler = logger.handlers[0]
        assert handler.stream == sys.stdout


class TestAddSyslogHandler:
    """Tests for _add_syslog_handler function."""

    def test_add_syslog_handler_success(self):
        """Test successful syslog handler addition."""
        logger = logging.getLogger("test_syslog")
        logger.handlers.clear()

        with patch("logging.handlers.SysLogHandler") as mock_syslog:
            mock_handler = MagicMock()
            mock_syslog.return_value = mock_handler

            _add_syslog_handler(logger, silent=True)

            # Verify syslog handler was created and added
            mock_syslog.assert_called_once()

    def test_add_syslog_handler_silent_mode_on_exception(self, capsys):
        """Test that silent=True suppresses exception output."""
        logger = logging.getLogger("test_syslog_silent")
        logger.handlers.clear()

        with patch(
            "logging.handlers.SysLogHandler", side_effect=OSError("No /dev/log")
        ):
            _add_syslog_handler(logger, silent=True)

        # In silent mode, nothing should be printed
        captured = capsys.readouterr()
        assert "Warning" not in captured.err

    def test_add_syslog_handler_non_silent_mode_on_exception(self, capsys):
        """Test that silent=False prints warning on exception."""
        logger = logging.getLogger("test_syslog_nonsilent")
        logger.handlers.clear()

        with patch(
            "logging.handlers.SysLogHandler", side_effect=OSError("No /dev/log")
        ):
            _add_syslog_handler(logger, silent=False)

        # In non-silent mode, warning should be printed
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "Could not set up syslog logging" in captured.err

    def test_add_syslog_handler_sets_formatter(self):
        """Test that syslog handler has correct formatter."""
        logger = logging.getLogger("test_syslog_format")
        logger.handlers.clear()

        with patch("logging.handlers.SysLogHandler") as mock_syslog:
            mock_handler = MagicMock()
            mock_syslog.return_value = mock_handler

            _add_syslog_handler(logger, silent=True)

            # Verify formatter was set
            mock_handler.setFormatter.assert_called_once()
            call_args = mock_handler.setFormatter.call_args[0][0]
            assert "kuma-sentinel" in call_args._fmt

    def test_add_syslog_handler_creates_with_correct_params(self):
        """Test that SysLogHandler is created with correct parameters."""
        logger = logging.getLogger("test_syslog_params")
        logger.handlers.clear()

        with patch("logging.handlers.SysLogHandler") as mock_syslog:
            mock_handler = MagicMock()
            mock_syslog.return_value = mock_handler

            _add_syslog_handler(logger, silent=True)

            # Verify SysLogHandler was called with correct args
            mock_syslog.assert_called_once_with(
                address="/dev/log",
                facility=logging.handlers.SysLogHandler.LOG_USER,
            )


class TestAddFileHandler:
    """Tests for _add_file_handler function."""

    def test_add_file_handler_creates_directory(self, tmp_path):
        """Test that file handler creates parent directories."""
        logger = logging.getLogger("test_file_dir")
        logger.handlers.clear()

        log_file = tmp_path / "logs" / "subdir" / "app.log"

        _add_file_handler(logger, str(log_file))

        assert log_file.parent.exists()
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.FileHandler)

    def test_add_file_handler_sets_formatter(self, tmp_path):
        """Test that file handler has correct formatter."""
        logger = logging.getLogger("test_file_format")
        logger.handlers.clear()

        log_file = tmp_path / "app.log"

        _add_file_handler(logger, str(log_file))

        handler = logger.handlers[0]
        assert handler.formatter is not None
        assert "[%(asctime)s]" in handler.formatter._fmt
        assert "%(message)s" in handler.formatter._fmt

    def test_add_file_handler_permission_error(self, capsys):
        """Test handling of PermissionError during file creation."""
        logger = logging.getLogger("test_file_permission")
        logger.handlers.clear()

        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")):
            _add_file_handler(logger, "/restricted/logs/app.log")

        # Should not crash and should print warning
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "Could not set up file logging" in captured.err

    def test_add_file_handler_oserror(self, capsys):
        """Test handling of OSError during file creation."""
        logger = logging.getLogger("test_file_oserror")
        logger.handlers.clear()

        with patch("pathlib.Path.mkdir", side_effect=OSError("Invalid path")):
            _add_file_handler(logger, "/invalid/path/app.log")

        # Should not crash and should print warning
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "Could not set up file logging" in captured.err

    def test_add_file_handler_writes_to_file(self, tmp_path):
        """Test that logs are actually written to the file."""
        logger = logging.getLogger("test_file_write")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)

        log_file = tmp_path / "test.log"

        _add_file_handler(logger, str(log_file))
        logger.info("Test message")

        # Check if file exists and contains the message
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content


class TestSetupDefaultLogging:
    """Tests for setup_default_logging function."""

    def setup_method(self):
        """Clean up logger before each test."""
        logger = logging.getLogger("kuma_sentinel")
        logger.handlers.clear()

    def test_setup_default_logging_returns_logger(self):
        """Test that setup_default_logging returns a logger instance."""
        logger = setup_default_logging()

        assert isinstance(logger, logging.Logger)
        assert logger.name == "kuma_sentinel"

    def test_setup_default_logging_sets_level_to_info(self):
        """Test that default logging level is set to INFO."""
        logger = setup_default_logging()

        assert logger.level == logging.INFO

    def test_setup_default_logging_adds_console_handler(self):
        """Test that console handler is added."""
        logger = setup_default_logging()

        console_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(console_handlers) > 0

    def test_setup_default_logging_clears_existing_handlers(self):
        """Test that existing handlers are cleared before adding new ones."""
        logger = logging.getLogger("kuma_sentinel")
        # Add a dummy handler
        dummy_handler = logging.NullHandler()
        logger.addHandler(dummy_handler)

        setup_default_logging()

        # The dummy handler should be gone
        assert dummy_handler not in logger.handlers

    def test_setup_default_logging_calls_syslog_silent(self):
        """Test that syslog handler is added in silent mode."""
        with patch("kuma_sentinel.core.logger._add_syslog_handler") as mock_syslog:
            setup_default_logging()

            # Verify syslog was called with silent=True
            assert mock_syslog.called
            call_args = mock_syslog.call_args[1]
            assert call_args.get("silent") is True


class TestSetupLogging:
    """Tests for setup_logging function."""

    def setup_method(self):
        """Clean up logger before each test."""
        logger = logging.getLogger("kuma_sentinel")
        logger.handlers.clear()

    def test_setup_logging_returns_logger(self, tmp_path):
        """Test that setup_logging returns a logger instance."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file))

        assert isinstance(logger, logging.Logger)
        assert logger.name == "kuma_sentinel"

    def test_setup_logging_with_info_level(self, tmp_path):
        """Test setup_logging with INFO level."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="INFO")

        assert logger.level == logging.INFO

    def test_setup_logging_with_debug_level(self, tmp_path):
        """Test setup_logging with DEBUG level."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="DEBUG")

        assert logger.level == logging.DEBUG

    def test_setup_logging_with_warning_level(self, tmp_path):
        """Test setup_logging with WARNING level."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="WARNING")

        assert logger.level == logging.WARNING

    def test_setup_logging_with_error_level(self, tmp_path):
        """Test setup_logging with ERROR level."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="ERROR")

        assert logger.level == logging.ERROR

    def test_setup_logging_with_critical_level(self, tmp_path):
        """Test setup_logging with CRITICAL level."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="CRITICAL")

        assert logger.level == logging.CRITICAL

    def test_setup_logging_with_lowercase_level(self, tmp_path):
        """Test setup_logging with lowercase level string."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="debug")

        assert logger.level == logging.DEBUG

    def test_setup_logging_with_invalid_level(self, tmp_path):
        """Test setup_logging with invalid level defaults to INFO."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="INVALID")

        assert logger.level == logging.INFO

    def test_setup_logging_adds_file_handler(self, tmp_path):
        """Test that file handler is added."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file))

        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) > 0

    def test_setup_logging_adds_console_handler(self, tmp_path):
        """Test that console handler is added."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file))

        console_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(console_handlers) > 0

    def test_setup_logging_clears_existing_handlers(self, tmp_path):
        """Test that existing handlers are cleared."""
        log_file = tmp_path / "app.log"
        logger = logging.getLogger("kuma_sentinel")

        # Add a dummy handler
        dummy_handler = logging.NullHandler()
        logger.addHandler(dummy_handler)

        setup_logging(str(log_file))

        # The dummy handler should be gone
        assert dummy_handler not in logger.handlers

    def test_setup_logging_calls_syslog_non_silent(self, tmp_path):
        """Test that syslog handler is added in non-silent mode."""
        log_file = tmp_path / "app.log"

        with patch("kuma_sentinel.core.logger._add_syslog_handler") as mock_syslog:
            setup_logging(str(log_file))

            # Verify syslog was called with silent=False
            assert mock_syslog.called
            call_args = mock_syslog.call_args[1]
            assert call_args.get("silent") is False

    def test_setup_logging_writes_to_file(self, tmp_path):
        """Test that setup_logging actually writes to the specified file."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(str(log_file), log_level="INFO")

        logger.info("Test message from setup_logging")

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message from setup_logging" in content


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_kuma_sentinel_logger(self):
        """Test that get_logger returns the kuma_sentinel logger."""
        logger = get_logger()

        assert isinstance(logger, logging.Logger)
        assert logger.name == "kuma_sentinel"

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns the same logger instance on multiple calls."""
        logger1 = get_logger()
        logger2 = get_logger()

        assert logger1 is logger2

    def test_get_logger_after_setup_logging(self, tmp_path):
        """Test that get_logger returns the configured logger."""
        log_file = tmp_path / "app.log"
        setup_logger = setup_logging(str(log_file))
        get_instance = get_logger()

        assert get_instance is setup_logger


class TestLogSecurityEvent:
    """Tests for log_security_event function."""

    def test_log_security_event_default_level_warning(self, caplog):
        """Test that security events are logged at WARNING level by default."""
        logger = logging.getLogger("test_security")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "test details")

        assert "[SECURITY-EVENT]" in caplog.text
        assert "test_event" in caplog.text
        assert "test details" in caplog.text

    def test_log_security_event_with_info_level(self, caplog):
        """Test logging security event with INFO level."""
        logger = logging.getLogger("test_security_info")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "test details", level="info")

        assert "[SECURITY-EVENT]" in caplog.text
        assert "test_event: test details" in caplog.text

    def test_log_security_event_with_warning_level(self, caplog):
        """Test logging security event with WARNING level."""
        logger = logging.getLogger("test_security_warning")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "test details", level="warning")

        assert "[SECURITY-EVENT]" in caplog.text
        assert "test_event: test details" in caplog.text

    def test_log_security_event_with_error_level(self, caplog):
        """Test logging security event with ERROR level."""
        logger = logging.getLogger("test_security_error")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "test details", level="error")

        assert "[SECURITY-EVENT]" in caplog.text
        assert "test_event: test details" in caplog.text

    def test_log_security_event_prefix_format(self, caplog):
        """Test that security event message has correct format."""
        logger = logging.getLogger("test_security_format")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "dangerous_command_detected", "rm -rf /")

        expected_message = "[SECURITY-EVENT] dangerous_command_detected: rm -rf /"
        assert expected_message in caplog.text

    def test_log_security_event_case_insensitive_level(self, caplog):
        """Test that level parameter is case insensitive."""
        logger = logging.getLogger("test_security_case")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "details", level="ERROR")

        assert "[SECURITY-EVENT]" in caplog.text

    def test_log_security_event_invalid_level_defaults_to_warning(self, caplog):
        """Test that invalid level defaults to warning."""
        logger = logging.getLogger("test_security_invalid")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "test_event", "details", level="INVALID")

        assert "[SECURITY-EVENT]" in caplog.text

    def test_log_security_event_with_mock_logger(self):
        """Test security event logging with mocked logger."""
        mock_logger = MagicMock(spec=logging.Logger)

        log_security_event(mock_logger, "permission_bypass", "config ignored")

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        assert "[SECURITY-EVENT]" in call_args
        assert "permission_bypass" in call_args

    def test_log_security_event_error_calls_logger_error(self):
        """Test that ERROR level calls logger.error()."""
        mock_logger = MagicMock(spec=logging.Logger)

        log_security_event(mock_logger, "critical_event", "details", level="error")

        mock_logger.error.assert_called_once()

    def test_log_security_event_info_calls_logger_info(self):
        """Test that INFO level calls logger.info()."""
        mock_logger = MagicMock(spec=logging.Logger)

        log_security_event(mock_logger, "info_event", "details", level="info")

        mock_logger.info.assert_called_once()

    def test_log_security_event_warning_calls_logger_warning(self):
        """Test that WARNING level calls logger.warning()."""
        mock_logger = MagicMock(spec=logging.Logger)

        log_security_event(mock_logger, "warning_event", "details", level="warning")

        mock_logger.warning.assert_called_once()

    def test_log_security_event_with_special_characters(self, caplog):
        """Test that special characters in event details are preserved."""
        logger = logging.getLogger("test_security_special")
        logger.setLevel(logging.DEBUG)

        special_details = "Command: rm -rf / && echo 'danger'"
        log_security_event(logger, "dangerous_cmd", special_details)

        assert special_details in caplog.text

    def test_log_security_event_multiple_calls(self, caplog):
        """Test that multiple security events are logged correctly."""
        logger = logging.getLogger("test_security_multi")
        logger.setLevel(logging.DEBUG)

        log_security_event(logger, "event1", "details1")
        log_security_event(logger, "event2", "details2", level="error")
        log_security_event(logger, "event3", "details3", level="info")

        assert "event1" in caplog.text
        assert "event2" in caplog.text
        assert "event3" in caplog.text
        assert caplog.text.count("[SECURITY-EVENT]") == 3


class TestLoggerIntegration:
    """Integration tests for logger module."""

    def setup_method(self):
        """Clean up logger before each test."""
        logger = logging.getLogger("kuma_sentinel")
        logger.handlers.clear()

    def test_setup_default_then_setup_logging(self, tmp_path):
        """Test transitioning from default logging to full logging setup."""
        log_file = tmp_path / "app.log"

        # Start with default logging
        logger1 = setup_default_logging()

        # Switch to full logging
        logger2 = setup_logging(str(log_file), log_level="DEBUG")

        # Should be the same logger instance
        assert logger1 is logger2

        # Handler count should have changed due to clearing and re-adding
        # At minimum, should have file and console handlers
        assert len(logger2.handlers) >= 2

    def test_logger_outputs_to_multiple_destinations(self, tmp_path, capsys):
        """Test that logger outputs to both file and console."""
        log_file = tmp_path / "app.log"
        logger = setup_logging(str(log_file), log_level="INFO")

        test_message = "Integration test message"
        logger.info(test_message)

        # Check file output
        assert log_file.exists()
        file_content = log_file.read_text()
        assert test_message in file_content

        # Check console output
        captured = capsys.readouterr()
        assert test_message in captured.out

    def test_security_event_with_configured_logger(self, tmp_path, caplog):
        """Test security event logging with fully configured logger."""
        log_file = tmp_path / "security.log"
        logger = setup_logging(str(log_file), log_level="DEBUG")

        log_security_event(logger, "unauthorized_access", "User X attempted command Y")

        # Check that security event is in the log output
        assert "[SECURITY-EVENT]" in caplog.text
        assert "unauthorized_access" in caplog.text

        # Check that it's also in the file
        file_content = log_file.read_text()
        assert "[SECURITY-EVENT]" in file_content
