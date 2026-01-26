"""Abstract base class for sentinel checks."""

from abc import ABC, abstractmethod
from logging import Logger
from typing import Optional

from kuma_sentinel.core.config.base import ConfigBase
from kuma_sentinel.core.heartbeat import HeartbeatService
from kuma_sentinel.core.models import CheckResult


class Checker(ABC):
    """Base class for all sentinel checks.

    Subclasses must implement the execute() method to perform the check
    and return a CheckResult. Heartbeat support is built-in and can be
    enabled via configuration for any check.
    """

    name: str = ""  # e.g., "portscan"
    description: str = ""  # e.g., "Scans TCP ports on target ranges"

    def __init__(self, logger: Logger, config: ConfigBase):
        """Initialize the checker.

        Args:
            logger: Logger instance for output
            config: Configuration object for this check
        """
        if not self.name:
            raise ValueError(f"Checker {self.__class__.__name__} must define 'name'")
        if not self.description:
            raise ValueError(
                f"Checker {self.__class__.__name__} must define 'description'"
            )
        self.logger = logger
        self.config = config
        self.heartbeat: Optional[HeartbeatService] = None
        self._initialize_heartbeat()

    def _initialize_heartbeat(self) -> None:
        """Initialize heartbeat service if enabled in config.

        Logs the status of heartbeat initialization including any missing
        configuration that would prevent heartbeat from running.
        """
        heartbeat_enabled = self.config.heartbeat_enabled
        heartbeat_token = self.config.heartbeat_token
        uptime_kuma_url = self.config.uptime_kuma_url
        heartbeat_interval = self.config.heartbeat_interval

        # Convert string "True"/"False" to boolean if needed
        if isinstance(heartbeat_enabled, str):
            heartbeat_enabled = heartbeat_enabled.lower() == "true"

        # Log heartbeat status
        if not heartbeat_enabled:
            self.logger.debug(
                f"ℹ️  Heartbeat disabled for {self.name} (heartbeat.enabled=false)"
            )
            return

        if not heartbeat_token:
            self.logger.warning(
                f"⚠️  Heartbeat enabled but token missing for {self.name} - "
                f"check will run without heartbeat notifications"
            )
            return

        if not uptime_kuma_url:
            self.logger.warning(
                f"⚠️  Heartbeat enabled but Uptime Kuma URL missing for {self.name} - "
                f"check will run without heartbeat notifications"
            )
            return

        if heartbeat_enabled and heartbeat_token and uptime_kuma_url:
            self.heartbeat = HeartbeatService(
                self.logger,
                str(uptime_kuma_url),
                str(heartbeat_token),
                heartbeat_interval,
                check_name=self.name,
            )
            self.logger.debug(
                f"✅ Heartbeat initialized for {self.name} (interval: {heartbeat_interval}s)"
            )

    @abstractmethod
    def execute(self) -> CheckResult:
        """Execute the check and return result.

        Returns:
            CheckResult with check outcome
        """
        pass

    def execute_with_heartbeat(self) -> CheckResult:
        """Execute check with automatic heartbeat management.

        Sends heartbeat at start and end (with duration), starts the service
        before execution and stops it afterward. Logs execution timeline and
        any errors that occur during execution.

        Returns:
            CheckResult from the check execution
        """
        try:
            if self.heartbeat:
                self.logger.debug(f"📤 Sending heartbeat start message for {self.name}")
                self.heartbeat.send_message(f"{self.name} check starting...")
                self.heartbeat.start()
                self.logger.debug(f"✅ Heartbeat service started for {self.name}")

            self.logger.info(f"▶️  Executing {self.name} check")
            result = self.execute()
            self.logger.info(
                f"✅ {self.name} check completed with status: {result.status}"
            )

            # Send end message with only status and duration (no detailed results)
            if self.heartbeat:
                status_emoji = "✅" if result.status == "up" else "❌"
                self.logger.debug(
                    f"📤 Sending heartbeat completion message for {self.name}"
                )
                self.heartbeat.send_message(
                    f"{status_emoji} {self.name} completed in {result.duration_seconds}s"
                )

            return result
        except TimeoutError as e:
            from kuma_sentinel.core.utils.sanitizer import DataSanitizer

            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(f"❌ {self.name} check timed out: {sanitized_error}")
            raise
        except Exception as e:
            from kuma_sentinel.core.utils.sanitizer import DataSanitizer

            sanitized_error = DataSanitizer.sanitize_error_message(e)
            self.logger.error(
                f"❌ {self.name} check failed with unexpected error: {sanitized_error}"
            )
            raise
        finally:
            if self.heartbeat:
                self.logger.debug(f"Stopping heartbeat service for {self.name}")
                self.heartbeat.stop()
