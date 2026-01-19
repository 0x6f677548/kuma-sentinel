"""Heartbeat service for monitoring agent health."""

import threading
import time
from typing import Optional

from kuma_sentinel.core.uptime_kuma import send_push


class HeartbeatService:
    """Manages periodic heartbeat pings to Uptime Kuma during check execution.
    Provides a reusable service for any monitoring check to signal agent health
    without needing to manage threading internally.
    """

    def __init__(
        self,
        logger,
        uptime_kuma_url: str,
        heartbeat_token: str,
        interval: int = 300,
        check_name: str = "Agent",
    ):
        """Initialize heartbeat service.
        Args:
            logger: Logger instance for heartbeat status messages
            uptime_kuma_url: Base URL for Uptime Kuma API
            heartbeat_token: Push token for heartbeat monitor
            interval: Seconds between heartbeat pings (default: 300)
            check_name: Name of the check being run (e.g., "PortScan")
        """
        self.logger = logger
        self.uptime_kuma_url = uptime_kuma_url
        self.heartbeat_token = heartbeat_token
        self.interval = interval
        self.check_name = check_name
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the heartbeat thread.
        Creates and starts a daemon thread that sends periodic pings
        until stop() is called. Does nothing if interval <= 0.
        """
        if self.interval <= 0:
            return

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._ping_loop,
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        """Stop the heartbeat thread and wait for it to finish.
        Signals the heartbeat thread to stop and waits up to 5 seconds
        for graceful shutdown.
        """
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def send_message(self, message: str) -> bool:
        """Send an immediate heartbeat with a custom message.
        Args:
            message: Status message to include in the heartbeat ping
        Returns:
            True if ping was successful, False otherwise
        """
        return send_push(
            self.logger,
            self.uptime_kuma_url,
            self.heartbeat_token,
            message,
            command="heartbeat",
        )

    def _ping_loop(self) -> None:
        """Background thread loop for periodic heartbeat pings.
        Sends initial ping immediately, then continues at configured intervals.
        Repeats until stop_event is set.
        """
        while not self.stop_event.is_set():
            time.sleep(self.interval)
            if not self.stop_event.is_set():
                self.send_message(f"{self.check_name} check in progress...")
