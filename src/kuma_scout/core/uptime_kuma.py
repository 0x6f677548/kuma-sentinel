"""Uptime Kuma API integration."""

import urllib.parse
import urllib.request
from typing import Optional

from kuma_scout.core.logger import log_security_event
from kuma_scout.core.output_handler import OutputHandler

# Timeout constants for different push types
PUSH_TIMEOUT_HEARTBEAT = 5


def url_encode(msg: str) -> str:
    """URL encode a message for safe transmission."""
    return urllib.parse.quote(msg)


def send_push(
    uptime_kuma_url: Optional[str],
    push_token: Optional[str],
    message: str,
    command: str,
    status: str = "up",
    timeout: int = PUSH_TIMEOUT_HEARTBEAT,
    ping_ms: Optional[int] = None,
    output_handler: Optional[OutputHandler] = None,
) -> bool:
    """Send a generic push notification to Uptime Kuma.

    Args:
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
    if output_handler is None:
        output_handler = OutputHandler()

    # Validate required parameters
    if not uptime_kuma_url:
        output_handler.warning(
            f"Cannot send {command} push: Uptime Kuma URL not configured", echo=True
        )
        return False

    if not push_token:
        log_security_event(
            "uptime_kuma_token_missing",
            f"Push token not configured for {command} - cannot send status updates to Uptime Kuma",
            level="warning",
        )
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
                output_handler.info(
                    f"{command} push sent ({status}): {message}", echo=False
                )
                return True
            else:
                # Check for authentication errors
                if (
                    "unauthorized" in data.lower()
                    or "forbidden" in data.lower()
                    or "invalid token" in data.lower()
                ):
                    log_security_event(
                        "uptime_kuma_authentication_failed",
                        f"Uptime Kuma API authentication failed for {command} - check push token validity",
                        level="error",
                    )
                output_handler.error(f"{command} push failed: {data}", echo=True)
                return False
    except Exception as e:
        output_handler.warning(f"{command} push failed: {str(e)}", echo=True)
        return False
