"""Uptime Kuma API integration."""

import urllib.error
import urllib.parse
import urllib.request
from logging import Logger
from typing import Optional

# Timeout constants for different push types
PUSH_TIMEOUT_HEARTBEAT = 5
PUSH_TIMEOUT_ALERT = 10


def url_encode(msg: str) -> str:
    """URL encode a message for safe transmission."""
    return urllib.parse.quote(msg)


def send_push(
    logger: Logger,
    uptime_kuma_url: Optional[str],
    push_token: Optional[str],
    message: str,
    command: str,
    status: str = "up",
    timeout: int = PUSH_TIMEOUT_HEARTBEAT,
    ping_ms: Optional[int] = None,
) -> bool:
    """Send a generic push notification to Uptime Kuma.

    Args:
        logger: Logger instance
        uptime_kuma_url: Base URL for Uptime Kuma API
        push_token: Push token for the monitor
        message: Notification message
        command: Command/check name (e.g., "portscan", "kopiasnapshotstatus")
        status: Status to report (default: "up")
        timeout: Request timeout in seconds
        ping_ms: Response time in milliseconds (optional, for command-specific alerts)

    Returns:
        True if successful, False otherwise
    """
    # Validate required parameters
    if not uptime_kuma_url:
        logger.warning(
            f"⚠️  Cannot send {command} push: Uptime Kuma URL not configured"
        )
        return False

    if not push_token:
        logger.warning(f"⚠️  Cannot send {command} push: push token not configured")
        return False

    try:
        encoded_msg = url_encode(message)
        push_url = f"{uptime_kuma_url}/{push_token}?status={status}&msg={encoded_msg}"

        # Append ping parameter if provided (for command-specific result alerts)
        if ping_ms is not None:
            push_url += f"&ping={ping_ms}"

        with urllib.request.urlopen(push_url, timeout=timeout) as response:
            data = response.read().decode()
            if '{"ok":true}' in data:
                logger.info(f"✅ {command} push sent ({status}): {message}")
                return True
            else:
                logger.error(f"❌ {command} push failed: {data}")
                return False
    except Exception as e:
        logger.error(f"❌ {command} push failed: {str(e)}")
        return False
