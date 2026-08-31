"""Tests for quiet and verbose functionality."""

import logging
from unittest.mock import Mock, patch

from rich.console import Console

from kuma_scout.cli.config_merger import ConfigMerger
from kuma_scout.core.logger import setup_logging
from kuma_scout.core.output_handler import OutputHandler
from kuma_scout.plugins.models import GlobalConfig


class TestOutputHandlerQuiet:
    """Test OutputHandler quiet mode."""

    def test_output_handler_quiet_false_echoes_output(self):
        """Test that quiet=False allows console output."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=False)

        handler.info("test message", echo=True)
        mock_console.print.assert_called_once_with("test message")

    def test_output_handler_quiet_true_suppresses_output(self):
        """Test that quiet=True suppresses console output."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)

        handler.info("test message", echo=True)
        mock_console.print.assert_not_called()

    def test_output_handler_quiet_debug_suppressed(self):
        """Test that debug messages are suppressed in quiet mode."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)

        handler.debug("debug message", echo=True)
        mock_console.print.assert_not_called()

    def test_output_handler_quiet_warning_suppressed(self):
        """Test that warning messages are suppressed in quiet mode."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)

        handler.warning("warning message", echo=True)
        mock_console.print.assert_not_called()

    def test_output_handler_quiet_error_suppressed(self):
        """Test that error messages are suppressed in quiet mode."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)

        handler.error("error message", echo=True)
        mock_console.print.assert_not_called()

    def test_output_handler_quiet_table_suppressed(self):
        """Test that table output is suppressed in quiet mode."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)
        mock_table = Mock()

        handler.print_table(mock_table, echo=True)
        mock_console.print.assert_not_called()

    def test_output_handler_quiet_logging_still_works(self):
        """Test that logging still works when quiet mode is enabled."""
        mock_console = Mock(spec=Console)
        handler = OutputHandler(console=mock_console, quiet=True)

        with patch.object(handler.logger, "info") as mock_logger:
            handler.info("test message", echo=True)
            mock_logger.assert_called_once()


class TestConfigMergerQuietVerbose:
    """Test ConfigMerger handling of quiet and verbose options."""

    def test_apply_cli_to_global_config_quiet(self):
        """Test that quiet flag is applied correctly."""
        config = GlobalConfig()
        assert config.quiet is False

        ConfigMerger.apply_cli_to_global_config(
            config,
            uptime_kuma_url=None,
            token=None,
            heartbeat_token=None,
            timeout=300,
            log_file=None,
            log_level=None,
            quiet=True,
            verbose=False,
        )

        assert config.quiet is True
        assert config.verbose is False

    def test_apply_cli_to_global_config_verbose(self):
        """Test that verbose flag is applied correctly."""
        config = GlobalConfig()
        assert config.verbose is False
        assert config.logging.level == "INFO"

        ConfigMerger.apply_cli_to_global_config(
            config,
            uptime_kuma_url=None,
            token=None,
            heartbeat_token=None,
            timeout=300,
            log_file=None,
            log_level=None,
            quiet=False,
            verbose=True,
        )

        assert config.verbose is True
        assert config.quiet is False
        # Verbose should set log level to DEBUG
        assert config.logging.level == "DEBUG"

    def test_apply_cli_to_global_config_verbose_respects_explicit_log_level(self):
        """Test that verbose doesn't override explicit log level."""
        config = GlobalConfig()

        ConfigMerger.apply_cli_to_global_config(
            config,
            uptime_kuma_url=None,
            token=None,
            heartbeat_token=None,
            timeout=300,
            log_file=None,
            log_level="WARNING",
            quiet=False,
            verbose=True,
        )

        assert config.verbose is True
        # Explicit log level should be preserved
        assert config.logging.level == "WARNING"


class TestSetupLoggingVerbose:
    """Test setup_logging with verbose mode."""

    def test_setup_logging_verbose_true_adds_console_handler(self):
        """Test that verbose=True adds a console handler."""
        logger = logging.getLogger("test_verbose_logger")
        logger.handlers.clear()

        # Setup logging with verbose=True
        setup_logging(log_file=None, log_level="DEBUG", verbose=True)

        # Check that logger has handlers
        assert len(logging.getLogger("kuma_scout").handlers) > 0

        # Check if console handler is in the handlers
        console_handlers = [
            h
            for h in logging.getLogger("kuma_scout").handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.handlers.SysLogHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_handlers) > 0

    def test_setup_logging_verbose_false_no_console_handler(self):
        """Test that verbose=False doesn't add extra console handler."""
        logger = logging.getLogger("kuma_scout")
        logger.handlers.clear()

        setup_logging(log_file=None, log_level="INFO", verbose=False)

        # With verbose=False, no stdout/console handler should be added
        # (only syslog and file if configured)
        console_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.handlers.SysLogHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        # Should be 0 unless syslog/file streams to stdout
        assert len(console_handlers) == 0
