"""Logging configuration for kuma sentinel."""

import logging
import logging.handlers
import sys
from pathlib import Path


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

    log_format = "[%(asctime)s] %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"

    # File handler
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_date_format))
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # Fallback to console if file logging is not possible
        print(f"\033[93mWarning: Could not set up file logging to {log_file}: {e}\033[0m", file=sys.stderr)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=log_date_format))
    logger.addHandler(console_handler)

    # Syslog/journalctl handler
    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address="/dev/log", facility=logging.handlers.SysLogHandler.LOG_USER
        )
        syslog_format = logging.Formatter("kuma-sentinel[%(process)d]: %(message)s")
        syslog_handler.setFormatter(syslog_format)
        logger.addHandler(syslog_handler)
    except Exception as e:
        # Syslog not available on all systems (e.g., Windows)
        # Fallback to console if syslog logging is not possible
        print(f"\033[93mWarning: Could not set up syslog logging: {e}. This is expected on non-Unix systems.\033[0m", file=sys.stderr)

    return logger


def get_logger():
    """Get the logger instance."""
    return logging.getLogger("kuma_sentinel")
