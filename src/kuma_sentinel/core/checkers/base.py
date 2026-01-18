"""Abstract base class for sentinel checks."""

from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Dict, Optional

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

    def __init__(self, logger: Logger, config: Dict[str, Any]):
        """Initialize the checker.

        Args:
            logger: Logger instance for output
            config: Configuration dictionary for this check
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
        """Initialize heartbeat service if enabled in config."""
        heartbeat_enabled = self.config.get("heartbeat_enabled", False)
        # Convert string "True"/"False" to boolean if needed
        if isinstance(heartbeat_enabled, str):
            heartbeat_enabled = heartbeat_enabled.lower() == "true"
        
        if (
            heartbeat_enabled
            and self.config.get("heartbeat_token")
            and self.config.get("uptime_kuma_url")
        ):
            self.heartbeat = HeartbeatService(
                self.logger,
                str(self.config.get("uptime_kuma_url")),
                str(self.config.get("heartbeat_token")),
                self.config.get("heartbeat_interval", 300),
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

        Starts heartbeat before execution and stops it afterward.

        Returns:
            CheckResult from the check execution
        """
        try:
            if self.heartbeat:
                self.heartbeat.send_message(f"{self.name} check starting...")
                self.heartbeat.start()

            return self.execute()
        finally:
            if self.heartbeat:
                self.heartbeat.stop()
