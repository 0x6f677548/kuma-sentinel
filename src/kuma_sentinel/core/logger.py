"""Logging configuration for kuma sentinel."""

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_file):
    """Configure logging with file, stdout, and journalctl.

    Args:
        log_file: Path to log file
    """
    logger = logging.getLogger("kuma_sentinel")
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    log_format = "[%(asctime)s] %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"

    # File handler
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_date_format))
    logger.addHandler(file_handler)

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
    except Exception:
        # Syslog not available on all systems (e.g., Windows)
        pass

    return logger


def get_logger():
    """Get the logger instance."""
    return logging.getLogger("kuma_sentinel")
