"""Logging configuration for kuma sentinel."""

import logging
import logging.handlers
import sys
from pathlib import Path

# Log format constants
_LOG_FORMAT = "[%(asctime)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_SYSLOG_FORMAT = "kuma-sentinel[%(process)d]: %(message)s"


def _add_console_handler(logger: logging.Logger) -> None:
    """Add console handler to logger with standard format."""
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
    )
    logger.addHandler(console_handler)


def _add_syslog_handler(logger: logging.Logger, silent: bool = True) -> None:
    """Add syslog/journalctl handler to logger.

    Args:
        logger: Logger instance to add handler to
        silent: If True, silently continue if syslog is unavailable.
                If False, print warning message.
    """
    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address="/dev/log", facility=logging.handlers.SysLogHandler.LOG_USER
        )
        syslog_handler.setFormatter(logging.Formatter(_SYSLOG_FORMAT))
        logger.addHandler(syslog_handler)
    except Exception as e:
        # Syslog not available on all systems (e.g., Windows)
        if not silent:
            print(
                f"\033[93mWarning: Could not set up syslog logging: {e}. This is expected on non-Unix systems.\033[0m",
                file=sys.stderr,
            )


def _add_file_handler(logger: logging.Logger, log_file: str) -> None:
    """Add file handler to logger with standard format.

    Args:
        logger: Logger instance to add handler to
        log_file: Path to log file
    """
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
        )
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # Fallback to console if file logging is not possible
        print(
            f"\033[93mWarning: Could not set up file logging to {log_file}: {e}\033[0m",
            file=sys.stderr,
        )


def setup_default_logging():
    """Configure default logging with console and journalctl handlers.

    This sets up basic logging when the application starts, before config is loaded.
    Uses INFO level by default to provide visibility during initialization.
    Later, setup_logging() will be called with config values to upgrade the configuration.
    """
    logger = logging.getLogger("kuma_sentinel")
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add handlers
    _add_console_handler(logger)
    _add_syslog_handler(logger, silent=True)

    return logger


def setup_logging(log_file, log_level="INFO"):
    """Configure logging with file, stdout, and journalctl.

    Args:
        log_file: Path to log file
        log_level: Logging level as string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger = logging.getLogger("kuma_sentinel")
    # Convert string log level to logging constant
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add handlers
    _add_file_handler(logger, log_file)
    _add_console_handler(logger)
    _add_syslog_handler(logger, silent=False)

    return logger


def get_logger():
    """Get the logger instance."""
    return logging.getLogger("kuma_sentinel")


def log_security_event(
    logger: logging.Logger, event_type: str, details: str, level: str = "warning"
) -> None:
    """Log a security-relevant event with consistent formatting.

    Security events are logged with a [SECURITY-EVENT] prefix to make them
    easy to identify and filter in logs. This maintains the existing logger
    infrastructure while providing clear visibility of security-critical events.

    Args:
        logger: Logger instance to use
        event_type: Type of security event (e.g., "dangerous_command_detected",
                   "permission_bypass", "token_validation_failed")
        details: Description of the event with relevant context
        level: Log level as string ("warning", "error", "info"). Default: "warning"

    Examples:
        log_security_event(logger, "dangerous_command_detected",
                          "Command 'rm -rf' matches dangerous pattern")
        log_security_event(logger, "permission_bypass",
                          "Config file permissions ignored via flag", level="error")
    """
    prefix = "[SECURITY-EVENT]"
    message = f"{prefix} {event_type}: {details}"

    log_level = level.upper()
    if log_level == "ERROR":
        logger.error(message)
    elif log_level == "INFO":
        logger.info(message)
    else:  # default to warning
        logger.warning(message)
