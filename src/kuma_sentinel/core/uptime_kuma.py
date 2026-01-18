"""Uptime Kuma API integration."""

import urllib.error
import urllib.parse
import urllib.request
from logging import Logger


def url_encode(msg: str) -> str:
    """URL encode a message for safe transmission."""
    return urllib.parse.quote(msg)


def send_heartbeat(
    logger: Logger, uptime_kuma_url: str, push_token: str, message: str
) -> bool:
    """Send heartbeat ping to Uptime Kuma.

    Args:
        logger: Logger instance
        uptime_kuma_url: Base URL for Uptime Kuma API
        push_token: Push token for heartbeat monitor
        message: Heartbeat message

    Returns:
        True if successful, False otherwise
    """
    try:
        encoded_msg = url_encode(message)
        push_url = f"{uptime_kuma_url}/{push_token}?status=up&msg={encoded_msg}"

        with urllib.request.urlopen(push_url, timeout=5) as response:
            data = response.read().decode()
            if '{"ok":true}' in data:
                logger.info(f"✅ Heartbeat sent: {message}")
                return True
            else:
                logger.warning(f"⚠️  Heartbeat failed to send: {data}")
                return False
    except Exception as e:
        logger.warning(f"⚠️  Heartbeat failed to send: {str(e)}")
        return False


# Backward compatibility alias
send_keepalive = send_heartbeat


def send_port_alert(
    logger: Logger, uptime_kuma_url: str, push_token: str, status: str, message: str
) -> bool:
    """Send port scan alert to Uptime Kuma.

    Args:
        logger: Logger instance
        uptime_kuma_url: Base URL for Uptime Kuma API
        push_token: Push token for port-scan alert monitor
        status: Status to report (up/down)
        message: Alert message

    Returns:
        True if successful, False otherwise
    """
    try:
        encoded_msg = url_encode(message)
        push_url = f"{uptime_kuma_url}/{push_token}?status={status}&msg={encoded_msg}"

        with urllib.request.urlopen(push_url, timeout=10) as response:
            data = response.read().decode()
            if '{"ok":true}' in data:
                logger.info(f"✅ Port alert sent ({status}): {message}")
                return True
            else:
                logger.error(f"❌ Port alert failed: {data}")
                return False
    except Exception as e:
        logger.error(f"❌ Port alert failed: {str(e)}")
        return False
